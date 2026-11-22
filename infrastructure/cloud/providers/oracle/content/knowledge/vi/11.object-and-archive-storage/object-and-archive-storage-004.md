# Thiết kế IAM policy cho bucket và object

Trong Oracle Cloud Infrastructure (OCI), một ứng dụng có thể cần tải hóa đơn từ Object Storage nhưng không được xóa dữ liệu, đổi cấu hình bucket hay phát hành liên kết chia sẻ. Một tiến trình sao lưu cơ sở dữ liệu Oracle lại cần đưa dữ liệu lên bucket, trong khi nhóm vận hành chỉ cần xem cấu hình và theo dõi lỗi. Cấp cùng một quyền quản trị cho các chủ thể này sẽ làm mất ranh giới trách nhiệm.

Bài học thuộc chương **Object Storage và Archive Storage**, trong phạm vi module **CLOUD_PROVIDERS_ORACLE**. Ta kết nối kiến thức tenancy, compartment và IAM với tình huống Compute, lưu trữ và sao lưu dữ liệu: thiết kế quyền tối thiểu, dùng danh tính cho tự động hóa, quan sát truy cập và hạn chế những thao tác có thể gây mất dữ liệu hoặc phát sinh chi phí.

Sau bài học, bạn có thể:

- Chuyển yêu cầu nghiệp vụ thành principal, phạm vi tài nguyên và permission cụ thể.
- Tách quyền quản lý bucket khỏi quyền đọc, tạo, ghi đè và xóa object.
- Viết policy theo bucket hoặc prefix, đồng thời hiểu giới hạn của quyền liệt kê.
- Lập ma trận kiểm thử quyền cho người dùng và workload trước khi đưa policy vào vận hành.

## Mô hình phân quyền cần nắm

Một yêu cầu truy cập cần trả lời bốn câu hỏi:

| Câu hỏi | Thành phần trong thiết kế |
| --- | --- |
| Ai thực hiện? | Người dùng qua group; workload qua dynamic group hoặc cơ chế principal tương ứng |
| Thực hiện việc gì? | API operation và các permission mà operation yêu cầu |
| Trên dữ liệu nào? | Compartment chứa bucket, tên bucket, tên hoặc pattern của object |
| Với ràng buộc nào? | Điều kiện IAM và các cơ chế bảo vệ liên quan |

Đừng đồng nhất **xác thực** với **phân quyền**. API key hoặc instance principal giúp OCI nhận diện bên gọi. Policy quyết định danh tính đó được phép làm gì.

Cũng cần tách **đường mạng** khỏi **quyền dữ liệu**. Ví dụ, thiết kế cho Compute trong private subnet truy cập Object Storage qua Service Gateway vẫn phải có IAM policy phù hợp. Đường đi đến dịch vụ không tự cấp quyền tải object.

### Bucket và object là hai phạm vi trách nhiệm

Bucket là nơi cấu hình các thuộc tính lưu trữ và bảo vệ dữ liệu. Object là nội dung được lưu trong bucket. Trong thiết kế quyền, hãy tách hai nhóm công việc:

- **Quản lý bucket:** xem hoặc đổi cấu hình, quản lý các cơ chế chia sẻ và bảo vệ.
- **Truy cập object:** liệt kê tên, đọc nội dung, tạo mới, ghi đè, xóa hoặc khôi phục từ Archive.

Một tài khoản được tải object không nhất thiết cần quyền đổi cấu hình bucket. Ngược lại, người kiểm tra cấu hình bucket có thể không cần đọc nội dung hóa đơn.

