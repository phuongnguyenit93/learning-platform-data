# Đọc tài liệu, giới hạn dịch vụ và thông báo thay đổi OCI

## Mục tiêu bài học

Sau bài học, bạn có thể tìm đúng tài liệu Oracle Cloud Infrastructure (OCI), kiểm tra điều kiện áp dụng trước khi làm theo hướng dẫn, đọc giới hạn tài nguyên của tenancy và phân loại các thông báo thay đổi. Bạn cũng có thể chuyển thông tin đọc được thành một quyết định triển khai có căn cứ.

Bài học thuộc phần **Tổng quan Oracle Cloud Infrastructure** của module CLOUD_PROVIDERS_ORACLE. Ví dụ xuyên suốt là một nhóm chuẩn bị triển khai API Java, cơ sở dữ liệu và nơi lưu tệp trên OCI. Nhóm cần biết hướng dẫn nào áp dụng, có đủ quyền và hạn mức không, và thay đổi nào có thể ảnh hưởng đến hệ thống.

Các số liệu và thông báo giả định trong bài chỉ phục vụ giải thích. Khi triển khai thật, cần kiểm tra tài liệu hiện hành cùng dữ liệu của đúng tenancy, subscription và phạm vi tài nguyên.

## 1. Đọc tài liệu là một phần của quyết định kỹ thuật

Một hướng dẫn có thể mô tả đúng sản phẩm nhưng chưa phù hợp với môi trường của bạn. Khác biệt có thể nằm ở region, phiên bản công cụ, mô hình triển khai, kiểu tài khoản hoặc quyền truy cập.

Ví dụ, một bài thực hành tạo VM thành công ở một region không chứng minh tenancy của bạn có cùng hạn mức hoặc còn đủ năng lực cấp phát tại vị trí đang chọn. Tương tự, một ví dụ Java dùng API mới có thể cần phiên bản SDK mà dự án hiện chưa sử dụng.

Trước khi sao chép một bước triển khai, hãy xác định ba điều:

1. **Hướng dẫn áp dụng cho đối tượng nào?** Dịch vụ, tính năng, phiên bản và môi trường nào?
2. **Môi trường của mình có đáp ứng điều kiện không?** Quyền, mạng, hạn mức, vùng triển khai và công cụ đã phù hợp chưa?
3. **Thao tác tạo ra kết quả và tác động gì?** Tài nguyên nào được tạo, thay đổi, tính phí hoặc có thể gián đoạn?

Mục tiêu là biến một câu như “làm theo tài liệu OCI” thành mô tả cụ thể: “dùng hướng dẫn của dịch vụ đã chọn, kiểm tra điều kiện ở môi trường này và xác nhận kết quả bằng cách này”.

## 2. Chọn đúng loại tài liệu cho câu hỏi

