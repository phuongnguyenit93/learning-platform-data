# Thiết kế quyền tối thiểu theo compartment và nhóm dịch vụ

## 1. Mục tiêu và bối cảnh

Quyền tối thiểu là cấp đủ quyền để một người hoặc workload hoàn thành nhiệm vụ đã được duyệt, trong phạm vi tài nguyên cần thiết và khoảng thời gian còn nhu cầu. Trên Oracle Cloud Infrastructure (OCI), việc này cần phối hợp chủ thể truy cập, IAM policy, compartment, loại tài nguyên và những điều kiện bổ sung.

Ví dụ, một nhóm chỉ cần xem trạng thái máy ứng dụng không nhất thiết phải quản lý toàn bộ Compute. Một ứng dụng Java cần đọc file đầu vào trong một bucket không cần quyền quản lý mọi tài nguyên lưu trữ của tenancy.

Bài học thuộc chương **Danh tính và phân quyền IAM** của module **CLOUD_PROVIDERS_ORACLE**. Nội dung liên hệ IAM với tenancy, compartment, VCN, Compute, lưu trữ và dịch vụ cơ sở dữ liệu Oracle để thiết kế hạ tầng có phân quyền, giám sát, tự động hóa, kiểm soát chi phí và tính sẵn sàng.

Sau bài học, bạn có thể:

- Chuyển một nhiệm vụ nghiệp vụ thành phạm vi quyền cụ thể.
- Phân biệt group danh tính với nhóm loại tài nguyên của dịch vụ.
- Giải thích quyền kế thừa theo cây compartment và quyền cộng dồn từ nhiều nguồn.
- Chọn verb, resource-type và điều kiện phù hợp thay vì cấp quyền rộng để sửa lỗi.
- Thiết kế những vai trò tách biệt cho mạng, Compute, dữ liệu và workload.
- Kiểm chứng quyền được cấp và việc thu hồi bằng bằng chứng phù hợp.

## 2. Bắt đầu từ nhiệm vụ thay vì câu lệnh policy

Trước khi viết policy, hãy mô tả yêu cầu theo mẫu:

> Chủ thể nào cần thực hiện thao tác nào, trên tài nguyên nào, trong compartment nào, vì mục đích gì và đến khi nào?

Ví dụ yêu cầu rõ ràng:

- Nhóm hỗ trợ cần liệt kê và xem thông tin instance của ứng dụng trong compartment lab.
- Nhóm vận hành nguồn cần thực hiện những thao tác nguồn đã được phê duyệt trên instance lab.
- Đội mạng quản lý vòng đời tài nguyên mạng trong compartment mạng lab.
- Ứng dụng đọc object trong bucket đầu vào được chỉ định.
- Tác vụ xuất báo cáo tạo object mới trong bucket đầu ra, không đọc hoặc xóa dữ liệu đã có.

Yêu cầu “cho nhóm phát triển dùng OCI” chưa đủ để suy ra bộ quyền. Nó không nói rõ có được tạo instance, sửa mạng, tải dữ liệu, thay secret hay xóa tài nguyên không.

### 2.1. Ma trận nhu cầu

| Chủ thể | Thao tác được duyệt | Phạm vi | Thao tác ngoài nhu cầu |
| --- | --- | --- | --- |
| Người xem Compute | Liệt kê và xem instance | Compartment ứng dụng lab | Tạo, cập nhật hoặc xóa instance |
| Người vận hành nguồn | Thao tác nguồn theo vai trò | Instance thuộc lab | Quản trị mạng, thay policy |
| Người quản trị mạng | Vận hành vòng đời mạng | Compartment mạng lab | Đọc dữ liệu nghiệp vụ trong bucket |
| Workload ứng dụng | Đọc dữ liệu đầu vào | Bucket được chỉ định | Tạo bucket hoặc xóa object |
| Tác vụ xuất dữ liệu | Tạo object mới | Bucket đầu ra được chỉ định | Đọc, ghi đè hoặc xóa object |
| Người quan sát database | Xem thông tin tài nguyên database | Compartment dữ liệu lab | Quản trị toàn bộ nền tảng database |

Ma trận là đặc tả thiết kế. Bộ quyền thực tế cần được đối chiếu với API và permission của từng dịch vụ; tên vai trò không tự bảo đảm đúng giới hạn.

## 3. Hai nghĩa khác nhau của “nhóm dịch vụ”

Trong thiết kế quyền, cần phân biệt:

