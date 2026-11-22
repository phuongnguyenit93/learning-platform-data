# Cú pháp IAM policy với subject, verb, resource và location

## Mục tiêu và phạm vi

Một IAM policy trong Oracle Cloud Infrastructure (OCI) trả lời câu hỏi: **chủ thể nào được thực hiện loại thao tác nào, trên loại tài nguyên nào, trong phạm vi nào?** Đọc đúng bốn phần này giúp bạn cấp quyền cho lab VCN, Compute, lưu trữ và cơ sở dữ liệu mà không mặc định trao toàn quyền tenancy.

Bài thuộc chương **Danh tính và phân quyền IAM**. Sau bài học, bạn có thể:

- Phân tích một policy statement thành subject, verb, resource-type và location.
- Viết subject đúng identity domain hoặc OCID.
- Tra quyền API cụ thể thay vì suy đoán chỉ từ tên verb.
- Phân biệt phạm vi được cấp quyền với nơi gắn policy và ảnh hưởng của kế thừa.
- Thêm điều kiện đơn giản, kiểm tra cả quyền được phép lẫn quyền ngoài phạm vi.

Các ví dụ dùng tên nhóm, compartment và bucket giả định. Chúng minh họa cú pháp, cần thay bằng tài nguyên và định danh thực tế trước khi áp dụng. Tài liệu Oracle được đối chiếu ngày **20/11/2026**; quyền chi tiết của dịch vụ cần tra lại khi triển khai.

## 1. Khung cú pháp và cách đọc một statement

Cú pháp cơ bản:

```text
Allow <subject> to <verb> <resource-type> in <location>
```

Có thể giới hạn thêm bằng điều kiện:

```text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
```

Một policy có thể chứa nhiều statement. Trong bài, luôn ghi rõ location; tài liệu chi tiết của Oracle xác định đây là thành phần bắt buộc. Tham khảo [IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm) và [Locations](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/location.htm).

Ví dụ xuyên suốt:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

Giả định `Lab` là compartment con trực tiếp của root và policy được tạo ở root.

| Phần | Giá trị trong ví dụ | Cách diễn giải |
| --- | --- | --- |
| Subject | `group 'Default'/'LabVmReaders'` | Nhóm `LabVmReaders` trong identity domain `Default` |
| Verb | `read` | Mức quyền đọc theo định nghĩa của resource-type |
| Resource-type | `instances` | Compute instances, không phải mọi tài nguyên của Compute |
| Location | `compartment Lab` | Phạm vi compartment `Lab`, cùng ảnh hưởng kế thừa xuống dưới |

Đọc thành một câu: “Cho nhóm LabVmReaders của domain Default quyền read đối với instances trong Lab.” Sau đó mới tra `read instances` bao phủ permission và API nào.

Tên policy, chẳng hạn `lab-vm-readers-policy`, phục vụ quản lý đối tượng policy. Tên đó không thay thế các statement bên trong. Một policy tên “ReadOnly” vẫn có thể chứa statement cấp `manage` nếu người viết cấu hình như vậy.

### 1.1. IAM policy cấp quyền, không phải policy đăng nhập

Trong phạm vi cú pháp đang học, statement bắt đầu bằng `Allow`; đây là cơ chế cấp quyền truy cập tài nguyên. Nó khác sign-on policy dùng để yêu cầu MFA khi đăng nhập. Oracle nêu policy chỉ cấp quyền, không có statement `Deny` trong [IAM Policies Overview](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Basics.htm).

Người dùng có thể đã xác thực bằng MFA nhưng vẫn bị từ chối API do thiếu quyền. Ngược lại, có quyền IAM không làm cho mật khẩu hoặc thiết bị MFA hoạt động trở lại khi đường đăng nhập gặp lỗi.

## 2. Subject: ai nhận quyền?

### 2.1. Nhóm trong identity domain

Với người dùng, cách cấp quyền thông dụng là cấp cho nhóm rồi quản lý thành viên nhóm. Khi dùng tên, chỉ rõ identity domain:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

Nếu nhóm ở domain khác:

```text
Allow group 'Engineering'/'LabVmReaders' to read instances in compartment Lab
```

Hai nhóm cùng tên trong hai domain là hai subject khác nhau. Đừng chỉ kiểm tra tên nhóm mà bỏ qua domain của người dùng và nhóm.