Điểm khởi đầu là [Oracle Cloud Infrastructure Documentation](https://docs.oracle.com/en-us/iaas/Content/home.htm). Từ đây có thể đi đến hướng dẫn dịch vụ, tài liệu phát triển, kiến trúc, release notes và các trang thay đổi.

| Câu hỏi đang cần trả lời | Loại tài liệu nên mở | Kết quả cần lấy |
| --- | --- | --- |
| Dịch vụ này giải quyết vấn đề gì? | Overview, Concepts | Khái niệm, đối tượng và mô hình hoạt động |
| Cần chuẩn bị gì trước khi tạo tài nguyên? | Prerequisites, Getting Started | Quyền, cấu hình và phụ thuộc |
| Thực hiện một thao tác như thế nào? | Tasks, How-to | Các bước và cách xác nhận kết quả |
| Gọi API cần tham số gì? | API Reference | Tham số, kiểu dữ liệu, phản hồi và lỗi |
| Dùng dòng lệnh nào? | CLI Command Reference | Cú pháp, tham số bắt buộc và phân trang |
| Dùng thư viện Java ra sao? | SDK Guide, API Reference, ví dụ đúng phiên bản | Lớp, phương thức và cấu hình client |
| Tại sao thao tác không thành công? | Troubleshooting, Known Issues | Điều kiện lỗi và cách xử lý phù hợp |
| Có gì vừa được bổ sung? | Release Notes | Tính năng hoặc khả năng mới |
| Có thay đổi nào làm hỏng tích hợp cũ? | Service Change Announcements | Phạm vi ảnh hưởng và việc cần làm |
| Tenancy được dùng bao nhiêu tài nguyên? | Service Limits và dữ liệu tenancy | Tên limit, phạm vi, giá trị và mức sử dụng |

Tài liệu kiến trúc và hướng dẫn thao tác có vai trò khác nhau. Một sơ đồ tham khảo giúp hiểu cách kết hợp dịch vụ; hướng dẫn thao tác mô tả cách tạo thành phần. Trước khi áp dụng sơ đồ, cần đánh giá mục tiêu bảo mật, chi phí và khả năng phục hồi của hệ thống mình.

Bài viết cộng đồng có thể giúp tìm cách tiếp cận. Với điều kiện cấp phát, cú pháp API, giới hạn hoặc thời hạn thay đổi, nên đối chiếu với tài liệu chính thức của sản phẩm.

## 3. Kiểm tra phạm vi trước khi đọc chi tiết

### 3.1. Nhận diện đúng sản phẩm và mô hình triển khai

Những tên gần nhau có thể thuộc các mô hình khác nhau. Chẳng hạn, một hướng dẫn cơ sở dữ liệu cho dịch vụ được quản lý không tự áp dụng cho database do đội bạn cài trên Compute.

Tương tự, hướng dẫn cho public cloud, Cloud@Customer hoặc một sản phẩm thế hệ cũ có thể có khác biệt về quyền, giao diện và cách vận hành.

Một phiếu đọc ngắn có thể gồm:

~~~text
Mục tiêu: xác định cách triển khai thành phần X

Dịch vụ và tính năng:
Mô hình triển khai:
Region / realm liên quan:
Phiên bản công cụ hoặc phần mềm:
Điều kiện IAM:
Phụ thuộc mạng và dữ liệu:
Nguồn chính thức:
Ngày kiểm tra:
~~~

Đây là mẫu ghi chép để người học sử dụng khi cần, không phải cấu hình OCI.

### 3.2. Phân biệt phiên bản tài liệu với phiên bản môi trường

Cần tách các thông tin sau:

| Thông tin | Cho biết điều gì? |
| --- | --- |
| Ngày cập nhật trang | Thời điểm nội dung trang được chỉnh sửa |
| Phiên bản SDK hoặc CLI | Khả năng và hành vi của công cụ phía client |
| Phiên bản API | Hợp đồng giao tiếp mà thao tác sử dụng |
| Phiên bản database hoặc Kubernetes | Phiên bản phần mềm của tài nguyên đang vận hành |
| Ngày phát hành tính năng | Thời điểm khả năng được công bố theo phạm vi ghi trong thông báo |
| Ngày thay đổi có hiệu lực | Mốc hành vi hoặc khả năng được điều chỉnh |

Một trang mới cập nhật không bảo đảm ví dụ phù hợp với SDK cũ. Một tính năng mới cũng chưa chắc có trong mọi region hoặc loại tài nguyên. Cần đọc điều kiện đi kèm thay vì chỉ nhìn ngày hoặc tiêu đề.

### 3.3. Với Java, đối chiếu đúng SDK đang dùng

Tài liệu [SDK for Java](https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/javasdk.htm) là điểm bắt đầu cho việc phát triển với OCI. Ví dụ và tài liệu tham chiếu cần được đối chiếu với phiên bản SDK của dự án.

Oracle ghi nhận rằng thay đổi không tương thích của SDK được mô tả trong changelog; xem [Setup and Prerequisites](https://docs.oracle.com/en-us/iaas/Content/API/Concepts/devguidesetupprereq.htm).

Khi một đoạn mã mẫu không dùng được, hãy kiểm tra trước:

- Phiên bản SDK có cùng lớp và phương thức không?
- Các dependency và HTTP client đã phù hợp chưa?
- Client đang trỏ tới đúng region hoặc endpoint chưa?
- Danh tính có quyền với thao tác đang gọi không?
- Tham số có đúng kiểu và đúng tài nguyên của môi trường không?

Việc đổi một thư viện cần đánh giá cùng các dependency liên quan. Chỉ thay số phiên bản mà chưa đọc hướng dẫn chuyển đổi có thể tạo ra lỗi khác ở thời điểm chạy.

## 4. Cách đọc một hướng dẫn thao tác

Hãy đọc theo luồng **điều kiện → thao tác → kết quả → tác động**.

### 4.1. Điều kiện

Tìm các mục về quyền IAM, tài nguyên có sẵn, yêu cầu mạng và giới hạn. Nếu hướng dẫn nói “chọn subnet đã tạo”, cần hiểu subnet phải có những đặc điểm nào và ai có quyền dùng nó.

Không nên giải quyết mọi lỗi quyền bằng cách cấp quản trị toàn tenancy. Quyền cần được đối chiếu với thao tác và phạm vi tài nguyên thực sự sử dụng.

### 4.2. Thao tác

Phân biệt các cách Console, CLI và API. Tham số có thể có tên hoặc cách biểu diễn khác nhau, nhưng đều cần tham chiếu đúng đối tượng.

Ví dụ trong tài liệu có thể dùng shell Bash. Khi thực hành trên PowerShell, cần điều chỉnh cách đặt biến và xuống dòng; không sao chép nguyên cú pháp nối dòng giữa hai shell.

### 4.3. Kết quả

Tài nguyên xuất hiện trong danh sách chưa luôn có nghĩa thao tác đã hoàn tất. Một số dịch vụ có trạng thái vòng đời hoặc work request cần theo dõi.

Trước khi thực hiện bước phụ thuộc, hãy đọc cách tài liệu xác định thành công: trạng thái nào, trường dữ liệu nào hoặc kiểm tra kết nối nào được yêu cầu.

### 4.4. Tác động

Cần xác định thao tác có khởi động lại dịch vụ, thay địa chỉ, tạo tài nguyên tính phí hoặc làm dữ liệu không còn truy cập được không.

Ví dụ, một bước dọn tài nguyên phải được hiểu cùng chính sách giữ volume và bản sao lưu. Mục tiêu thực hành là hoàn thành bài học mà vẫn biết dữ liệu nào cần giữ và tài nguyên nào còn tồn tại.

## 5. Phân biệt các loại giới hạn

Một yêu cầu cấp phát có thể bị chặn vì nhiều lý do khác nhau.

| Khái niệm | Ý nghĩa | Hướng kiểm tra ban đầu |
| --- | --- | --- |
| Service limit | Hạn mức Oracle đặt cho tài nguyên trong phạm vi nhất định | Tên limit và giá trị hiện hành của tenancy |
| Compartment quota | Phân bổ hoặc hạn chế do quản trị viên đặt bằng quota policy | Chính sách áp dụng cho compartment và cây cha |
| Host capacity | Năng lực hạ tầng thực tế để đáp ứng cấu hình tại vị trí yêu cầu | Shape, region, AD và FD |
| API throttling | Hạn chế tốc độ gọi API | Mã lỗi, mức đồng thời và chính sách retry |
| Giới hạn kỹ thuật của dịch vụ | Ràng buộc như kích thước, số phần tử hoặc cấu hình hỗ trợ | Tài liệu riêng của tính năng |

Oracle giải thích service limit và compartment quota tại [Service Limits](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/overview.htm). Quota được quản trị viên cấu hình; việc đặt quota cao hơn không làm vượt được service limit. Xem [Quota Policy Syntax](https://docs.oracle.com/en-us/iaas/Content/Quotas/Concepts/quota_policy_syntax.htm).

Không phải mọi loại tài nguyên đều hỗ trợ cùng cơ chế quota hoặc truy vấn usage. Vì vậy, cần kiểm tra khả năng của limit hoặc dịch vụ cụ thể.

### 5.1. Đọc đủ tên, đơn vị và phạm vi

Một con số chưa có đơn vị và phạm vi thì chưa dùng được để lập kế hoạch.

Ví dụ cần xác định limit đang đo:

- Số tài nguyên hay lượng năng lực?
- Đơn vị CPU, bộ nhớ, dung lượng hoặc số lượng khác?
- Phạm vi toàn tenancy, region hay AD?
- Có gắn với một subscription cụ thể không?
- Có áp dụng cho đúng nhóm shape hoặc loại dịch vụ đang chọn không?

[Limits by Service](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/default.htm) công bố các giới hạn mặc định và phạm vi. Giá trị thực tế cần đối chiếu với tenancy; không dùng bảng mặc định như một bản ghi chắc chắn về tài khoản của mình.

Ví dụ, được cấp thêm số lượng instance chưa chắc giải quyết được thiếu hạn mức năng lực cho cấu hình cần dùng. Một VM còn có phụ thuộc về boot volume, subnet và các tài nguyên liên quan.

### 5.2. Có hạn mức không bảo đảm còn năng lực cấp phát

Host capacity là tài nguyên hạ tầng thực tế. Một yêu cầu vẫn có thể thất bại dù chưa dùng hết service limit.

Tài liệu [Resolving Out of Host Capacity error](https://docs.oracle.com/en-us/iaas/Content/Compute/Tasks/troubleshooting-out-of-host-capacity.htm?Highlight=Sea+sha) mô tả khả năng thiếu năng lực theo cấu hình và vị trí; các phương án có thể gồm đổi shape hoặc vị trí cấp phát.

Thay đổi AD hoặc region cũng có thể kéo theo thay đổi kết nối, dữ liệu, độ trễ và yêu cầu phục hồi. Vì vậy, cần đánh giá lại kiến trúc trước khi dùng phương án thay thế.

## 6. Đọc giới hạn thực tế trong Console

Trang **Limits, Quotas and Usage** cho phép xem các giới hạn theo bộ lọc phù hợp. Hướng dẫn chính thức là [Viewing a Tenancy's Limits and Usage](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/view-tenancy.htm).

Trình tự đọc:

1. Xác định tenancy và region đang làm việc.
2. Chọn dịch vụ.
3. Kiểm tra subscription nếu bộ lọc này áp dụng.
4. Chọn scope và compartment.
5. Đối chiếu tên limit, giá trị, usage và available.
6. Kiểm tra quota liên quan cùng nhu cầu cấp phát bổ sung.

Các trường thường gặp:

| Trường | Cách đọc |
| --- | --- |
| Limit Name | Tên kỹ thuật để tra cứu và đối chiếu |
| Service Limit | Tổng hạn mức theo phạm vi đã chọn |
| Usage | Mức đã sử dụng theo dữ liệu hiển thị |
| Available | Phần hạn mức còn lại theo cách tính của trường hiển thị |
| Scope | Phạm vi mà limit áp dụng |

Available trong trang giới hạn không phải cam kết rằng phần cứng của một shape đang sẵn sàng. Cần tách kiểm tra hạn mức với kiểm tra năng lực cấp phát.

Giao diện có thể không hiển thị mọi giới hạn của mọi dịch vụ. Nếu không tìm thấy một mục, hãy kiểm tra tài liệu dịch vụ và quyền truy cập trước khi kết luận tài nguyên không có giới hạn.

Đối với tài nguyên có đơn vị lẻ hoặc cách làm tròn, cần đọc phần giải thích của trường dữ liệu. Không áp dụng phép tính số nguyên cho mọi loại limit.

## 7. Tra cứu bằng CLI mà chưa thay đổi tài nguyên

Ví dụ sau dùng PowerShell và chỉ minh họa truy vấn. Điều kiện là OCI CLI đã được cấu hình xác thực, profile phù hợp và danh tính có quyền đọc cần thiết. Các giá trị trong dấu ngoặc nhọn cần được thay bằng dữ liệu môi trường thực.

### 7.1. Tìm định nghĩa và giá trị limit

~~~powershell
$tenancyOcid = '<OCID_TENANCY>'
$regionId = '<REGION_ID>'
$profileName = 'LEARNING'

oci limits definition list --compartment-id $tenancyOcid --service-name compute --region $regionId --profile $profileName --all

oci limits value list --compartment-id $tenancyOcid --service-name compute --region $regionId --profile $profileName --all
~~~

Lệnh thứ nhất giúp tìm tên và đặc điểm limit được hỗ trợ; lệnh thứ hai lấy các giá trị của dịch vụ theo phạm vi truy vấn. Tham khảo [limit definition list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/definition/list.html) và [limit value list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/value/list.html).

Tùy loại limit, có thể cần thêm bộ lọc subscription hoặc AD. Tùy chọn --all lấy toàn bộ các trang kết quả; nếu chỉ đọc trang đầu, bạn có thể bỏ sót mục cần kiểm tra.

Không đoán tên limit từ tên hiển thị của shape. Hãy lấy đúng tên kỹ thuật và scope từ dữ liệu định nghĩa hoặc tài liệu liên quan.

### 7.2. Đọc usage và availability của compartment

~~~powershell
$projectCompartmentOcid = '<OCID_COMPARTMENT_DU_AN>'
$limitName = '<TEN_LIMIT_DA_XAC_DINH>'
$limitScope = '<AD_HOAC_REGION_HOAC_GLOBAL>'

$availabilityArguments = @(
    'limits'
    'resource-availability'
    'get'
    '--compartment-id'
    $projectCompartmentOcid
    '--service-name'
    'compute'
    '--limit-name'
    $limitName
    '--region'
    $regionId
    '--profile'
    $profileName
)

if ($limitScope -eq 'AD') {
    $availabilityDomainName = '<TEN_AD_TRONG_TENANCY>'
    $availabilityArguments += @(
        '--availability-domain'
        $availabilityDomainName
    )
}

oci @availabilityArguments
~~~

Theo [resource-availability get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/limits/resource-availability/get.html), tham số AD phải được cung cấp khi scope của limit là AD và phải được bỏ khi scope không phải AD. Không phải mọi limit đều hỗ trợ API này; tài liệu cũng nêu trường hợp trả về 404 khi giá trị không có sẵn.

Kết quả availability phục vụ kiểm tra hạn mức. Nó không phải kết quả khảo sát năng lực phần cứng của một shape.

### 7.3. Đọc đúng ý nghĩa của lỗi truy vấn

Nếu lệnh thất bại, cần kiểm tra đồng thời tên limit, tham số scope, region, subscription khi áp dụng và quyền của danh tính.

Trong mô hình quyền của Limits API, các thao tác đọc định nghĩa và giá trị có yêu cầu khác với đọc resource availability theo compartment. Đối chiếu phần IAM trong tài liệu Service Limits thay vì mặc định profile đọc được danh sách VM sẽ đọc được mọi dữ liệu hạn mức.

Không đưa private key, token hoặc toàn bộ cấu hình xác thực vào báo cáo lỗi. Chỉ giữ những thông tin cần thiết để xác định thao tác và phạm vi truy vấn.

## 8. Ví dụ: đủ hạn mức cho một đợt triển khai chưa?

Giả sử nhóm triển khai API Java muốn tạo thêm ba VM. Mỗi VM cần hai đơn vị của một limit năng lực đã được xác định.

Các con số dưới đây hoàn toàn giả định. Giả sử chỉ có một quota liên quan, mọi số liệu cùng scope, cùng đơn vị, không có yêu cầu cấp phát đang chạy và không có ràng buộc quota bổ sung ở compartment cha.

| Dữ liệu | Giá trị giả định |
| --- | --- |
| Service limit | 24 đơn vị |
| Usage toàn phạm vi của limit | 18 đơn vị |
| Quota cho compartment dự án | 12 đơn vị |
| Usage của compartment dự án | 8 đơn vị |
| Nhu cầu tạo thêm | 3 VM × 2 đơn vị = 6 đơn vị |

Phân tích:

~~~text
Phần còn lại theo service limit: 24 - 18 = 6
Phần còn lại theo quota dự án: 12 - 8 = 4

Với các giả định của ví dụ:
phần có thể phân bổ thêm bị giới hạn ở 4 đơn vị.

Nhu cầu là 6 đơn vị:
chưa đáp ứng quota của compartment dự án.
~~~

Trong trường hợp này, chỉ gửi yêu cầu tăng service limit không xử lý được ràng buộc quota của dự án. Nhóm cần trao đổi với người quản lý quota về nhu cầu thực tế và phương án triển khai.

Nếu có quota ở nhiều cấp hoặc chính sách khác, phép tính minh họa trên chưa đủ. Cần đọc chính sách áp dụng và dữ liệu availability của đúng phạm vi.

### 8.1. Đừng chỉ tính trạng thái ổn định

Một ứng dụng có hai VM ở trạng thái ổn định có thể tạm cần VM thứ ba khi cập nhật theo cách tạo mới trước, chuyển lưu lượng rồi mới xóa máy cũ.

Vì vậy, nhu cầu cần tính có thể gồm:

- Tài nguyên đang phục vụ.
- Tài nguyên tạm thời trong cập nhật hoặc thay thế.
- Tài nguyên cho thử phục hồi.
- Tài nguyên phụ thuộc như volume và thành phần mạng.

Một kế hoạch vừa khít hạn mức ở trạng thái ổn định có thể không đủ để cập nhật hoặc phục hồi. Khi tính dự phòng, vẫn cần đánh giá chi phí và cách dọn tài nguyên tạm.

### 8.2. Khi nào đề nghị tăng service limit?

Chỉ nên gửi yêu cầu sau khi đã xác định đúng hạn mức đang chặn nhu cầu. Hồ sơ nên có dịch vụ, limit name, phạm vi, giá trị hiện tại, mức mong muốn và lý do triển khai.

Hướng dẫn [Creating a Limit Increase Request](https://docs.oracle.com/en-us/iaas/Content/General/service-limits/create-request.htm) mô tả cách gửi và theo dõi yêu cầu. Không nên giả định việc tăng được duyệt ngay hoặc tăng hạn mức sẽ giữ chỗ phần cứng.

Nếu vấn đề là quota nội bộ, làm việc với quản trị viên quota. Nếu vấn đề là host capacity, xem hướng dẫn năng lực cấp phát. Nếu là giới hạn kỹ thuật không hỗ trợ cấu hình mong muốn, cần điều chỉnh thiết kế hoặc xác minh với bộ phận hỗ trợ.

## 9. Đọc lỗi để chọn đúng tài liệu

Mã HTTP là điểm bắt đầu. Cần đọc thêm error code, thông điệp, request ID và trạng thái tài nguyên hoặc work request khi có.

| Dấu hiệu | Hướng điều tra |
| --- | --- |
| LimitExceeded | Kiểm tra service limit và scope |
| QuotaExceeded | Kiểm tra quota áp dụng cho compartment |
| Out of host capacity | Kiểm tra năng lực của cấu hình và vị trí cấp phát |
| TooManyRequests / HTTP 429 | Kiểm tra tốc độ gọi, mức đồng thời và backoff |
| NotAuthorizedOrNotFound | Kiểm tra cả quyền, định danh và phạm vi tài nguyên |
| InvalidParameter | Đối chiếu kiểu, giá trị và điều kiện tham số |

Các mã lỗi API phổ biến được mô tả tại [API Errors](https://docs.oracle.com/en-us/iaas/Content/API/References/apierrors.htm); vấn đề năng lực Compute có hướng dẫn riêng trong tài liệu Compute.

Một lỗi hạn mức hoặc quota không được giải quyết bằng việc retry liên tục khi điều kiện vẫn giữ nguyên. Với lỗi có thể thử lại, cần tuân theo hướng dẫn của thao tác và tính đến khả năng một yêu cầu trước đã tạo tác động.

Đối với ứng dụng Java dùng SDK, cần kiểm tra cấu hình retry hiện có trước khi thêm retry ở tầng ứng dụng. Hai tầng thử lại không được kiểm soát có thể làm tăng số lời gọi và kéo dài thời gian xử lý.

Thông tin tối thiểu để trao đổi kỹ thuật:

~~~text
Thao tác và dịch vụ:
Thời điểm, kèm múi giờ:
Region / AD / compartment liên quan:
Phiên bản CLI hoặc SDK:
HTTP status và error code:
Request ID hoặc work request ID:
Kết quả kỳ vọng:
Kết quả thực tế:
Các điều kiện đã kiểm tra:
~~~

Mẫu này giúp nối lỗi quan sát được với đúng tài liệu, đồng thời tránh kết luận sớm rằng mọi lỗi tạo tài nguyên đều do thiếu hạn mức.

## 10. Phân biệt các kênh thông tin thay đổi

| Kênh | Mục đích sử dụng |
| --- | --- |
| Release Notes | Theo dõi tính năng và khả năng mới được công bố |
| Service Change Announcements | Theo dõi thay đổi hành vi, ngừng hỗ trợ tính năng hoặc API và yêu cầu chuyển đổi |
| Known Issues | Tra cứu vấn đề đã biết và cách xử lý hoặc giới hạn liên quan |
| Console Announcements | Đọc thông tin vận hành liên quan đến môi trường theo phạm vi thông báo |
| OCI Status | Đối chiếu trạng thái dịch vụ công khai theo phạm vi được cung cấp |
| Changelog SDK, CLI hoặc provider | Đánh giá thay đổi của công cụ phía client |

Các điểm truy cập chính thức:

- [OCI Release Notes](https://docs.oracle.com/en-us/iaas/releasenotes/index.htm).
- [Service Change Announcements](https://docs.oracle.com/en-us/iaas/Content/servicechanges.htm).
- [Known Issues](https://docs.oracle.com/en-us/iaas/Content/knownissues.htm).
- [Console Announcements](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/announcements.htm).
- [OCI Status](https://ocistatus.oraclecloud.com/).

### 10.1. Release notes: điều gì mới có thể sử dụng?

Khi đọc một release note, hãy lấy tên dịch vụ, ngày phát hành, phạm vi triển khai và đường dẫn hướng dẫn chi tiết.

Một tính năng mới có thể hữu ích cho việc giám sát hoặc tự động hóa hệ thống, nhưng cần đánh giá điều kiện áp dụng. Không nhất thiết nâng cấp production ngay khi thấy một thông báo mới.

Ví dụ giả định, một dịch vụ bổ sung metric mới. Nhóm cần kiểm tra metric có xuất hiện ở tài nguyên của mình không, quyền đọc có phù hợp không và alarm nào thực sự cần dùng metric đó.

### 10.2. Service changes: điều gì cần điều chỉnh?

Trang Service Change Announcements mô tả những thay đổi có thể ảnh hưởng tương thích, gồm API, tính năng bị ngừng hỗ trợ và hành vi dịch vụ.

Các trường quan trọng là:

| Trường hoặc câu hỏi | Ý nghĩa cần lấy |
| --- | --- |
| Date Announced | Ngày công bố thông tin |
| Date in Effect | Ngày thay đổi bắt đầu áp dụng |
| Details | Nội dung điều chỉnh |
| Does this impact me? | Điều kiện để hệ thống thuộc phạm vi ảnh hưởng |
| What do I need to do? | Hành động được yêu cầu hoặc hướng chuyển đổi |

Ngày công bố và ngày hiệu lực có vai trò khác nhau. Một mục được công bố từ lâu vẫn có thể liên quan nếu thời điểm áp dụng sắp đến; một thông báo mới cũng có thể mô tả thay đổi đã có hiệu lực.

### 10.3. Known issues và trạng thái vận hành

Known Issues giúp nhận diện vấn đề đã được ghi nhận. Workaround cần được đối chiếu với cấu hình và phiên bản đang dùng, vì có thể làm thay đổi hiệu năng hoặc mô hình vận hành.

OCI Status cung cấp thông tin trạng thái dịch vụ; ví dụ cách liên hệ với trang này được mô tả trong [Oracle Database Overview](https://docs.oracle.com/en-us/iaas/doc/database-overview.html).

Không thấy sự cố trên trang trạng thái chưa đủ để kết luận cấu hình ứng dụng đúng. Vẫn cần kiểm tra mạng, quyền, tài nguyên và log của hệ thống mình.

## 11. Đọc Console Announcements theo mức ảnh hưởng

Console Announcements truyền đạt thông tin vận hành quan trọng. Một số loại tiêu biểu là **Required action**, **Recommended action**, **Scheduled maintenance**, **Planned change** và **Information**. Ý nghĩa và các loại đầy đủ nằm trong tài liệu Console Announcements.

Không cần ghi nhớ toàn bộ danh sách nhãn. Cần xác định thông báo có yêu cầu hành động, có cửa sổ tác động hoặc chỉ cung cấp thông tin để theo dõi.

Khi mở một thông báo, hãy trả lời:

1. Dịch vụ và môi trường nào bị ảnh hưởng?
2. Region, tài nguyên hoặc phạm vi nào được nêu?
3. Bắt đầu và kết thúc khi nào, theo múi giờ nào?
4. Có yêu cầu thao tác trước hạn không?
5. Có thể xảy ra restart, mất kết nối hoặc thay đổi hành vi không?
6. Có bản cập nhật thay lịch hoặc xác nhận hoàn tất không?

Nếu giao diện không hiển thị thông báo hoặc chỉ hiện tóm tắt, cần kiểm tra quyền. Tài liệu nêu việc xem danh sách và chi tiết còn phụ thuộc quyền được cấp; không nên kết luận “không có thay đổi” chỉ từ một màn hình trống.

### 11.1. Đọc chi tiết và lịch sử cập nhật

Thông báo có thể có mô tả, OCID và mã tham chiếu phục vụ trao đổi với Support. Xem [Viewing the Details of an Announcement](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/announcements_topic-To_view_the_details_of_an_announcement.htm).

Một lịch bảo trì có thể được cập nhật. Khi chuẩn bị hành động, cần mở lại thông báo và kiểm tra phiên bản thông tin hiện tại, thay vì chỉ dùng nội dung email đầu tiên.

Thời gian cần được ghi cả mốc gốc lẫn giờ địa phương. Ví dụ giả định:

~~~text
Cửa sổ trong thông báo: 01:00–02:00 UTC
Giờ Việt Nam, UTC+7:   08:00–09:00 cùng ngày
~~~

Nếu việc đổi múi giờ đi qua nửa đêm, ngày địa phương cũng thay đổi. Ngoài ra, đừng suy ra phạm vi ảnh hưởng chỉ từ tên region xuất hiện trong địa chỉ email gửi.

### 11.2. Thiết lập đường nhận thông tin

OCI hỗ trợ announcement subscription với bộ lọc và một Notifications topic để chuyển thông báo đến các endpoint đã cấu hình. Xem [Subscribing to Announcements](https://docs.oracle.com/en-us/iaas/Content/General/Concepts/announcements_topic-Subscribing.htm).

Về mặt vận hành, cần xác định:

- Ai đọc thông tin cho từng nhóm dịch vụ?
- Bộ lọc có bỏ sót tài nguyên hoặc region đang dùng không?
- Endpoint nhận thông báo có hoạt động và được theo dõi không?
- Ai xử lý khi người phụ trách chính vắng mặt?
- Sau thay đổi phạm vi hệ thống, bộ lọc có được cập nhật không?

Chỉ tạo subscription chưa chứng minh cả đội nhận và xử lý được thông tin. Cần kiểm tra đường nhận theo khả năng được hỗ trợ và có trách nhiệm phản hồi rõ ràng.

Các hướng dẫn này mô tả quy trình cho hệ thống của người học; bài học không thực hiện đăng ký hay gửi thông báo.

## 12. Chuyển thông báo thành một kế hoạch thay đổi

Một thông báo chỉ có giá trị vận hành khi được nối với tài nguyên và mã đang sử dụng.

### 12.1. Quy trình đánh giá ảnh hưởng

~~~mermaid
flowchart TD
    A["Nhận release note hoặc thông báo"] --> B["Xác định dịch vụ, phạm vi và mốc thời gian"]
    B --> C["Đối chiếu tài nguyên, phiên bản và cấu hình"]
    C --> D{"Hệ thống thuộc phạm vi ảnh hưởng?"}
    D -->|"Chưa rõ"| E["Thu thập thêm bằng chứng hoặc hỏi Support"]
    E --> C
    D -->|"Không"| F["Ghi căn cứ và điều kiện cần xem lại"]
    D -->|"Có"| G["Lập hành động, người phụ trách và hạn xử lý"]
    G --> H["Thử trong môi trường phù hợp"]
    H --> I["Triển khai theo kế hoạch thay đổi"]
    I --> J["Kiểm tra kết quả và theo dõi sau thay đổi"]
~~~

Để kết luận không bị ảnh hưởng, cần có căn cứ. Ví dụ, thông báo áp dụng cho một kiểu endpoint mà hệ thống không sử dụng. Câu “chưa thấy lỗi” chưa chứng minh không phụ thuộc vào khả năng sắp thay đổi.

### 12.2. Ví dụ giả định với ứng dụng Java

Giả sử Oracle thông báo rằng sau một mốc thời gian, một dịch vụ sẽ không chấp nhận một cấu hình TLS cũ. Đây là tình huống minh họa, không đại diện cho một lịch thay đổi hiện hành.

Nhóm cần làm rõ:

| Bước | Bằng chứng hoặc kết quả cần có |
| --- | --- |
| Xác định phụ thuộc | Client Java và thành phần trung gian nào kết nối tới endpoint bị ảnh hưởng |
| Kiểm tra hiện trạng | Phiên bản runtime, thư viện HTTP và cấu hình TLS thực sự đang chạy |
| Chọn thay đổi | Cách cập nhật phù hợp với hướng dẫn và khả năng hỗ trợ |
| Thử trước | Kết nối, xác thực, tải đại diện và tình huống lỗi đều được kiểm tra |
| Triển khai | Có thời điểm, người phụ trách và tín hiệu theo dõi |
| Xác nhận | Yêu cầu nghiệp vụ đi qua toàn bộ chuỗi vẫn hoàn thành |

Chỉ sửa SDK chưa chắc đủ nếu kết nối còn đi qua proxy hoặc thành phần khác có cấu hình riêng. Ngược lại, nếu lỗi nằm ở mã phía client, thay cấu hình VM đơn thuần có thể không xử lý đúng nguyên nhân.

Phương án quay lại cũng cần được đánh giá theo mốc hiệu lực. Sau khi nhà cung cấp loại bỏ một khả năng cũ, đưa client trở lại cấu hình cũ có thể không khôi phục được dịch vụ. Khi đó cần phương án thay thế nằm trong các khả năng còn được hỗ trợ.

### 12.3. Ghi một mục hành động có thể kiểm tra

~~~text
Nguồn chính thức:
Mã thông báo hoặc đường dẫn:
Ngày kiểm tra gần nhất:
Ngày hiệu lực / cửa sổ bảo trì:
Tài nguyên và môi trường liên quan:
Kết luận ảnh hưởng và bằng chứng:
Hành động:
Người phụ trách:
Hạn nội bộ:
Cách thử và tiêu chí thành công:
Phương án xử lý nếu thay đổi thất bại:
Trạng thái và bằng chứng hoàn tất:
~~~

Hạn nội bộ nên dành chỗ cho kiểm thử và điều chỉnh trước thời điểm bắt buộc. Với thông báo đổi lịch, cần cập nhật kế hoạch theo thông tin mới.

## 13. Thực hành đọc tài liệu trước một bài lab OCI

Giả sử bạn chuẩn bị tạo môi trường cho API Java, kết nối một dịch vụ Oracle Database và lưu tệp trên Object Storage.

Trước khi cấp phát, hãy hoàn thành các bước sau:

1. **Chọn nguồn:** mở tài liệu chính thức của từng dịch vụ và xác định mô hình triển khai.
2. **Đọc điều kiện:** ghi quyền IAM, yêu cầu mạng và các thành phần cần có.
3. **Đối chiếu công cụ:** ghi phiên bản CLI hoặc SDK dự định dùng và mở tài liệu tương ứng.
4. **Đọc giới hạn:** xác định limit name, đơn vị, scope và giá trị trong tenancy.
5. **Tính nhu cầu:** gồm tài nguyên ban đầu và phần tạm cần khi cập nhật hoặc thử phục hồi.
6. **Kiểm tra thay đổi:** đọc service changes, known issues và thông báo liên quan.
7. **Xác định kết quả:** ghi cách biết tài nguyên và luồng ứng dụng đã hoạt động.
8. **Chuẩn bị kết thúc:** xác định dữ liệu cần giữ và tài nguyên cần dọn.

Kết quả có thể trình bày trong một bảng:

| Thành phần | Tài liệu áp dụng | Điều kiện quan trọng | Giới hạn cần kiểm tra | Tín hiệu hoàn thành |
| --- | --- | --- | --- | --- |
| API Java | Hướng dẫn Compute hoặc nền tảng thực thi được chọn | Quyền, image, mạng, runtime | Các limit liên quan đến cấu hình và volume | API đáp ứng kiểm tra sức khỏe |
| Oracle Database | Tài liệu đúng dịch vụ và mô hình | Kết nối, quyền, lựa chọn triển khai | Limit năng lực, lưu trữ và tài nguyên liên quan | Ứng dụng thực hiện được thao tác dữ liệu cần thiết |
| Object Storage | Hướng dẫn bucket và truy cập object | Quyền, cơ chế xác thực, đường kết nối | Các ràng buộc của bucket, object và thao tác đang dùng | Ghi và đọc lại tệp giả lập thành công |

Không cần tạo tài nguyên để luyện phần nhận diện tài liệu. Nếu chưa có tenancy hoặc quyền xem limit, hãy đánh dấu dữ liệu còn thiếu; bảng mặc định chỉ là thông tin tham khảo cho đến khi kiểm tra được môi trường thật.

## 14. Những nhầm lẫn cần tránh

| Nhầm lẫn | Cách đọc và xử lý đúng |
| --- | --- |
| Trang tài liệu mới nhất luôn phù hợp với dự án | Đối chiếu sản phẩm, mô hình và phiên bản đang dùng |
| Tutorial thành công nghĩa là production đã sẵn sàng | Bổ sung quyền, chi phí, vận hành và phục hồi theo yêu cầu |
| Limit mặc định là giá trị chắc chắn của tenancy | Kiểm tra giá trị và bộ lọc thực tế |
| Available nghĩa là chắc chắn tạo được VM | Kiểm tra riêng năng lực phần cứng và các điều kiện cấp phát |
| Nâng quota là vượt được service limit | Service limit vẫn có hiệu lực |
| Mọi lỗi 404 đều là tài nguyên không tồn tại | Đọc mã lỗi, quyền và điều kiện của API cụ thể |
| Retry liên tục sẽ giải quyết lỗi hạn mức | Phải xử lý điều kiện hạn mức hoặc quota đang chặn |
| Release notes thay thế mọi thông báo vận hành | Theo dõi thêm service changes và thông báo của môi trường |
| Đã nhận email thì việc thay đổi đã được xử lý | Cần người phụ trách, hành động và bằng chứng hoàn thành |
| Không thấy cảnh báo nghĩa là không có ảnh hưởng | Kiểm tra phạm vi, quyền, bộ lọc và phụ thuộc thực tế |

Khi học các phần tiếp theo của OCI, hãy duy trì thói quen gắn mỗi quyết định với **nguồn chính thức, phạm vi áp dụng, dữ liệu môi trường và thời điểm kiểm tra**. Cách làm này giúp việc triển khai có phân quyền, tự động hóa, kiểm soát chi phí và chuẩn bị tính sẵn sàng dựa trên những điều kiện có thể đối chiếu được.