OCI cung cấp các resource type `buckets`, `objects`, `objectstorage-namespaces` và nhóm tổng hợp `object-family`. Chọn resource type cụ thể giúp biểu đạt trách nhiệm rõ hơn so với cấp quyền rộng trên cả nhóm tài nguyên. Xem [tham chiếu policy cho Object Storage và Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

## Bắt đầu từ yêu cầu, chưa bắt đầu từ policy

Giả sử hệ thống có compartment `DataProd`, hai bucket private:

- `billing-documents-prod`: chứa hóa đơn và dữ liệu tiếp nhận.
- `db-backups-prod`: chứa bản sao lưu cơ sở dữ liệu.

Thiết kế vai trò ban đầu:

| Vai trò minh họa | Nhu cầu hợp lệ | Việc phải bị chặn |
| --- | --- | --- |
| `BillingReaders` | Liệt kê và tải dữ liệu trong bucket hóa đơn | Upload, ghi đè, xóa, đổi cấu hình bucket |
| `InvoicePrefixReaders` | Tải object đã biết tên trong `invoices/` | Liệt kê cả bucket, đọc ngoài prefix |
| `BillingUploaders` | Tạo tên object mới trong `incoming/` | Đọc, ghi đè tên đã tồn tại, xóa |
| `StorageMetadataAuditors` | Xem cấu hình bucket hóa đơn | Tải nội dung hóa đơn, sửa cấu hình |
| `AuditUploadAgents` | Compute tự động gửi dữ liệu nhỏ vào `incoming/` | Dùng khóa cá nhân, sửa hoặc xóa dữ liệu đã gửi |
| `ArchiveRecoveryOperators` | Yêu cầu restore và đọc bản sao lưu | Xóa bản sao lưu, thay đổi bucket |

Đây là các lựa chọn của tình huống học tập, không phải vai trò mặc định của OCI. Trước khi viết policy thực tế, cần ghi rõ:

1. Bucket nằm trong compartment nào.
2. Bên gọi là người dùng hay workload.
3. Client gọi những API nào, kể cả API gọi ngầm.
4. Có cần listing, multipart, overwrite, PAR hay restore không.
5. Có policy rộng hơn, quyền kế thừa hoặc cơ chế bảo vệ khác đang tác động không.

Yêu cầu “được upload” chưa đủ cụ thể. Upload object nhỏ với tên mới và upload bản sao lưu lớn bằng multipart có thể cần các tập permission khác nhau.

## Cú pháp và phạm vi policy

Một allow statement có dạng:

```text
Allow <subject> to <verb> <resource-type> in <location> where <conditions>
```

Ví dụ:

```text
Allow group BillingReaders to read objects in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

Các thành phần của ví dụ:

| Thành phần | Ý nghĩa |
| --- | --- |
| `group BillingReaders` | Cấp quyền cho thành viên của group |
| `read objects` | Chọn verb và loại tài nguyên |
| `in compartment DataProd` | Giới hạn vị trí tài nguyên |
| `target.bucket.name` | Giới hạn thêm bucket được truy cập |

Các group và dynamic group trong ví dụ được giả định thuộc identity domain mặc định. Nếu dùng domain khác, định danh subject theo domain, ví dụ `group FinanceDomain/BillingReaders`. Có thể dùng OCID khi cần định danh chính xác; không đưa placeholder vào policy triển khai. Xem [cú pháp IAM policy](https://docs.oracle.com/en-us/iaas/Content/Identity/Concepts/policysyntax.htm) và [định danh subject trong policy](https://docs.oracle.com/en-us/iaas/Content/Identity/policysyntax/policy-syntax.htm).

### Phân biệt chỗ lưu policy và phạm vi tài nguyên

Policy là một tài nguyên được quản lý tại tenancy hoặc compartment. Phần `in compartment ...` trong statement chỉ định phạm vi tài nguyên được cấp quyền; nó không có nghĩa policy phải cấp quyền toàn tenancy chỉ vì policy được lưu ở root.

Trong ví dụ này, có thể để nhóm quản trị IAM quản lý policy tại root, nhưng statement vẫn chỉ áp dụng cho `DataProd`. Với compartment lồng nhau, sử dụng đường dẫn compartment phù hợp hoặc cú pháp `in compartment id <compartment_ocid>`.

Compartment con kế thừa quyền từ cấp trên. Vì vậy, đưa bucket vào compartment riêng chỉ có tác dụng cô lập quyền khi các policy ở tổ tiên cũng phù hợp. Xem [quản lý compartment và quyền kế thừa](https://docs.oracle.com/en-us/iaas/Content/Identity/Tasks/managingcompartments.htm).

### Một allow statement hẹp không thu hồi một allow statement rộng

Giả sử cùng một người dùng thuộc hai group:

```text
Allow group BillingReaders to read objects in compartment DataProd
where target.bucket.name = 'billing-documents-prod'

Allow group LegacyStorageAdmins to manage object-family in tenancy
```

Nếu người dùng vẫn thuộc `LegacyStorageAdmins`, statement đầu tiên không biến họ thành người chỉ đọc. Khi đánh giá quyền, phải xét toàn bộ các nguồn cấp quyền có hiệu lực.

OCI đã bổ sung **deny policies** dưới dạng tính năng cần bật ở cấp tenancy. Bài này xây dựng allow policy và không giả định tenancy đã bật deny. Nếu môi trường có deny policy, cần xét cả các ràng buộc đó; không suy luận kết quả chỉ từ một allow statement. Xem [thông báo chính thức về IAM deny policies](https://docs.oracle.com/en-us/iaas/releasenotes/identity/deny-policies.htm).

## Hiểu verb trước khi chọn permission

Các verb `inspect`, `read`, `use`, `manage` thể hiện mức quyền tăng dần. Tuy nhiên, ý nghĩa cụ thể phụ thuộc resource type. Với `objects`, điểm dễ nhầm là `use` có quyền ghi đè nhưng không tự cấp quyền tạo một object mới. Tên verb không thay thế việc đọc bảng permission của dịch vụ.

Để thiết kế quyền tối thiểu, nên lập ánh xạ API cho các thao tác thực sự cần:

| Thao tác | Permission chính cần xem |
| --- | --- |
| Liệt kê bucket | `BUCKET_INSPECT` |
| Xem cấu hình bucket | `BUCKET_READ` |
| Liệt kê object | `OBJECT_INSPECT` |
| Tải nội dung object | `OBJECT_READ` |
| Put object với tên chưa tồn tại | `OBJECT_CREATE` |
| Put object với tên đã tồn tại | `OBJECT_OVERWRITE` |
| Xóa object | `OBJECT_DELETE` |
| Xóa một version | `OBJECT_VERSION_DELETE` |
| Yêu cầu restore object Archive | `OBJECT_RESTORE` |
| Quản lý pre-authenticated request | `PAR_MANAGE` |

Bảng trên phục vụ thiết kế, không đại diện toàn bộ API của dịch vụ. Các nghiệp vụ như multipart, lifecycle, copy và replication có thể yêu cầu nhiều permission hoặc quyền cho service principal. Tra [permission theo từng API](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm) khi chọn client và luồng xử lý.

Có hai hệ quả thực tế:

- `read buckets` không biểu đạt yêu cầu tải nội dung object; việc đó cần quyền trên `objects`.
- `manage objects` không kèm điều kiện permission sẽ rộng hơn nhiều so với “chỉ được tạo mới”.

## Mẫu quyền đọc theo bucket

Nhóm `BillingReaders` cần liệt kê và tải tất cả object trong bucket hóa đơn:

```text
Allow group BillingReaders to read objects in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

Policy này phù hợp khi ứng dụng cần duyệt danh sách object trước khi tải. Nó cũng cho phép thấy tên các object trong bucket, nên cần đánh giá tên object có chứa dữ liệu nhạy cảm hay không.

Nếu nhóm thực sự cần xem cấu hình bucket, bổ sung statement riêng:

```text
Allow group BillingReaders to read buckets in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

Không thêm statement thứ hai chỉ để thử làm một lỗi phân quyền biến mất. Với API/CLI đã biết namespace, bucket và tên object, thiết kế có thể không cần luồng khám phá tài nguyên của Console.

Nhóm chỉ kiểm tra cấu hình dùng vai trò riêng:

```text
Allow group StorageMetadataAuditors to read buckets in compartment DataProd
where target.bucket.name = 'billing-documents-prod'
```

Nếu Console cần liệt kê bucket, cân nhắc quyền discovery riêng:

```text
Allow group StorageMetadataAuditors to inspect buckets in compartment DataProd
```

Statement discovery này có phạm vi **toàn bộ tên bucket trong compartment**. Không nên coi nó là quyền chỉ nhìn thấy một bucket. Nếu việc lộ tên bucket không phù hợp, hãy chọn luồng truy cập trực tiếp hoặc thiết kế lại ranh giới compartment.

## Mẫu chỉ đọc object thuộc một prefix

Giả sử ứng dụng đã biết chính xác object cần tải và chỉ được đọc tên bắt đầu bằng `invoices/`:

```text
Allow group InvoicePrefixReaders to manage objects in compartment DataProd
where all {
  target.bucket.name = 'billing-documents-prod',
  target.object.name = 'invoices/*',
  request.permission = 'OBJECT_READ'
}
```

Ở đây, `manage` là tập quyền ban đầu, còn `request.permission` thu hẹp statement xuống quyền đọc. Toàn bộ điều kiện trong `all` phải cùng thỏa mãn.

Ví dụ thiết kế:

| Object được yêu cầu | Kết quả mong đợi của vai trò này |
| --- | --- |
| `invoices/2026/november-001.pdf` | Cho phép đọc |
| `invoices/archive/2025-001.pdf` | Cho phép đọc |
| `payroll/2026/november.csv` | Không cho phép đọc |
| `invoices-old/november-001.pdf` | Không cho phép đọc |

Prefix là một phần của tên object, không phải thư mục có ACL riêng. OCI hỗ trợ `target.object.name` và pattern cho phân quyền object; ví dụ này sử dụng dấu `/` để tạo ranh giới tên dễ nhận biết. Xem [IAM ở mức object và cách đặt tên object](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm).

### Listing là một quyết định riêng

Mẫu trên không cấp `OBJECT_INSPECT`, nên không dùng nó để liệt kê object. Nó phục vụ tải trực tiếp object đã biết tên.

Nếu bổ sung một statement cho phép `OBJECT_INSPECT` trên toàn bucket, bạn đã mở thêm khả năng khám phá tên object của bucket. Tham số `--prefix` trong một lệnh CLI là bộ lọc do client gửi; không nên lấy lựa chọn bộ lọc của client làm bằng chứng về ranh giới phân quyền.

Khi ứng dụng cần cả discovery lẫn giới hạn dữ liệu:

- Xác định rõ có được thấy tên object ngoài prefix không.
- Kiểm thử riêng listing và truy cập trực tiếp ngoài prefix.
- Nếu yêu cầu cách ly tên và nội dung phức tạp, cân nhắc tách bucket theo nhóm dữ liệu.

Tên bucket có phân biệt hoa thường ở dịch vụ, nhưng tham chiếu IAM lưu ý điều kiện tên bucket được so khớp không phân biệt hoa thường. Tránh thiết kế ranh giới chỉ bằng các tên bucket khác nhau ở chữ hoa/chữ thường. Xem [biến điều kiện Object Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

## Mẫu chỉ được tạo object mới

Với dữ liệu tiếp nhận, yêu cầu có thể là “gửi lên một lần, không đọc lại và không sửa dữ liệu đã gửi”:

```text
Allow group BillingUploaders to manage objects in compartment DataProd
where all {
  target.bucket.name = 'billing-documents-prod',
  target.object.name = 'incoming/*',
  request.permission = 'OBJECT_CREATE'
}
```

Tập quyền này được thiết kế cho luồng PutObject một phần, với tên mới:

- Upload tên mới trong `incoming/`: được phép.
- Upload lại đúng tên đã tồn tại: thiếu quyền overwrite.
- Đọc hoặc xóa object: thiếu permission tương ứng.
- Gửi dữ liệu ra ngoài `incoming/`: không thỏa điều kiện tên.

Ứng dụng nên sinh tên duy nhất, chẳng hạn `incoming/<request-id>.json`, và ghi lại request ID để xử lý retry. Khi kết nối bị gián đoạn sau upload, client có thể không biết yêu cầu đã hoàn tất hay chưa. Không nên xử lý mọi retry bằng cách cấp thêm quyền ghi đè; cần xác định cách đối soát kết quả và chống gửi trùng.

Quyền tạo mới không đồng nghĩa dữ liệu bất biến trước mọi principal. Một quản trị viên hoặc một workload có quyền xóa/ghi đè khác vẫn có thể tác động theo quyền của họ. Với dữ liệu cần bảo vệ lâu dài, phải thiết kế thêm retention, versioning và phân tách vai trò phù hợp.

### Multipart làm thay đổi yêu cầu quyền

Client có thể tự chuyển file lớn sang multipart. Theo tham chiếu OCI, các bước multipart đòi hỏi thêm quyền ghi đè; bước commit còn có yêu cầu quyền đọc bucket và object. Vì vậy, policy chỉ có `OBJECT_CREATE` không phải mẫu upload mọi kích thước. Xem [yêu cầu permission của multipart](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

Với một workload sao lưu lớn mà nghiệp vụ chấp nhận quyền đọc và ghi đè, có thể thiết kế vai trò khác trong bucket riêng:

```text
Allow group BulkBackupUploaders to read buckets in compartment DataProd
where target.bucket.name = 'db-backups-prod'

Allow group BulkBackupUploaders to manage objects in compartment DataProd
where all {
  target.bucket.name = 'db-backups-prod',
  any {
    request.permission = 'OBJECT_CREATE',
    request.permission = 'OBJECT_OVERWRITE',
    request.permission = 'OBJECT_READ',
    request.permission = 'OBJECT_INSPECT'
  }
}
```

Đây là vai trò **có quyền đọc và ghi đè**, nên không được mô tả là “chỉ ghi mới”. Chưa cấp quyền xóa cũng có nghĩa luồng hủy multipart cần được xem xét riêng: thao tác abort yêu cầu quyền xóa theo bảng API của OCI.

Quyết định thực tế nằm ở ba yếu tố: kích thước dữ liệu, hành vi SDK/CLI và yêu cầu bảo vệ bản sao lưu. Hãy chọn chúng cùng nhau.

## Dùng dynamic group cho workload trên Compute

Một tiến trình chạy trên Compute nên có danh tính workload riêng thay vì dùng API key cá nhân của người vận hành.

Ví dụ dynamic group `AuditUploadAgents` chỉ khớp một instance:

```text
instance.id = '<INSTANCE_OCID>'
```

Matching rule xác định thành viên, chưa cấp quyền dữ liệu. Sau đó tạo policy:

```text
Allow dynamic-group AuditUploadAgents to manage objects in compartment DataProd
where all {
  target.bucket.name = 'billing-documents-prod',
  target.object.name = 'incoming/*',
  request.permission = 'OBJECT_CREATE'
}
```

Thay placeholder bằng OCID thực trước khi sử dụng. Nếu mở rộng matching rule tới mọi instance trong một compartment, cần xem xét cả người có quyền tạo hoặc thay đổi các instance đủ điều kiện. Xem [quy tắc matching cho dynamic group](https://docs.oracle.com/en-us/iaas/Content/Identity/dynamicgroups/Writing_Matching_Rules_to_Define_Dynamic_Groups.htm).

Để kiểm tra từ đúng instance bằng OCI CLI, dùng phương thức xác thực tương ứng:

```powershell
oci os object put --auth instance_principal --region ap-singapore-1 --namespace-name <NAMESPACE> --bucket-name billing-documents-prod --name incoming/<UNIQUE_NAME>.txt --file <SMALL_LOCAL_FILE> --no-multipart --force
```

Các giá trị trong dấu `<...>` phải được thay trước khi chạy. Mẫu này dành cho file nhỏ và quyền tạo mới. `--force` điều khiển hành vi xác nhận của CLI; nó không vượt qua IAM hay tự cấp `OBJECT_OVERWRITE`. Tham khảo [phương thức xác thực CLI](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/oci.html) và [lệnh object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

Không dùng `instance_principal` trên laptop rồi lấy lỗi đó kết luận policy sai. Phải kiểm tra từ môi trường thực sự có instance identity đã được đưa vào dynamic group.

## Tách quyền chia sẻ dữ liệu khỏi quyền upload

Pre-authenticated request (PAR) tạo URL cho phép bên có URL truy cập tài nguyên theo phạm vi và kiểu truy cập đã cấp. Việc chia sẻ URL trở thành một phần của kiểm soát dữ liệu.

Nếu nhiệm vụ chỉ là upload hóa đơn, không có lý do mặc định để cấp `PAR_MANAGE`. Quyền tạo PAR còn phải đi kèm các quyền dữ liệu phù hợp với loại truy cập được chia sẻ. Xem [quyền và giới hạn của PAR](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests.htm).

Một thiết kế dễ kiểm soát hơn:

1. Workload upload có quyền dữ liệu cần thiết.
2. Một vai trò chia sẻ riêng tạo PAR khi có yêu cầu nghiệp vụ.
3. Yêu cầu chia sẻ ghi rõ object/prefix, người nhận, kiểu truy cập và hạn dùng.
4. URL được quản lý như bí mật và có phương án thu hồi.

Đừng sửa bucket thành public để giải quyết một lỗi IAM của ứng dụng. Việc thay đổi public access là quyết định khác hẳn việc cấp quyền cho một principal đã xác thực. Oracle khuyến nghị giới hạn nhóm được giữ `BUCKET_UPDATE`, vì quyền này có thể tác động cấu hình truy cập công khai. Xem [bảo vệ quyền truy cập Object Storage](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm).

## Quyền dành cho phục hồi Archive

Đọc object và yêu cầu restore object Archive là hai nhu cầu cần phân biệt. Với vai trò phục hồi trong bucket sao lưu:

```text
Allow group ArchiveRecoveryOperators to manage objects in compartment DataProd
where all {
  target.bucket.name = 'db-backups-prod',
  any {
    request.permission = 'OBJECT_RESTORE',
    request.permission = 'OBJECT_READ',
    request.permission = 'OBJECT_INSPECT'
  }
}
```

Vai trò này được thiết kế để tìm object, yêu cầu restore và đọc dữ liệu khi object đã sẵn sàng. Nó không cấp quyền xóa hoặc ghi đè.

Trong quy trình vận hành, cần tách kết quả “yêu cầu restore được chấp nhận” khỏi kết quả “dữ liệu đã có thể tải”. Người thực hiện phục hồi cũng nên ghi nhận đối tượng cần khôi phục và mục đích để tránh các lần restore không cần thiết. Việc không cấp quyền phục hồi cho mọi tài khoản đọc thông thường giúp kiểm soát tốt hơn thao tác truy xuất dữ liệu Archive.

## Ma trận kiểm thử policy

Không kiểm thử bằng tài khoản Administrators để kết luận một vai trò hẹp đã đúng. Hãy dùng identity thật của từng vai trò và bảo đảm nó không đồng thời thuộc group quản trị rộng.

Chuẩn bị dữ liệu giả lập trong môi trường học tập, với các object đã biết:

- `invoices/demo.txt`
- `payroll/demo.txt`
- Một tên mới sẽ sinh trong `incoming/`

Ma trận mong đợi, với các policy tương ứng trong bài:

| Phép thử | BillingReaders | InvoicePrefixReaders | BillingUploaders |
| --- | --- | --- | --- |
| Liệt kê object của bucket hóa đơn | Thành công | Bị chặn | Bị chặn |
| Đọc `invoices/demo.txt` | Thành công | Thành công | Bị chặn |
| Đọc `payroll/demo.txt` | Thành công | Bị chặn | Bị chặn |
| Tạo tên mới trong `incoming/` | Bị chặn | Bị chặn | Thành công |
| Ghi đè tên vừa tạo | Bị chặn | Bị chặn | Bị chặn |
| Xóa object đã tạo | Bị chặn | Bị chặn | Bị chặn |
| Truy cập bucket không được giao | Bị chặn | Bị chặn | Bị chặn |
| Thay đổi cấu hình bucket | Bị chặn | Bị chặn | Bị chặn |
| Tạo PAR | Bị chặn | Bị chặn | Bị chặn |

“Bị chặn” phải được xác minh bằng tình huống có tài nguyên đích hợp lệ. Yêu cầu tới tên object không tồn tại không chứng minh policy đã ngăn truy cập object thật.

### Ví dụ kiểm tra bằng PowerShell và OCI CLI

Các lệnh dưới đây là bài thực hành, không tự tạo group hay policy. Giả định CLI đã được cài đặt, profile đã cấu hình cho **các danh tính riêng**, namespace đã biết và file dữ liệu giả lập đã có sẵn.

```powershell
$Namespace = 'REPLACE_WITH_NAMESPACE'
$Bucket = 'billing-documents-prod'
$Region = 'ap-singapore-1'
$PayloadPath = './sample-invoice.txt'
$ObjectName = 'incoming/' + [guid]::NewGuid().ToString('N') + '.txt'

# Profile BILLING_READER: mong đợi liệt kê được.
oci os object list --profile BILLING_READER --region $Region --namespace-name $Namespace --bucket-name $Bucket --limit 10

# Profile INVOICE_PREFIX_READER: mong đợi tải được object đã biết.
oci os object get --profile INVOICE_PREFIX_READER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name invoices/demo.txt --file ./invoice-demo.download.txt

# Cùng profile, ngoài prefix: mong đợi bị chặn.
oci os object get --profile INVOICE_PREFIX_READER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name payroll/demo.txt --file ./payroll-denied.download.txt

# Profile BILLING_UPLOADER: lần đầu với tên mới phải thành công.
oci os object put --profile BILLING_UPLOADER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name $ObjectName --file $PayloadPath --no-multipart --force

# Chạy lại ngay với cùng ObjectName: mong đợi bị chặn ghi đè.
oci os object put --profile BILLING_UPLOADER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name $ObjectName --file $PayloadPath --no-multipart --force

# Chỉ thử trên object giả lập vừa tạo: mong đợi bị chặn xóa.
oci os object delete --profile BILLING_UPLOADER --region $Region --namespace-name $Namespace --bucket-name $Bucket --name $ObjectName --force
```

Dùng file nhỏ để kiểm tra riêng luồng PutObject một phần. Sau đó mới kiểm tra kích thước và SDK mà ứng dụng thực tế sử dụng. Tài liệu [CLI object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html) mô tả cơ chế tự chọn multipart và tùy chọn `--no-multipart`.

Tên profile chỉ giúp chọn cấu hình xác thực; nó không phải một vai trò IAM. Hai profile cùng trỏ về một người dùng có quyền quản trị sẽ không kiểm chứng được ranh giới giữa reader và uploader.

Ghi lại thời điểm, principal, operation, tài nguyên, kết quả và request ID khi chạy thử. Với phép thử thất bại như mong đợi, vẫn kiểm tra rằng nguyên nhân không phải sai region, sai namespace hoặc tài nguyên không tồn tại. Thay đổi policy có thể cần thời gian lan truyền trước khi kết quả kiểm tra ổn định; xem [lưu ý về hiệu lực policy Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects.htm).

## Chẩn đoán khi kết quả khác thiết kế

| Hiện tượng | Hướng kiểm tra |
| --- | --- |
| Đọc được object nhưng Console không mở được danh sách | Tách quyền truy cập trực tiếp khỏi quyền discovery của Console |
| Upload file nhỏ được nhưng file lớn thất bại | Kiểm tra client có chuyển sang multipart và gọi các API phụ hay không |
| Uploader sửa được object cũ | Kiểm tra `OBJECT_OVERWRITE`, verb `use` và các group/policy khác |
| Prefix reader thấy tên dữ liệu ngoài phạm vi | Kiểm tra statement cấp `OBJECT_INSPECT` ở mức bucket |
| Cùng lệnh chạy ở laptop được, trên Compute bị chặn | Kiểm tra principal, matching rule và phương thức `--auth` |
| Đổi sang bucket khác vẫn truy cập được | Tìm statement rộng hơn, quyền kế thừa hoặc group quản trị |
| IAM có vẻ đúng nhưng bucket dùng khóa khách hàng vẫn lỗi | Kiểm tra quyền của Object Storage service với khóa Vault |
| Quyền xóa có vẻ đủ nhưng xóa bị từ chối | Kiểm tra retention và các ràng buộc bảo vệ dữ liệu khác |

Bucket sử dụng customer-managed key tạo thêm quan hệ phân quyền với Vault. Đừng cấp `manage keys` cho ứng dụng chỉ để xử lý lỗi object: xác định đúng service principal và quyền khóa cần cho luồng đó. Các yêu cầu bổ sung được ghi cùng từng API trong [tham chiếu quyền Object Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

Về quan sát, cần phân biệt thay đổi quản trị và truy cập dữ liệu object; lựa chọn Audit, Object Storage service logs và các cấu hình ghi log phù hợp. Thu thập dữ liệu có ích cho chẩn đoán mà không ghi nội dung API key hoặc URL PAR vào báo cáo lỗi. Xem [hướng dẫn bảo mật và ghi log của Object Storage](https://docs.oracle.com/en-us/iaas/Content/Security/Reference/objectstorage_security.htm).

## Đưa thiết kế vào vận hành

Trước khi áp dụng cho ứng dụng thật, lưu policy cùng lý do cấp quyền và chủ sở hữu vai trò. Mỗi statement nên có câu trả lời cho câu hỏi “bỏ quyền này thì thao tác nghiệp vụ nào không thực hiện được?”.

Một thay đổi triển khai nên có:

- Danh sách principal và bucket chịu tác động.
- Luồng API dự kiến, gồm cả multipart hoặc restore nếu có.
- Kết quả thử thao tác được phép và thao tác phải bị chặn.
- Cách khôi phục policy trước đó nếu ứng dụng lỗi.
- Người chịu trách nhiệm xem lại quyền khi workload hoặc dữ liệu thay đổi.

Khi tự động hóa triển khai, dùng danh tính và quyền dành cho công việc đó; không mặc định giữ quyền quản trị tenancy trong pipeline. Với bản sao lưu hoặc hóa đơn quan trọng, phân tách người vận hành dữ liệu, người quản lý policy và người quản lý khóa giúp giảm khả năng một tài khoản đơn lẻ tác động toàn bộ chuỗi bảo vệ.

Điểm cốt lõi của thiết kế IAM cho Object Storage là mô tả chính xác **ai được làm gì trên dữ liệu nào**, rồi kiểm chứng điều đó bằng đúng danh tính và đúng luồng API. Một policy ngắn chỉ có giá trị khi phạm vi của nó phù hợp với nghiệp vụ và không bị các quyền rộng khác làm mất ranh giới.