Có thể bỏ phần domain với nhóm thuộc Default; khi đó policy diễn giải theo Default domain. Viết đầy đủ giúp ví dụ và cấu hình dễ đọc hơn. Tham khảo [Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm).

Đối với tên có khoảng trắng, giữ đúng cách đặt dấu nháy đơn theo cú pháp, ví dụ:

```text
Allow group 'Engineering'/'Lab VM Readers' to read instances in compartment Lab
```

### 2.2. Dùng OCID của nhóm

Có thể chỉ định nhóm bằng OCID:

```text
Allow group id <GROUP_OCID> to read instances in compartment Lab
```

`<GROUP_OCID>` là chỗ giữ chỗ, cần thay bằng OCID nhóm thực tế, gồm cả việc bỏ dấu `<` và `>`. Không thay bằng OCID người dùng hoặc identity domain. Cú pháp theo OCID cũng được nêu tại [Subjects](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/subject.htm).

Dùng tên thuận tiện cho việc đọc; dùng OCID giúp tham chiếu rõ một đối tượng. Với cả hai cách, vẫn cần ghi nhận nhóm đó thuộc môi trường nào và ai được phép thay đổi thành viên.

### 2.3. Dynamic group và service principal

Subject còn có thể là dynamic group hoặc một dịch vụ OCI. Dynamic group dùng cho những tài nguyên đáp ứng matching rule; việc tài nguyên thuộc nhóm và việc policy cấp quyền cho nhóm là hai cấu hình riêng. Service principal dùng trong các tình huống dịch vụ cần thao tác thay mặt bạn.

Ví dụ khung cú pháp cho dynamic group:

```text
Allow dynamic-group 'Default'/'LabInstances' to read objects in compartment Lab
```

Dòng này minh họa subject của tài nguyên chạy workload, không phải nhóm người dùng. Nó cũng cấp quyền đọc objects trên phạm vi Lab tương ứng, nên chưa giới hạn vào một bucket riêng.

Không đổi `group` thành `dynamic-group` chỉ để sửa một lỗi đăng nhập của người dùng. Khi chuyển sang tự động hóa, phải xác định loại principal mà SDK, CLI hoặc dịch vụ thực sự dùng để gọi API.

Các subject bao quát như `any-user` hoặc `any-group` có phạm vi khác nhóm lab cụ thể. Chỉ sử dụng khi đã hiểu chủ thể được bao phủ và điều kiện giới hạn cần thiết; không dùng làm lối tắt để một API hết báo thiếu quyền.

## 3. Verb: mức quyền nào được cấp?

Bốn verb thông dụng theo mức tăng dần là:

```text
inspect → read → use → manage
```

| Verb | Ý nghĩa tổng quát |
| --- | --- |
| `inspect` | Khả năng quan sát hoặc liệt kê theo resource-type; có ngoại lệ về thông tin được trả về |
| `read` | Bao gồm mức inspect và khả năng đọc bổ sung theo loại tài nguyên |
| `use` | Bao gồm mức read, thêm thao tác với tài nguyên hiện có theo định nghĩa dịch vụ |
| `manage` | Bao gồm toàn bộ permission của resource-type trong phạm vi statement |

Đây là định hướng, không phải bảng CRUD áp dụng tuyệt đối cho mọi dịch vụ. `use` thường không gồm tạo/xóa; một số thao tác cập nhật cũng yêu cầu `manage`. Tham khảo [Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Verbs.htm).

### 3.1. Verb chỉ có nghĩa cụ thể khi đi cùng resource-type

Mỗi tổ hợp verb và resource-type ánh xạ đến tập **permission** do Oracle định nghĩa. API operation yêu cầu một hoặc nhiều permission. Vì vậy, cần tra theo chuỗi:

```text
Nhu cầu của người dùng
    → API operation
    → permission cần thiết
    → verb + resource-type cấp permission đó
    → location và conditions phù hợp
```

Ví dụ, `inspect volumes` và `read volumes` không nhất thiết khác nhau về permission; Oracle chỉ ra trường hợp không có quyền tăng thêm giữa hai mức này trong [Advanced Policy Features — Relation to Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policyadvancedfeatures.htm).