1. **Group danh tính:** tập người dùng, chẳng hạn nhóm vận hành Compute.
2. **Resource family:** nhóm loại tài nguyên được OCI định nghĩa để viết policy, chẳng hạn `instance-family`, `virtual-network-family` hoặc `object-family`.

Một group danh tính có thể nhận nhiều statement trên nhiều loại tài nguyên. Một resource family không phải nhóm người dùng, cũng không phải phạm vi compartment.

| Khái niệm | Ví dụ | Tác dụng |
| --- | --- | --- |
| User group | `LabComputeViewers` | Gom người dùng có cùng nhiệm vụ |
| Dynamic group | `LabAppRuntime` | Chọn những tài nguyên/workload thuộc cơ chế hỗ trợ làm chủ thể |
| Resource-type riêng lẻ | `instances`, `buckets`, `objects` | Chọn loại tài nguyên cấp quyền |
| Resource family | `instance-family`, `object-family` | Gom nhiều loại tài nguyên và quyền theo định nghĩa dịch vụ |
| Compartment | `LabApp`, `LabData` | Xác định phạm vi tài nguyên và cây kế thừa |

Không suy ra một family chỉ gồm những quyền bạn đang nghĩ tới. Chẳng hạn, Oracle mô tả `instance-family` có thêm một số quyền liên quan VNIC và volume ngoài các loại tài nguyên trực tiếp của Compute để hỗ trợ các tình huống phổ biến. [Oracle: Details for the Core Services](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm)

Family giúp rút ngắn policy, nhưng không phải lúc nào cũng là lựa chọn nhỏ nhất. Khi nhiệm vụ hẹp, bắt đầu từ resource-type riêng lẻ và kiểm tra permission cụ thể thường dễ giải thích hơn.

## 4. Thiết kế cây compartment trước khi cấp quyền

Giả sử môi trường thực hành có cấu trúc:

~~~text
Tenancy
├── Labs
│   ├── LabNetwork
│   ├── LabApp
│   └── LabData
└── Production
    ├── ProdNetwork
    ├── ProdApp
    └── ProdData
~~~

Trong ví dụ:

- VCN và subnet dùng chung cho lab nằm ở `LabNetwork`.
- Instance chạy ứng dụng nằm ở `LabApp`.
- Bucket và tài nguyên database lab nằm ở `LabData`.
- Môi trường sản xuất thuộc nhánh riêng.

Đây là một phương án minh họa, không phải cấu trúc bắt buộc cho mọi tenancy. Tách compartment cần phản ánh trách nhiệm, vòng đời và phạm vi kiểm soát; không cần tạo một compartment cho mọi tài nguyên đơn lẻ.

### 4.1. Quyền từ phạm vi cha ảnh hưởng phạm vi con

Khi cấp quyền áp dụng cho một compartment, phải xét những compartment con của nó. OCI sử dụng kế thừa quyền theo cây compartment. Vì vậy, một quyền rộng ở `Labs` có thể ảnh hưởng `LabApp`, `LabNetwork` và `LabData`; việc tạo compartment con mới không tự loại bỏ quyền từ phía trên. [Oracle: Managing Compartments](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm)

Hệ quả thiết kế:

- Không cấp quyền quản lý rộng ở `Labs` nếu chủ thể chỉ cần vận hành `LabApp`.
- Khi đánh giá quyền ở compartment con, phải xem cả các nguồn cấp từ cha và tenancy.
- Không đặt quyền lab ở phạm vi `tenancy` chỉ vì đó là vị trí dễ chọn trong Console.
- Khi di chuyển resource hoặc compartment, đánh giá những quyền sẽ mất và những quyền mới có hiệu lực.

Compartment là phạm vi tổ chức tài nguyên và cấp quyền; nó không thay thế VCN, subnet, NSG hoặc cơ chế xác thực trong ứng dụng. Tách compartment không tự chặn đường mạng hoặc quyền SQL đã được cấp độc lập.

### 4.2. Vị trí đặt policy và phạm vi cấp quyền là hai quyết định

Một policy được gắn vào một compartment hoặc root. Vị trí gắn policy ảnh hưởng ai có thể quản lý policy đó; phần `in compartment ...` của statement xác định tài nguyên được cấp quyền.

Trong các ví dụ bên dưới, giả sử policy được quản trị tập trung tại **Labs**, còn `LabApp`, `LabNetwork` và `LabData` là những compartment con trực tiếp. Vì vậy, tên compartment ở statement có thể được đối chiếu rõ trong cây này.