Một điểm đáng chú ý với ví dụ Compute: theo bảng hiện tại, `ListInstances` và `GetInstance` dùng `INSTANCE_READ`, được bao phủ bởi `read instances`. Không mặc định tên API có chữ “List” là luôn chỉ cần `inspect`. Tham khảo [Permissions Required for Each API Operation](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm).

### 3.2. Quyền quan sát vẫn có thể chứa thông tin đáng chú ý

`inspect` không bảo đảm mọi kết quả chỉ có tên và OCID. Ví dụ, inspect policy có thể cho thấy nội dung policy; inspect tài nguyên mạng có thể bao gồm route hoặc security rule. Các ngoại lệ được Oracle trình bày tại [Verbs](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Verbs.htm).

Tương tự, quyền đọc thông tin instance không đồng nghĩa chỉ thấy một biểu tượng VM trên Console. Khi quyết định cấp quyền, xem dữ liệu mà API trả về và tránh đặt bí mật vào metadata để rồi mặc định người có quyền đọc không thể thấy chúng.

### 3.3. Chọn quyền theo tác vụ, không theo chức danh

Nhu cầu “đọc cấu hình VM” dẫn đến kiểm tra API đọc. Nhu cầu “quản trị hệ thống” cần được tách thành các tác vụ cụ thể: đọc, cập nhật, vận hành, tạo hoặc xóa tài nguyên nào.

Không chọn `manage` chỉ vì người dùng thuộc đội kỹ thuật. Với một lab chỉ quan sát, cấp quyền tạo/xóa sẽ làm rộng cả khả năng tác động dữ liệu lẫn rủi ro chi phí mà bài học chưa cần.

## 4. Resource: loại tài nguyên nào?

Tên resource-type thuộc ngôn ngữ policy, không phải tên tùy ý của dịch vụ trên giao diện.

| Ví dụ resource-type | Phạm vi diễn giải |
| --- | --- |
| `instances` | Compute instances |
| `vcns` | Virtual Cloud Networks |
| `volumes` | Block volumes theo định nghĩa dịch vụ |
| `buckets` | Bucket của Object Storage |
| `objects` | Object bên trong bucket |

Một VM tên `java-lab-01` không phải resource-type. Tên “Compute” trên menu cũng không tự trở thành từ khóa `compute` trong policy. Tra resource-type được Oracle công bố cho dịch vụ.

### 4.1. Resource-type riêng và resource family

Family gom các resource-type thường được quản lý cùng nhau, chẳng hạn `virtual-network-family`, `volume-family` và `object-family`. Chọn family giúp giảm số statement nhưng thường mở rộng các loại tài nguyên được bao phủ. Xem [Resources](https://docs.oracle.com/en-us/iaas/Content/Identity/policiesgs/policies_topic-ResourceTypes.htm).

So sánh:

```text
Allow group 'Default'/'LabNetworkReaders' to read vcns in compartment Lab
```

```text
Allow group 'Default'/'LabNetworkReaders' to read virtual-network-family in compartment Lab
```

Hai statement không tương đương về phạm vi resource. Dòng thứ hai bao phủ thêm các thành phần mạng trong family; không nên dùng thay dòng thứ nhất mà chưa rà lại nhu cầu.

`instance-family` cũng có các permission bổ sung được Oracle mô tả riêng. Không suy ra mọi family chỉ là danh sách tên nhìn thấy trên Console. Khi dịch vụ bổ sung resource-type, định nghĩa family còn có thể được mở rộng. Tham khảo [Details for the Core Services](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm) và [Resources](https://docs.oracle.com/en-us/iaas/Content/Identity/policiesgs/policies_topic-ResourceTypes.htm).

### 4.2. `all-resources` là phạm vi lớn

```text
Allow group 'Default'/'LabAdmins' to manage all-resources in compartment Lab
```

Statement này cấp quyền rộng trong phạm vi Lab cùng ảnh hưởng kế thừa, không chỉ cho VM của một bài thực hành. Chỉ dùng khi nhu cầu thật sự là quản trị toàn bộ phạm vi đó và đã kiểm soát người được vào nhóm.

Việc đổi `compartment Lab` thành `tenancy` làm phạm vi tăng lên toàn tenancy đối với các resource được cấp. Đây không phải cách sửa lỗi thiếu quyền thông thường.

## 5. Location: quyền có hiệu lực trong phạm vi nào?

Location thông dụng là `tenancy`, `compartment <tên>` hoặc `compartment id <OCID>`. Khi dùng tên compartment, cách phân giải phụ thuộc nơi tạo policy; đường dẫn compartment lồng nhau dùng dấu hai chấm. Region và Availability Domain không phải giá trị thay trực tiếp cho location; muốn giới hạn theo chúng, dùng condition phù hợp. Tham khảo [Locations](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/location.htm).

Giả sử có cây compartment:

```text
Root tenancy
├── Lab
│   ├── ComputeLab
│   └── NetworkLab
└── Production
```

### 5.1. Phạm vi một nhánh compartment

Với policy đặt ở root:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

Quyền này áp dụng cho instances trong Lab và nhánh con theo cơ chế kế thừa, nên cần tính cả ComputeLab và NetworkLab nếu chúng có instances. Không suy ra người dùng cũng được đọc instances trong Production.

Nếu chỉ cần ComputeLab, viết rõ đường dẫn từ vị trí tạo policy:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab:ComputeLab
```

Có thể tham chiếu compartment bằng OCID:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment id <COMPUTE_LAB_COMPARTMENT_OCID>
```

Chuỗi giữ chỗ phải được thay bằng OCID **compartment** thực tế. Không dùng OCID instance hoặc identity domain ở vị trí này.

### 5.2. Scope của statement khác nơi gắn policy

**Policy attachment** là nơi lưu/gắn đối tượng policy trong hệ thống compartment. Nó ảnh hưởng đến phạm vi quản trị policy và ai có thể sửa hoặc xóa policy đó. Oracle trình bày cơ chế này tại [Policy Attachment](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Attachment.htm).

Ví dụ một policy đặt ở root vẫn có thể chứa statement chỉ cấp `read instances in compartment Lab`. Việc đối tượng policy nằm ở root không tự biến location của statement thành `tenancy`.

Ngược lại, đặt policy ở một compartment con không tự cho phép quản trị viên compartment đó cấp quyền lên mọi nhánh khác. Khi tổ chức phân quyền quản trị policy, phải xét vị trí gắn và phạm vi có thể tham chiếu.

Với cây ví dụ, nếu tạo policy tại Lab để tham chiếu compartment con trực tiếp ComputeLab, location theo tên có thể là:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment ComputeLab
```

Dòng này phải được đọc cùng thông tin “policy được tạo tại Lab”. Đưa nó lên root mà không rà lại location có thể làm tên compartment không còn được phân giải như dự kiến.

### 5.3. Kế thừa từ cha xuống con

Compartments nhận quyền từ policy có hiệu lực ở cấp cha. Nếu cấp quyền quản lý tài nguyên trong Lab, quyền đó tiếp tục có hiệu lực xuống các compartment con thuộc phạm vi tương ứng. Xem [Policy Inheritance](https://docs.oracle.com/en-us/iaas/Content/Identity/policieshow/Policy_Inheritance.htm).

Ví dụ học tập:

```text
Allow group 'Default'/'LabNetworkAdmins' to manage virtual-network-family in compartment Lab
```

Nếu muốn tạo một khu vực chỉ quan sát trong nhánh Lab, thêm statement `read` tại khu vực con không làm mất quyền `manage` mà cùng người dùng đã nhận từ cha. Cần thiết kế lại nhóm hoặc phạm vi của grant rộng hơn.

Sự kế thừa giúp quản trị nhất quán, nhưng cũng là lý do phải rà các policy ở root và tổ tiên khi một người có nhiều quyền hơn dự kiến.

## 6. Conditions: thu hẹp grant khi bốn phần cơ bản chưa đủ

`where` bổ sung điều kiện mà request phải đáp ứng để nhận quyền từ statement đó. Ví dụ, cho nhóm đọc object trong bucket `lab-input`:

```text
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where target.bucket.name = 'lab-input'
```

Giả định bucket thuộc Lab và biến `target.bucket.name` được hỗ trợ cho thao tác cần thực hiện. Oracle mô tả biến này tại [Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

### 6.1. Một điều kiện, AND và OR

Khung cú pháp:

```text
where <variable> = '<value>'
where all {<condition-1>, <condition-2>}
where any {<condition-1>, <condition-2>}
```

- `all` yêu cầu mọi điều kiện trong tập đều đúng.
- `any` yêu cầu ít nhất một điều kiện trong tập đúng.
- Giá trị chuỗi được viết trong dấu nháy đơn theo cú pháp.

Ví dụ cho phép đọc object trong một trong hai bucket:

```text
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where any {target.bucket.name = 'lab-input', target.bucket.name = 'lab-reference'}
```

Tham khảo [Conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/conditions.htm). Không dùng cú pháp SQL như `AND`, `OR`, hoặc tự thêm JSON vào một policy statement thuần văn bản.

### 6.2. Biến điều kiện phải phù hợp API

Không phải request nào cũng có mọi thuộc tính target. Nếu biến không áp dụng cho request, điều kiện không thể cấp quyền cho request đó. Chẳng hạn, một điều kiện nhắm một target cụ thể có thể không phù hợp API liệt kê nhiều target. Xem [Advanced Policy Features — Variables that Aren't Applicable to a Request](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policyadvancedfeatures.htm).

Vì vậy, khi một thao tác liệt kê bị từ chối nhưng một thao tác đọc tài nguyên đã biết lại hoạt động, hãy tra biến được hỗ trợ và permission của từng API. Đừng vội bỏ mọi điều kiện hoặc đổi sang `manage all-resources`.

Một lưu ý quan trọng: **so khớp condition không phân biệt hoa thường**, kể cả khi tên tài nguyên của dịch vụ có phân biệt. Điều kiện với `BucketA` có thể khớp cả `bucketA`. Oracle nêu ví dụ này tại [Conditions](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/conditions.htm). Không dựa vào khác biệt chữ hoa/thường để thiết kế ranh giới truy cập giữa hai bucket.

### 6.3. Condition giới hạn statement, không thu hồi grant khác

Giả sử cùng một người dùng nhận được:

```text
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where target.bucket.name = 'lab-input'
```

và từ một nhóm khác:

```text
Allow group 'Default'/'LabStorageAdmins' to manage object-family in compartment Lab
```

Nếu người đó thuộc cả hai nhóm, statement đầu không giới hạn quyền rộng mà statement thứ hai đã cấp. Muốn chỉ đọc bucket mục tiêu, phải xử lý nguồn grant rộng hơn hoặc membership tương ứng.

Đây là lý do việc kiểm tra quyền cần xem toàn bộ nhóm và grant phù hợp với principal. Sắp xếp statement hẹp ở trước statement rộng không tạo một rule từ chối.

## 7. Một tác vụ có thể cần nhiều permission

API không nhất thiết tương ứng một resource-type. Ví dụ, tạo VM còn liên quan image và mạng; gắn volume liên quan volume, attachment và instance. Các permission cần thiết được liệt kê theo API tại [Permissions Required for Each API Operation](https://docs.oracle.com/en-us/iaas/Content/Identity/policyreference/corepolicyreference_topic-Permissions_Required_for_Each_API_Operation.htm).

Một statement như:

```text
Allow group 'Default'/'LabVmBuilders' to manage instances in compartment Lab
```

không đủ để kết luận nhóm đã có toàn bộ quyền cho một quy trình tạo VM qua Console. Người dùng còn có thể cần đọc tài nguyên phục vụ lựa chọn trên giao diện và thao tác với những thành phần phụ thuộc.

Cách phân tích nên đi theo từng thao tác thực tế:

1. Xác định API bị từ chối, không chỉ tên nút trên Console.
2. Tra permission mà API yêu cầu.
3. Tra tổ hợp verb/resource-type cung cấp permission đó.
4. Xác định compartment của từng tài nguyên liên quan.
5. Kiểm tra principal và conditions trên mỗi grant cần thiết.

Ví dụ một VM được tạo trong Lab nhưng subnet nằm ở compartment dùng chung Networking. Chỉ kiểm tra quyền trên instances ở Lab sẽ bỏ sót phần truy cập mạng trong Networking.

Các grant cần thiết có thể nằm trong nhiều policy hoặc đến từ nhiều nhóm của cùng người dùng, như Oracle giải thích tại [Resources — Access That Requires Several Resource Types](https://docs.oracle.com/en-us/iaas/Content/Identity/policiesgs/policies_topic-ResourceTypes.htm). Việc một statement được lưu thành công chỉ chứng minh cú pháp được chấp nhận; chưa chứng minh toàn bộ quy trình hoạt động.

## 8. Ba ví dụ áp dụng có giới hạn rõ ràng

Trong cả ba ví dụ dưới, giả định policy ở root, các compartment được nêu là con trực tiếp của root, nhóm đã tồn tại và người thử không nhận thêm quyền rộng từ nơi khác.

### 8.1. Đọc thông tin VM của lab

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

Mục tiêu là đọc thông tin Compute instance. Nó không cấp quyền vận hành VM, đăng nhập SSH hoặc đọc mọi dịch vụ trong Lab.

Theo bảng Compute hiện tại, quyền `read instances` bao gồm `ListInstances` và `GetInstance`. Các bước như xem IP qua VNIC hoặc xem tài nguyên liên quan có thể cần permission riêng. Tham khảo [Details for the Core Services](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/corepolicyreference.htm).

### 8.2. Liệt kê bucket của Lab, đọc object ở một bucket

```text
Allow group 'Default'/'LabObjectReaders' to inspect buckets in compartment Lab
Allow group 'Default'/'LabObjectReaders' to read objects in compartment Lab where target.bucket.name = 'lab-input'
```

Hai dòng tách việc xem danh sách bucket khỏi việc đọc object. Theo bảng quyền dịch vụ, `inspect buckets` bao phủ `ListBuckets`, còn `read objects` bao gồm quyền đọc object qua `GetObject`. Tham khảo [Details for Object Storage and Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

Đây là ví dụ cho các API được nêu, chưa phải cam kết toàn bộ màn hình Object Storage đều hoạt động. Nếu Console cần `GetBucket` hoặc API khác, tra quyền bổ sung và chỉ cấp khi cần. Không mở rộng từ đọc một bucket thành quản trị toàn bộ Object Storage để làm một trang hết báo lỗi.

### 8.3. Quản trị mạng trong compartment chuyên dụng

```text
Allow group 'Default'/'LabNetworkAdmins' to manage virtual-network-family in compartment Networking
```

Nhóm nhận quyền rộng trên family mạng trong Networking. Ví dụ phù hợp để thảo luận phân công cho đội mạng của lab; không phải mức quyền mặc định dành cho người chỉ triển khai ứng dụng Java.

Một người dùng group này có thể thay đổi thành phần ảnh hưởng kết nối và an toàn mạng trong phạm vi được cấp. Khi bài thực hành chỉ cần dùng subnet có sẵn, cần phân tích quyền sử dụng tài nguyên đó thay vì trao luôn quyền quản trị cả family.

## 9. Quy trình viết policy từ một yêu cầu thực tế

Giả sử đề bài là: “Nhóm hỗ trợ được xem thông tin VM trong Lab, không được quản lý tài nguyên Production.”

### Bước 1 — Xác định principal và tác vụ

Ghi rõ nhóm nhận quyền, domain của nhóm, người sẽ thử và API cần gọi. Cụm từ “được xem” cần được cụ thể hóa thành tác vụ như liệt kê instances hoặc lấy chi tiết một instance đã biết.

### Bước 2 — Chốt resource và phạm vi

Chọn `instances` nếu mục tiêu chỉ là thông tin Compute instance. Xác định Lab có compartment con hay không và việc cấp quyền xuống các compartment đó có phù hợp yêu cầu không.

Ghi nhận nơi đặt policy. Với ví dụ đặt ở root và Lab là con trực tiếp, statement là:

```text
Allow group 'Default'/'LabVmReaders' to read instances in compartment Lab
```

Không thêm quyền vào Production chỉ vì người dùng thấy tên compartment đó trên Console. Khả năng nhìn thấy cấu trúc compartment và khả năng đọc tài nguyên bên trong là hai phạm vi cần phân tích riêng.

### Bước 3 — Rà các nguồn quyền khác

Trước khi thử, kiểm tra người dùng không thuộc `Administrators` hoặc nhóm khác cấp quyền rộng hơn mục tiêu. Rà những policy có hiệu lực từ root và compartment cha.

Một người có quyền quản trị sẵn gần như luôn thực hiện được thao tác đọc trong ví dụ. Dùng danh tính đó để thử sẽ không chứng minh policy mới đã cấp đúng quyền hoặc giới hạn đúng phạm vi.

### Bước 4 — Viết dự kiến cho cả trường hợp được phép và ngoài phạm vi

| Tác vụ | Dự kiến khi người dùng chỉ nhận bộ quyền đọc instances ở Lab |
| --- | --- |
| `ListInstances` trong Lab | Được phép đối với trường hợp instance thông thường đã xác định |
| `GetInstance` cho VM thuộc Lab | Được phép |
| Đọc instance trong nhánh con của Lab | Cần tính ảnh hưởng kế thừa; grant ở Lab có thể áp dụng xuống dưới |
| Đọc instance trong Production | Bộ policy này không cấp quyền đó |
| Đọc bucket hoặc object chỉ vì chúng cũng thuộc Lab | Không được cấp bởi resource-type `instances` |
| Tạo, sửa hoặc xóa VM | Không được cấp bởi grant `read instances` |

Bảng này là dự kiến của mô hình lab, không bảo đảm kết quả nếu danh tính còn nhận quyền từ các nguồn khác. Với API có điều kiện riêng, chẳng hạn instance trong compute cluster, cần kiểm tra permission bổ sung theo tài liệu dịch vụ.

### Bước 5 — Chỉ bổ sung quyền gắn với một nguyên nhân đã xác định

Nếu API mong muốn bị từ chối, xác định permission còn thiếu và compartment chứa tài nguyên liên quan rồi mới chỉnh policy. Mỗi lần thay đổi nên trả lời được “thêm dòng này để cho phép thao tác nào”.

Không đổi đồng thời subject, verb, resource và location chỉ để thử vận may; bạn sẽ khó biết thay đổi nào giải quyết vấn đề và quyền nào đã bị mở rộng ngoài nhu cầu.

## 10. Thực hành kiểm tra bằng các API chỉ đọc

### 10.1. Chuẩn bị môi trường kiểm tra

Dùng tenancy lab mà bạn được phép quản lý, một nhóm đọc và một người dùng thử không có quyền quản trị rộng. Chuẩn bị sẵn:

- Identity domain và tên nhóm chính xác.
- Compartment Lab cùng một instance lab đã tồn tại, nếu cần thử lấy chi tiết.
- Region chứa instance và OCID compartment/instance thực tế.
- Profile OCI CLI của đúng người dùng thử, đã cấu hình thông tin xác thực phù hợp.
- Ghi nhận policy được đặt ở đâu, statement đã áp dụng và quyền khác của người dùng.

Không cần tạo thêm VM chỉ để kiểm tra cú pháp policy trong bài này. Nếu Lab chưa có instance, một phép liệt kê thành công với danh sách rỗng có thể cho thấy API đã thực hiện được, nhưng chưa kiểm chứng quyền đọc một tài nguyên cụ thể.

### 10.2. Liệt kê instances trong Lab

Ví dụ PowerShell, với các giá trị giữ chỗ phải thay trước khi chạy:

```powershell
$profileName = 'LAB_VM_READER'
$regionId = 'THAY_BANG_REGION_ID'
$labCompartmentOcid = 'THAY_BANG_OCID_COMPARTMENT_LAB'

oci compute instance list --profile $profileName --region $regionId --compartment-id $labCompartmentOcid --all
```

Kiểm tra kết quả, mã lỗi nếu có và đúng compartment đã truy vấn. `--all` lấy các trang kết quả, không mở rộng quyền IAM hoặc phạm vi sang mọi compartment. Tham khảo [OCI CLI — instance list](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/list.html).

### 10.3. Đọc một instance đã biết

```powershell
$instanceOcid = 'THAY_BANG_OCID_INSTANCE_TRONG_LAB'

oci compute instance get --profile $profileName --region $regionId --instance-id $instanceOcid
```

Lệnh lấy thông tin instance, không khởi động hoặc dừng máy. Tham khảo [OCI CLI — instance get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/compute/instance/get.html).

Nếu muốn hiển thị địa chỉ IP, có thể phải thực hiện thêm các API VNIC và có quyền tương ứng. Không coi việc đọc thông tin instance thành công là bằng chứng tất cả thao tác trên trang chi tiết VM đều đã được phép.

### 10.4. Kiểm tra ngoài phạm vi bằng thao tác đọc

Dùng cùng danh tính thử và một tài nguyên thử nghiệm ngoài Lab đã được người quản lý chuẩn bị. Thực hiện truy vấn chỉ đọc để kiểm tra bộ quyền có giới hạn như dự kiến không; không dùng thao tác xóa hoặc tạo tài nguyên để kiểm tra một grant chỉ đọc.

Nếu truy cập ngoài phạm vi vẫn thành công, rà membership, policy tổ tiên và các grant khác trước khi sửa statement đang học. Có thể statement hẹp đã đúng nhưng người dùng nhận quyền rộng từ một nhóm khác.

Nếu request thất bại, kiểm tra đúng region, OCID và sự tồn tại của tài nguyên cùng người quản lý môi trường. Một request dùng sai định danh không chứng minh ranh giới phân quyền đã hoạt động đúng.

### 10.5. Ghi bằng chứng đủ để đối chiếu

Biểu mẫu gợi ý:

```text
Principal/profile dùng để thử:
Domain và nhóm cấp quyền:
Vị trí gắn policy:
Statement đã áp dụng:
API hoặc thao tác được thử:
Region, compartment và tài nguyên đích:
Kết quả mong đợi:
Kết quả thực tế:
Nguồn quyền khác đã rà:
Permission cần bổ sung, nếu có:
```

Không ghi private key, token hoặc nội dung cấu hình xác thực bí mật vào kết quả bài tập. Kết quả quan trọng là mối liên hệ giữa statement và hành vi thực tế của API.

## 11. Phân loại lỗi thường gặp

| Biểu hiện | Điều cần kiểm tra trước |
| --- | --- |
| Không lưu được statement | Từ khóa, vị trí `to`/`in`, dấu nháy, dấu ngoặc condition và resource-type hợp lệ |
| Nhóm tồn tại nhưng người dùng không có quyền | Đúng domain, đúng nhóm, membership và principal thực tế của phiên/CLI |
| Đọc được Lab nhưng không thấy trang phụ trên Console | API phụ thuộc và permission của resource-type liên quan |
| `manage instances` nhưng chưa tạo được VM | Image, subnet, VNIC, NSG hoặc thành phần liên quan theo API thực tế |
| Policy nằm ở root mà Production vẫn không đọc được | Location của statement có thể chỉ là Lab; attachment không tự cấp tenancy-wide |
| Người dùng vẫn quản lý được tài nguyên sau khi thêm rule đọc | Grant rộng khác, membership khác hoặc policy kế thừa |
| Condition hoạt động cho một API nhưng không cho API khác | Biến target có áp dụng cho request đó không và API cần permission nào |
| Tên compartment không được hiểu như dự kiến | Vị trí tạo policy, đường dẫn compartment, tên trùng hoặc OCID dùng sai loại |
| Lệnh đọc không trả tài nguyên | Region, compartment, bộ lọc, định danh và quyền; danh sách rỗng không đồng nghĩa chắc chắn thiếu quyền |

Một số lỗi ở ngoài IAM: quota, service limit, capacity, cấu hình mạng hoặc trạng thái tài nguyên. Đã cấp đúng permission không bảo đảm mọi thao tác triển khai đều thành công. Vì vậy, giữ nguyên thông tin lỗi cần thiết và phân loại trước khi mở rộng quyền.

## 12. Tiêu chí hoàn thành

Bạn hoàn thành bài khi có thể:

- Đọc một statement thành câu đầy đủ về chủ thể, mức quyền, loại tài nguyên và phạm vi.
- Viết subject đúng domain hoặc OCID, không nhầm người dùng với nhóm hay dynamic group.
- Tra ít nhất một API đến permission và tổ hợp verb/resource-type tương ứng.
- Giải thích được scope của statement, nơi gắn policy và ảnh hưởng kế thừa.
- Chỉ ra vì sao một condition hẹp không thu hồi grant rộng từ policy khác.
- Viết một policy đọc tài nguyên trong Lab, thử bằng danh tính ít quyền và đối chiếu trường hợp ngoài phạm vi.
- Ghi nhận giới hạn của phép thử và không dùng quyền quản trị toàn tenancy để che lỗi thiếu quyền cụ thể.

Khi đọc hoặc viết policy cho VCN, Compute, lưu trữ hay cơ sở dữ liệu Oracle ở các bài tiếp theo, hãy bắt đầu từ tác vụ cần thực hiện rồi xác định đủ bốn phần và permission liên quan. Cách làm này giúp quyền truy cập bám sát nhu cầu thực hành, đồng thời giữ phạm vi tác động và chi phí trong kiểm soát.