Nếu đặt policy cao hơn, cần tham chiếu đường dẫn compartment phù hợp hoặc OCID. Không sao chép tên một compartment lá mà bỏ qua cây thực tế. Cú pháp và ngữ nghĩa gắn policy cần được đối chiếu khi chọn nơi tạo policy. [Oracle: How Policies Work](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policies.htm)

Không giao quyền sửa policy cho nhóm vận hành tài nguyên chỉ để họ tự giải quyết lỗi thiếu quyền. Khả năng thay policy là một năng lực quản trị cần được xem xét riêng.

## 5. Chọn đúng chủ thể trong Identity Domain

Cú pháp subject có thể chỉ rõ domain và group:

~~~text
Allow group 'Default'/'LabComputeViewers' to <verb> <resource-type> in compartment LabApp
~~~

`Default` là tên domain minh họa. Nếu group thuộc domain khác, phải dùng đúng domain đó. Hai group cùng tên ở hai domain không phải cùng một chủ thể. OCI cũng hỗ trợ tham chiếu group bằng OCID theo cú pháp policy tương ứng. [Oracle: Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm)

Nên đặt group theo nhiệm vụ, chẳng hạn xem Compute hoặc vận hành mạng, rồi quản lý membership qua quy trình được phê duyệt. Không dùng tên group làm bằng chứng rằng quyền thực tế đã đúng.

Ví dụ, group mang tên `ReadOnly` vẫn có thể nhận quyền quản lý nếu một policy khác cấp như vậy. Một user thuộc nhiều group phải được đánh giá theo toàn bộ quyền có hiệu lực của user đó.

Với workload, chọn danh tính tài nguyên phù hợp thay cho credential cá nhân khi được dịch vụ hỗ trợ. Quy tắc chọn thành viên dynamic group là một phần của ranh giới bảo mật, không chỉ là thao tác cấu hình phụ.

## 6. Chọn verb theo API và permission

Policy OCI thường dùng cấu trúc:

~~~text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
~~~

Phần điều kiện có thể bỏ khi không cần. Những thành phần này phối hợp để xác định yêu cầu nào được cho phép. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm)

Các verb thường gặp là `inspect`, `read`, `use` và `manage`, nhưng phải đọc bảng ánh xạ của loại tài nguyên thực tế:

| Verb | Cách tiếp cận khi thiết kế | Không nên suy diễn |
| --- | --- | --- |
| `inspect` | Xem những permission quan sát cơ bản của loại tài nguyên | Mọi dịch vụ đều cho cùng một kiểu dữ liệu |
| `read` | Kiểm tra thêm những nội dung hoặc API đọc được cấp | Mọi thao tác đọc đều không nhạy cảm |
| `use` | Kiểm tra những thao tác sử dụng và cập nhật đi kèm | Chỉ “dùng”, không thể thay đổi trạng thái |
| `manage` | Xem toàn bộ quyền được đưa vào mức này | Chỉ tạo tài nguyên, không có quyền xóa hoặc thay đổi quan trọng |

### 6.1. Verb chỉ là cách gom permission

Để chọn đúng quyền, cần tra:

1. API operation nào thực hiện nhiệm vụ?
2. Operation đó cần những permission nào?
3. Permission thuộc resource-type và verb nào?
4. Có condition phù hợp để giới hạn thêm không?
5. Có tài nguyên phụ thuộc nằm ở compartment khác không?

Một verb có thể gom nhiều permission hơn nhiệm vụ hiện tại. Vì vậy, “chọn verb thấp nhất có vẻ hợp lý” là bước khởi đầu, không phải toàn bộ quy trình thiết kế.

### 6.2. Quyền đọc cũng có thể nhạy cảm

Object Storage `read objects` cho phép đọc nội dung object, không chỉ xem tên file. Với Autonomous Database, tài liệu policy phân biệt `inspect` với `read`; một số API tạo hoặc lấy wallet được ánh xạ ở mức `read autonomous-databases`. Không dùng quyền đọc như một nhãn an toàn chung cho mọi dịch vụ. [Oracle: Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/objectstoragepolicyreference.htm), [Oracle: IAM Policies for Autonomous Database](https://docs.oracle.com/en-us/iaas/autonomous-database-serverless/doc/autonomous-database-iam-policies.html)

Nếu người quan sát chỉ cần thông tin tài nguyên Autonomous Database, xem xét bắt đầu từ `inspect autonomous-databases` và kiểm tra các operation cần thiết. Quyền OCI quản lý tài nguyên database cũng phải được phân biệt với user và quyền dữ liệu bên trong database.

## 7. Các mẫu policy theo nhiệm vụ

Các mẫu sau minh họa thiết kế trong cây lab ở trên. Group, dynamic group, compartment và bucket phải được tạo, xác nhận và phê duyệt riêng trước khi áp dụng. Những chuỗi trong dấu `<...>` là placeholder, không phải định danh có thể dùng nguyên văn.

Không cần cấp đồng thời tất cả các mẫu cho một user. Mỗi mẫu phục vụ một nhiệm vụ khác nhau.

### 7.1. Liệt kê và xem instance của ứng dụng lab

~~~text
Allow group 'Default'/'LabComputeViewers' to read instances in compartment LabApp where any {request.operation = 'ListInstances', request.operation = 'GetInstance'}
~~~

Statement giữ phạm vi tại `LabApp`, chọn loại `instances` và giới hạn operation phục vụ yêu cầu đã nêu. Nó không nhằm làm mọi mục trong giao diện Compute hiển thị đầy đủ.

Nếu người dùng cần xem VNIC hoặc volume, xác định nhu cầu đó và cấp quyền tương ứng riêng. Không đổi ngay sang quản lý toàn `instance-family` chỉ vì một tab phụ bị từ chối.

`any` là điều kiện OR: operation phải là một trong những giá trị được liệt kê. OCI hỗ trợ `any` và `all` để kết hợp điều kiện; biến điều kiện phải phù hợp với yêu cầu đang xét. [Oracle: Conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/conditions.htm)

### 7.2. Vận hành trạng thái nguồn của instance

Một vai trò vận hành nguồn có thể cần quyền xem instance và thực hiện các power action:

~~~text
Allow group 'Default'/'LabPowerOperators' to read instances in compartment LabApp where any {request.operation = 'ListInstances', request.operation = 'GetInstance'}
Allow group 'Default'/'LabPowerOperators' to use instances in compartment LabApp where request.permission = 'INSTANCE_POWER_ACTIONS'
~~~

Oracle ánh xạ operation `InstanceAction` tới permission `INSTANCE_POWER_ACTIONS`. Điều kiện ở statement thứ hai giới hạn permission được cho phép thay vì cấp toàn bộ những quyền khác của `use instances`. [Oracle: Permissions Required for Each Core API Operation](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm)

Mẫu này không khẳng định chỉ cho phép một action cụ thể như START. Nhiều thao tác nguồn dùng chung operation và permission; nếu nghiệp vụ cần giới hạn sâu hơn, phải kiểm tra biến được dịch vụ hỗ trợ hoặc thiết kế một luồng tự động hóa có kiểm soát.

Các power action có thể ảnh hưởng tính sẵn sàng. Dù không có quyền tạo hoặc xóa tài nguyên, vai trò này vẫn cần phê duyệt và dấu vết vận hành.

### 7.3. Quản trị mạng trong phạm vi riêng

~~~text
Allow group 'Default'/'LabNetworkAdmins' to manage virtual-network-family in compartment LabNetwork
~~~

Mẫu này dành cho người chịu trách nhiệm **vòng đời tài nguyên mạng** trong lab. Nó là quyền rộng trong một phạm vi dịch vụ đã được giới hạn, phù hợp khi nhiệm vụ thực sự cần quản trị mạng.

Nếu nhóm chỉ cần sử dụng subnet đã có để triển khai ứng dụng, không dùng mẫu quản trị mạng này thay cho những quyền sử dụng phụ thuộc. Việc quản trị route, gateway và quy tắc mạng cần được phân công riêng.

### 7.4. Người đọc dữ liệu trong một bucket

Giả sử bucket `lab-input` ở `LabData` chứa dữ liệu thử nghiệm:

~~~text
Allow group 'Default'/'LabInputReaders' to read buckets in compartment LabData where target.bucket.name = 'lab-input'
Allow group 'Default'/'LabInputReaders' to read objects in compartment LabData where target.bucket.name = 'lab-input'
~~~

Statement đầu phục vụ việc đọc cấu hình bucket đã biết; statement sau cho phép đọc object trong bucket đó. Không có nhu cầu đọc cấu hình bucket thì cần đánh giá lại sự cần thiết của statement đầu.

Không mặc định điều kiện tên bucket sẽ cho phép liệt kê tất cả bucket trong compartment. Operation liệt kê có thể không có biến target tương ứng như yêu cầu đang xét. Khi biến điều kiện không áp dụng, phải kiểm tra hành vi theo tài liệu và thiết kế một quyền discovery riêng nếu thật sự cần.

Tên trong condition của OCI có quy tắc đối chiếu riêng; tài liệu Object Storage lưu ý điều kiện tên bucket không phân biệt hoa thường. Không tạo hai ranh giới bảo mật chỉ khác chữ hoa/chữ thường rồi dựa vào điều kiện tên để tách chúng. [Oracle: Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/objectstoragepolicyreference.htm)

### 7.5. Tạo object mới mà không đọc, ghi đè hoặc xóa

Giả sử tác vụ xuất báo cáo chỉ cần tạo object mới trong `lab-output`:

~~~text
Allow group 'Default'/'LabReportWriters' to manage objects in compartment LabData where all {target.bucket.name = 'lab-output', request.permission = 'OBJECT_CREATE'}
~~~

Verb `manage` là mức gom quyền có chứa `OBJECT_CREATE`, nhưng condition chỉ cho phép permission đã chọn trong bucket được chỉ định. Không đọc từ tên verb rồi kết luận statement này cho phép mọi thao tác quản lý object.

Mẫu phục vụ việc ghi một object mới theo operation thích hợp. Ghi đè tên đã tồn tại và multipart upload có thể cần permission khác; ứng dụng phải được kiểm tra với cách upload thực tế. Không nới quyền sang xóa hoặc ghi đè chỉ vì thư viện đang dùng một quy trình upload khác dự kiến. [Oracle: Policy Builder Policy Templates](https://docs.oracle.com/en-us/iaas/Content/Identity/policiescommon/commonpolicies.htm)

Một kết quả thiết kế hợp lệ có thể là điều chỉnh quy trình xuất file để dùng tên mới và cơ chế upload phù hợp, thay vì cấp thêm quyền không nằm trong nhiệm vụ.

### 7.6. Workload đọc bucket bằng danh tính tài nguyên

Giả sử dynamic group `LabAppRuntime` đã chọn đúng những instance được phép chạy ứng dụng:

~~~text
Allow dynamic-group 'Default'/'LabAppRuntime' to read objects in compartment LabData where target.bucket.name = 'lab-input'
~~~

Ứng dụng sử dụng cơ chế xác thực danh tính tài nguyên tương ứng, chẳng hạn instance principal trên Compute khi đã được cấu hình phù hợp. Không cấp quyền đọc bucket cho tài khoản cá nhân của người triển khai rồi nhúng private key đó vào ứng dụng.

Nếu dynamic group chọn mọi instance trong `LabApp`, người có quyền tạo instance hoặc kiểm soát mã chạy trên những instance đó có thể tiếp cận quyền của workload. Phải xét cả quyền quản lý thành viên gián tiếp, khả năng triển khai mã và quyền trên tài nguyên đích.

## 8. Phân tích quyền phụ thuộc giữa các dịch vụ

Triển khai một instance không chỉ liên quan tới tài nguyên `instances`. Operation `LaunchInstance` còn có thể cần quyền sử dụng subnet, VNIC, NSG, image và những tài nguyên liên quan tùy cấu hình. [Oracle: Details for Verb + Resource-Type Combinations](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Details_for_Verb__ResourceType_Combinations.htm)

Trong cây ví dụ, instance nằm ở `LabApp`, subnet ở `LabNetwork`, còn dữ liệu đầu vào ở `LabData`. Đó là ba phạm vi quyền khác nhau:

~~~mermaid
flowchart LR
    G["Chủ thể triển khai"] --> A["Quyền vòng đời Compute tại LabApp"]
    G --> N["Quyền sử dụng mạng tại LabNetwork"]
    R["Danh tính workload sau triển khai"] --> D["Quyền đọc bucket tại LabData"]
    A --> VM["Instance ứng dụng"]
    N --> VM
    VM --> R
~~~

Sơ đồ tách chủ thể triển khai khỏi danh tính ứng dụng. Chúng có thể được vận hành bởi cùng đội nhưng không cần cùng một bộ quyền.

### 8.1. Cách phân tích một thao tác triển khai

1. Chọn operation và cấu hình triển khai cụ thể.
2. Tra bảng permission của operation đó.
3. Gắn từng tài nguyên phụ thuộc với compartment thực tế.
4. Xác định những permission phục vụ tạo, sử dụng và quan sát kết quả.
5. Tách quyền runtime của ứng dụng khỏi quyền triển khai.
6. Kiểm tra những permission mới phát sinh khi thêm tính năng như volume, khóa tùy chỉnh hoặc image riêng.

Một statement như sau có thể là **một phần** quyền sử dụng mạng, không phải bộ quyền triển khai hoàn chỉnh:

~~~text
Allow group 'Default'/'LabDeployers' to use subnets in compartment LabNetwork
Allow group 'Default'/'LabDeployers' to use network-security-groups in compartment LabNetwork
~~~

Không diễn giải hai dòng trên thành bảo đảm mọi cách launch instance đều thành công. Cũng không bổ sung `manage virtual-network-family` khi điều còn thiếu chỉ là một permission sử dụng phụ thuộc đã xác định.

### 8.2. Quyền quan sát của Console có thể khác luồng API tối thiểu

Console có thể gọi nhiều API để hiển thị dropdown, tab và thông tin liên quan. Một bộ quyền đủ cho operation trực tiếp chưa chắc làm toàn bộ giao diện hoạt động đầy đủ.

Cần quyết định user có thật sự cần quy trình Console đó không. Nếu có, bổ sung các quyền discovery đã được giải thích; nếu không, giữ luồng API hoặc tự động hóa phù hợp. Không xem mọi thông báo thiếu dữ liệu trên Console là lý do cấp quyền quản trị toàn dịch vụ.

## 9. Đánh giá quyền có hiệu lực và nguy cơ mở rộng

### 9.1. Statement hẹp không triệt tiêu quyền rộng từ nguồn khác

Khi xem các policy Allow trong bài này, phải cộng xét những nguồn cấp quyền liên quan. Một user có thể nhận permission qua nhiều group và nhiều policy. Viết thêm một statement giới hạn bucket không làm mất quyền rộng đã được một statement khác cho phép. [Oracle: IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm)

Ví dụ, An thuộc `LabInputReaders`, đồng thời thuộc một group đã được quản lý toàn `object-family` ở `Labs`. Condition chỉ đọc `lab-input` không chứng minh An mất quyền ở những bucket khác.

Do đó, rà soát phải bao gồm:

- Tất cả membership của user và các vai trò quản trị liên quan.
- Policy áp dụng từ tenancy, compartment cha và compartment đích.
- Các statement không có điều kiện hoặc có phạm vi rộng hơn.
- Dynamic group và những cơ chế chọn thành viên workload.
- Những đường truy cập dữ liệu ngoài IAM policy đang kiểm tra.

### 9.2. Những quyền có thể làm thay đổi ranh giới

Một số quyền cần đánh giá theo khả năng mở rộng quyền thực tế:

| Năng lực | Vì sao cần xem xét riêng? |
| --- | --- |
| Sửa policy | Có thể thay đổi những permission được cấp trong phạm vi được quản lý |
| Sửa group membership | Có thể đưa thêm người vào bộ quyền hiện có |
| Sửa dynamic group hoặc tiêu chí thành viên | Có thể đưa thêm workload vào quyền runtime |
| Tạo hoặc kiểm soát instance có quyền runtime | Có thể làm mã khác sử dụng danh tính workload |
| Sửa tag được dùng để cấp quyền | Có thể thay đổi việc tài nguyên/chủ thể thỏa điều kiện |
| Đọc secret hoặc dữ liệu nhạy cảm | Có thể mở thêm đường truy cập ngoài tài nguyên đang xét |
| Tạo liên kết chia sẻ dữ liệu | Có thể mở một đường sử dụng dữ liệu khác với profile người dùng |

Không chỉ đánh giá “có quyền xóa không?”. Quyền thay đổi danh tính, mã thực thi, cấu hình mạng hoặc secret cũng có thể tạo ảnh hưởng lớn.

Nếu dùng tag-based access control, cần kiểm soát ai được gán hoặc thay tag liên quan. Không xây ranh giới dựa vào một thuộc tính mà người nhận quyền tự do sửa.

## 10. Kiểm chứng theo ma trận được phép và ngoài phạm vi

Đánh giá quyền phải có cả phép thử dương và phép thử ngoài phạm vi. Chỉ chạy một thao tác thành công không chứng minh bộ quyền đã tối thiểu.

| Vai trò | Phép thử được phép | Phép thử ngoài phạm vi |
| --- | --- | --- |
| `LabComputeViewers` | List/Get instance trong `LabApp` | Cập nhật cấu hình hoặc đọc instance ngoài phạm vi đã duyệt |
| `LabPowerOperators` | Power action đã được duyệt trên instance thử nghiệm | Quản lý mạng hoặc xóa instance |
| `LabInputReaders` | Đọc bucket/object `lab-input` | Đọc bucket khác hoặc thay cấu hình chia sẻ |
| `LabReportWriters` | Tạo object mới theo phương thức được duyệt | Đọc, ghi đè hoặc xóa object |
| `LabAppRuntime` | Đọc object đầu vào bằng danh tính workload | Truy cập bucket không được cấp |

Đây là kế hoạch kiểm tra. Những thao tác có thể ghi dữ liệu, gián đoạn hoặc xóa tài nguyên chỉ được thử trên đối tượng lab được phép và theo phương án đã duyệt; không dùng tài nguyên sản xuất để kiểm tra một kỳ vọng bị từ chối.

### 10.1. Xác định đúng chủ thể đang được thử

Với CLI, xác nhận profile và loại auth. Một terminal đang dùng credential quản trị sẽ làm sai kết quả dù người kiểm tra tin rằng đang thử group chỉ đọc.

Với workload, kiểm tra yêu cầu thực sự dùng instance principal hoặc cơ chế đã chọn, thay vì một API key còn sót trong cấu hình. Với Console, dùng phiên phù hợp để tránh nhầm tài khoản hoặc ngữ cảnh.

### 10.2. Tài nguyên phải tồn tại và đúng phạm vi

Một yêu cầu thất bại vì OCID sai hoặc tài nguyên không tồn tại không chứng minh IAM đã chặn quyền như thiết kế. Người quản trị cần xác nhận đối tượng thử trước khi đánh giá kết quả.

Tương tự, timeout, lỗi TLS hoặc lỗi DNS không phải bằng chứng policy từ chối. Ghi nhận đúng lớp phát sinh lỗi và chỉ kết luận khi có bằng chứng phù hợp.

### 10.3. Hồ sơ kiểm tra

Mỗi phép thử nên ghi:

- Danh tính và phương thức xác thực.
- Group hoặc dynamic group liên quan.
- Policy/statement được kỳ vọng cấp quyền.
- Operation, tài nguyên và compartment đích.
- Region nếu thao tác phụ thuộc region.
- Kết quả mong đợi và kết quả thực tế.
- Thời điểm và request ID khi có.

Không ghi private key, token hoặc secret vào hồ sơ. Nếu chưa đủ điều kiện chạy một phép thử, đánh dấu chưa xác minh thay vì đánh dấu đạt theo suy đoán.

## 11. Bài thực hành: giới hạn đọc vào một bucket

### 11.1. Chuẩn bị

Cần một môi trường lab đã được cho phép với:

- Cây compartment hoặc phạm vi tương đương đã được xác nhận.
- Hai bucket thử nghiệm đã tồn tại trong `LabData`: `lab-input` và `lab-other`.
- Dữ liệu giả lập, không có thông tin nhạy cảm.
- Group `LabInputReaders` và user thử nghiệm không có quyền rộng từ nguồn khác.
- Tài khoản quản trị độc lập được phép áp dụng policy.
- OCI CLI đã kết nối bằng profile của user thử nghiệm.

Bài kiểm tra dưới đây chỉ đọc cấu hình và danh sách object, không yêu cầu tạo bucket hay triển khai Compute. Nếu thiếu đối tượng thử nghiệm, làm việc theo quy trình lab; không tự tạo tài nguyên tính phí để thay thế.

### 11.2. Áp dụng đúng bộ quyền

Người có thẩm quyền thêm hai statement ở mục 7.4 tại vị trí phù hợp của cây compartment. Xác minh membership và kiểm tra các nguồn quyền khác trước khi chạy thử.

Không gán user thử nghiệm vào nhóm quản trị để khắc phục một lỗi trong quá trình chuẩn bị.

### 11.3. Kiểm tra đường được phép

Ví dụ PowerShell, dùng profile API key riêng cho user thử nghiệm:

~~~powershell
$labNamespace = '<OBJECT_STORAGE_NAMESPACE>'
oci os bucket get --namespace-name $labNamespace --bucket-name 'lab-input' --profile LAB_READER --auth api_key
oci os object list --namespace-name $labNamespace --bucket-name 'lab-input' --profile LAB_READER --auth api_key --limit 5
~~~

Thay placeholder và tên profile bằng giá trị lab thật. Nếu dùng session token, chọn profile phù hợp và `--auth security_token`.

Kết quả mong đợi là lấy được thông tin bucket chỉ định và liệt kê object trong bucket đó. Danh sách trống vẫn có thể là kết quả hợp lệ nếu bucket chưa có object; không nhầm nó với lỗi quyền.

### 11.4. Kiểm tra bucket ngoài phạm vi

Sau khi người quản trị xác nhận `lab-other` tồn tại:

~~~powershell
oci os bucket get --namespace-name $labNamespace --bucket-name 'lab-other' --profile LAB_READER --auth api_key
~~~

Với bộ quyền đã mô tả và không có nguồn cấp bổ sung, yêu cầu này không được phép. Dịch vụ có thể trả lỗi không được ủy quyền hoặc không tìm thấy; đối chiếu kết quả với sự tồn tại đã được quản trị viên xác nhận.

Nếu yêu cầu thành công, tìm nguồn quyền rộng hơn hoặc credential thực tế đang được dùng. Không kết luận condition bị bỏ qua trước khi loại trừ những nguồn đó.

### 11.5. Thu hồi và kiểm tra lại

Gỡ user khỏi group thử nghiệm theo quy trình. Đọc lại membership, rồi kiểm tra yêu cầu trước đó được phép sau khi thay đổi đã được áp dụng trong ngữ cảnh xác thực phù hợp.

Không cam kết một số giây cố định cho mọi thay đổi IAM. Nếu hết thời gian chờ theo runbook mà quyền vẫn còn, điều tra policy, group, phiên và danh tính thực tế.

Cuối bài, lưu bằng chứng cần thiết và dọn những đối tượng thuộc riêng bài tập theo thẩm quyền. Không xóa bucket dùng chung hoặc dữ liệu của bài khác.

## 12. Vận hành và thu hẹp quyền theo thời gian

Một bộ quyền phù hợp lúc triển khai có thể trở nên dư thừa khi công việc thay đổi. Cần đưa policy vào vòng đời quản trị:

1. **Yêu cầu:** nêu nhiệm vụ, phạm vi và thời hạn.
2. **Thiết kế:** lập ma trận operation–permission–resource–compartment.
3. **Phê duyệt:** xác nhận người chịu trách nhiệm tài nguyên và rủi ro.
4. **Áp dụng:** thay đổi membership hoặc policy theo cách có dấu vết.
5. **Kiểm tra:** thực hiện phép thử được phép và ngoài phạm vi.
6. **Theo dõi:** quan sát hoạt động và thay đổi cấu hình liên quan.
7. **Rà soát:** gỡ quyền khi hết nhiệm vụ hoặc hết thời hạn.

Với tự động hóa, có thể quản lý policy như mã, kiểm tra thay đổi và giữ khả năng quay lại phiên bản đã biết. Quyền triển khai tự động cũng phải giới hạn; một pipeline có thể sửa mọi policy không trở nên ít rủi ro chỉ vì nó là pipeline.

Nhật ký sử dụng giúp phát hiện quyền dư nhưng không phải bằng chứng duy nhất. Một permission chưa được dùng gần đây có thể phục vụ khôi phục sự cố; cần xem lại mục đích và người phê duyệt trước khi loại bỏ.

Quyền tạm thời nên có cơ chế hết hạn hoặc công việc thu hồi được theo dõi tại hệ thống quản trị. Không giả định việc đặt chữ “temporary” trong tên group sẽ tự làm quyền hết hiệu lực.

## 13. Liên hệ với chi phí và tính sẵn sàng

Thiết kế quyền tối thiểu giúp giảm phạm vi ảnh hưởng khi thao tác sai hoặc credential bị lộ:

- Quyền tạo tài nguyên đúng phạm vi hạn chế việc triển khai ngoài kế hoạch, nhưng vẫn cần kiểm soát chi phí và hạn mức phù hợp.
- Quyền power action có thể làm gián đoạn dịch vụ dù không cho phép xóa instance.
- Quyền xóa backup hoặc thay khóa mã hóa có thể ảnh hưởng khả năng phục hồi.
- Quyền sửa mạng có thể làm mất kết nối hoặc mở thêm đường truy cập dữ liệu.
- Quyền đọc secret, wallet hoặc dữ liệu có thể tạo tác động vượt ngoài phần tài nguyên hiện trên Console.

Ngược lại, thu hồi quá mức mà không xét quyền phụ thuộc có thể làm pipeline ngừng chạy, ứng dụng không đọc được dữ liệu hoặc người trực mất khả năng xử lý sự cố. Cần kiểm thử nhiệm vụ hợp lệ và chuẩn bị đường quản trị khẩn cấp được kiểm soát.

Mục tiêu là bộ quyền **đủ cho nhiệm vụ đã duyệt và có thể chứng minh giới hạn**, được rà soát theo cấu trúc compartment, từng nhóm tài nguyên dịch vụ và danh tính thực sự sử dụng. Khi giải thích được vì sao từng permission tồn tại, đội vận hành sẽ dễ duy trì, điều tra và thu hồi quyền hơn khi hạ tầng OCI thay đổi.
