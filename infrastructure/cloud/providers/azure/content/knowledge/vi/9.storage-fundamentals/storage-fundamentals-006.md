# Shared key, Shared Access Signature và user delegation SAS

Trong module **CLOUD_PROVIDERS_AZURE**, chúng ta khám phá hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời học cách triển khai, giám sát, bảo vệ và kiểm soát chi phí một kiến trúc ứng dụng trên Azure. Ở chương **Nền tảng Azure Storage**, một quyết định bảo mật quan trọng là: ứng dụng và người dùng bên ngoài được phép truy cập blob, file hoặc những dịch vụ lưu trữ khác bằng cách nào, trong bao lâu, với quyền gì?

Azure Storage cung cấp nhiều cơ chế xác thực và ủy quyền. Trong bài này, chúng ta tập trung vào **Shared Key** (khóa tài khoản lưu trữ), **Shared Access Signature (SAS)** và biến thể **user delegation SAS** cho Blob Storage. Chúng liên quan với nhau nhưng không đồng nghĩa. Việc chọn sai có thể khiến một người nhận đường dẫn tải hóa đơn vô tình được cấp quyền rộng tới cả storage account.

Sau bài học, bạn có thể:

- Phân biệt xác thực bằng account key với việc trao quyền tạm thời bằng SAS.
- So sánh **service SAS**, **account SAS** và **user delegation SAS** theo nguồn ký, phạm vi, khả năng cấp quyền và thu hồi.
- Đọc các tham số quan trọng trong một SAS token như `sp`, `se`, `sr`, `spr` và `sig`.
- Phát hành một **user delegation SAS** cho một blob bằng Azure CLI và Microsoft Entra ID theo nguyên tắc ít quyền nhất.
- Thiết kế vòng đời phát hành, phân phối, giới hạn và thu hồi SAS; kiểm tra các lỗi thường gặp.
- Đánh giá khi nào nên tắt Shared Key authorization cho Blob Storage và các hệ quả vận hành.

## 1. Bài toán: chia sẻ dữ liệu mà không lộ khóa tài khoản

Giả sử một ứng dụng quản lý đơn hàng lưu tệp hóa đơn ở Azure Blob Storage:

```text
Storage account: stordersprod
  |
  +-- Blob container: invoices (private)
         |
         +-- 2026/INV-1042.pdf
         +-- 2026/INV-1043.pdf
```

Một khách hàng cần tải duy nhất hóa đơn `INV-1042.pdf` trong 10 phút. Bạn có thể cấp quyền theo nhiều cách:

1. **Không nên:** đưa storage account key vào trình duyệt hoặc ứng dụng điện thoại; khóa này có phạm vi quyền rất rộng.
2. **Có thể:** server sinh **SAS URL** cho đúng blob, với quyền đọc và thời hạn ngắn; trình duyệt dùng URL này trực tiếp tới Blob Storage.
3. **Ưu tiên cho backend chạy trên Azure:** dùng **managed identity + Azure RBAC** để backend tự truy cập Storage qua Microsoft Entra ID, không phải cất account key.

Luồng chia sẻ tải hóa đơn:

```text
Khách hàng --> API đơn hàng (đã đăng nhập, kiểm tra quyền sở hữu hóa đơn)
                          |
                          | Backend dùng Entra ID / managed identity
                          | để yêu cầu user delegation key và tạo SAS
                          v
               SAS đọc 1 blob, hết hạn sau 10 phút
                          |
                          v
             Khách hàng tải blob trực tiếp qua HTTPS
                          |
                          v
                    Azure Blob Storage
```

SAS là **bearer credential**: ai nắm được URL/token đều có thể sử dụng trong phạm vi quyền và điều kiện đã ký, ngay cả khi họ không phải người được gửi URL ban đầu. Vì vậy, trước khi phát hành SAS, API phải **xác thực người yêu cầu và kiểm tra quyền truy cập dữ liệu ở tầng nghiệp vụ**. SAS không tự biết một hóa đơn thuộc về khách hàng nào.

## 2. Shared Key authorization là gì?

Mỗi storage account thuộc loại hỗ trợ Shared Key có các **account access keys** (thường có hai khóa `key1` và `key2`). Đây là bí mật ở cấp **storage account**, được Azure cấp phát và dùng để ký các yêu cầu Shared Key hoặc những SAS sử dụng cơ chế khóa tài khoản.

Khi client dùng Shared Key authorization, client tạo chữ ký mật mã từ nội dung yêu cầu và account key. Dịch vụ Storage xác minh chữ ký để xác thực yêu cầu.

```text
Ứng dụng giữ account key
        |
        | Tạo chữ ký Shared Key cho request
        v
HTTP request + Authorization header
        |
        v
Azure Storage kiểm tra chữ ký bằng khóa của storage account
        |
        v
Chấp nhận hoặc từ chối theo cơ chế authorization áp dụng
```

**Đặc điểm quan trọng:** account key là thông tin xác thực có đặc quyền rất rộng ở phạm vi tài khoản lưu trữ. Nó không gắn một cách tự nhiên với các quyền chi tiết của từng người dùng Microsoft Entra ID. Người có account key có thể thực hiện nhiều hoạt động dữ liệu hoặc phát hành SAS trong phạm vi dịch vụ hỗ trợ, và việc phân biệt từng người đã sử dụng cùng một khóa trở nên khó khăn.

### 2.1. Vì sao không phân phối account key?

Nếu bạn đưa account key vào một máy khách hoặc ứng dụng frontend:

- Người nhận có thể trích xuất và tái sử dụng khóa.
- Không thể giới hạn account key chỉ ở một blob và một khoảng thời gian ngắn giống SAS.
- Việc thu hồi khóa sẽ ảnh hưởng mọi ứng dụng hoặc SAS còn dựa trên khóa đó.
- Khó quy trách nhiệm cho một tác nhân cụ thể nếu nhiều workload sử dụng chung một khóa.
- Khóa có thể bị lộ qua repository, biến môi trường, bản sao lưu, thông báo lỗi hoặc công cụ giám sát.

Khi phải sử dụng Shared Key để tương thích với hệ thống cũ, bảo vệ nó như một bí mật có đặc quyền cao: lưu trong dịch vụ quản lý bí mật phù hợp, giới hạn người được đọc khóa, ghi nhận quy trình truy cập và có kế hoạch thay thế bằng Microsoft Entra ID khi dịch vụ hỗ trợ.

### 2.2. Hai account keys hỗ trợ xoay vòng

Storage account thường có hai khóa để hỗ trợ **key rotation** theo từng bước:

1. Xác định mọi client, dịch vụ, bản cấu hình và SAS đang phụ thuộc vào khóa sẽ thay đổi.
2. Chuyển client sang khóa còn lại theo quy trình an toàn, xác nhận truy cập hoạt động.
3. Tạo lại (**regenerate**) khóa cũ, cập nhật hệ thống cần dùng khóa mới.
4. Thử nghiệm, theo dõi lỗi xác thực và đưa lịch xoay vòng vào vận hành định kỳ.

**Tái tạo account key làm mất hiệu lực các chữ ký/SAS đã được ký bằng chính khóa đó** và có thể làm gián đoạn client chưa chuyển đổi. Không regenerate cả hai khóa liên tiếp mà chưa kiểm kê đầy đủ phụ thuộc. Nếu khóa bị lộ, phải xử lý theo quy trình sự cố an ninh thay vì chỉ dựa vào việc SAS có ngày hết hạn.

## 3. SAS là gì?

**Shared Access Signature** là token chứa các điều kiện truy cập được ký bằng một khóa hợp lệ. Client gửi SAS kèm yêu cầu đến Azure Storage, thường trong **query string của URL**, để dịch vụ xác minh quyền mà không cần client nhận account key hoặc đăng nhập bằng Entra ID.

Ví dụ minh họa đã **lược bỏ chữ ký thực**, không thể sử dụng để truy cập:

```text
https://stordersprod.blob.core.windows.net/invoices/2026/INV-1042.pdf
    ?sv=<service-version>
    &sp=r
    &se=2026-11-20T10%3A10%3A00Z
    &spr=https
    &sr=b
    &sig=<redacted-signature>
```

Trong thực tế URL sẽ nằm trên một dòng. Thời gian trên chỉ là ví dụ quá khứ để minh họa cấu trúc, không phải một SAS hợp lệ hiện tại.

SAS không phải account key, nhưng **vẫn là thông tin nhạy cảm**. Ai có SAS hợp lệ đều có thể thực hiện các hành động được phép trong thời gian và phạm vi token còn hiệu lực. Đừng coi một URL có `sig` là đường dẫn công khai vô hại.

### 3.1. Các tham số SAS thường gặp

| Tham số | Tên gọi | Ý nghĩa |
|---|---|---|
| `sv` | Signed version | Phiên bản giao thức Storage được sử dụng để ký/xử lý SAS |
| `sp` | Signed permissions | Quyền như đọc, ghi, tạo, xóa, liệt kê, tùy loại SAS và dịch vụ |
| `st` | Signed start | Thời điểm bắt đầu hiệu lực nếu có |
| `se` | Signed expiry | Thời điểm hết hạn |
| `spr` | Signed protocol | Ví dụ `https` để chỉ cho phép HTTPS |
| `sip` | Signed IP | Dải IP công cộng được phép sử dụng SAS nếu khai báo và tương thích đường mạng |
| `sr` | Signed resource | Loại tài nguyên ở service/user delegation SAS, ví dụ blob (`b`) hoặc container (`c`) |
| `ss` | Signed services | Các dịch vụ được cấp phạm vi ở account SAS |
| `srt` | Signed resource types | Các loại tài nguyên ở account SAS |
| `si` | Signed identifier | Tham chiếu stored access policy đối với service SAS thích hợp |
| `sig` | Signature | Chữ ký bảo vệ tính toàn vẹn của các điều kiện đã ký |

Không phải mọi SAS đều có cùng tập tham số. Ví dụ, **user delegation SAS** có thêm các trường định danh/khóa ủy quyền như `skoid`, `sktid`, `skt`, `ske`, `sks` và `skv`. Những trường này không biến SAS thành một login token của người dùng cuối.

Một số quyền viết tắt thường gặp trong Blob Storage:

| Ký hiệu | Quyền | Lưu ý |
|---|---|---|
| `r` | Read | Đọc nội dung/properties theo quyền được hỗ trợ |
| `a` | Add | Bổ sung dữ liệu với các loại blob phù hợp |
| `c` | Create | Tạo tài nguyên theo phạm vi SAS |
| `w` | Write | Ghi/cập nhật dữ liệu theo loại tài nguyên |
| `d` | Delete | Xóa dữ liệu, quyền mạnh cần hạn chế |
| `l` | List | Liệt kê container/blobs theo phạm vi hỗ trợ |

Quyền chính xác phụ thuộc **loại SAS, dịch vụ và phiên bản REST API**. Không tự suy ra rằng một chuỗi `sp` áp dụng giống nhau cho Blob, Queue, File và Table. Khi viết code, hãy dùng SDK/CLI để tạo tập quyền hợp lệ thay vì tự ghép chữ ký bằng tay.

### 3.2. Phạm vi và quyền quyết định mức rủi ro

SAS được tạo cho **một blob chỉ với quyền `r` trong 10 phút** có phạm vi nhỏ hơn SAS cho một container với `rlwd` trong nhiều ngày. Nguyên tắc thiết kế:

- Chọn tài nguyên hẹp nhất: blob thay vì container khi chỉ cần một tệp.
- Chỉ cấp phép cần thiết: `r` thay vì `w`, `d` hoặc quyền rộng hơn.
- Đặt thời hạn ngắn, xét thêm độ trễ mạng và thời gian đồng hồ.
- Dùng `spr=https`, cân nhắc `sip` nếu IP nguồn ổn định và nằm trong phạm vi dịch vụ xử lý.
- Tránh phát hành SAS vào logs, email đại trà, URL analytics, client-side error reports hoặc support tickets.

Nếu không khai báo `st`, SAS có thể có hiệu lực ngay theo xử lý của dịch vụ. Với trường hợp cần `st`, hãy chú ý **clock skew** giữa client và Azure Storage: đặt thời điểm bắt đầu chính xác bằng “bây giờ” có thể dẫn tới lỗi tạm thời trong một số môi trường. Khi không cần giới hạn thời điểm bắt đầu, thường có thể bỏ `st`.

## 4. Ba loại SAS cần phân biệt

Azure Storage hỗ trợ các loại SAS khác nhau về **nguồn khóa ký** và **phạm vi**:

1. **Service SAS:** ký bằng **storage account key**, cấp quyền cho tài nguyên thuộc **một dịch vụ Storage** cụ thể; với Blob Storage thường dùng cho blob hoặc container.
2. **Account SAS:** cũng ký bằng **storage account key**, có thể cấp các thao tác ở phạm vi **nhiều dịch vụ/loại tài nguyên** được khai báo trong token.
3. **User delegation SAS:** được ký bằng **user delegation key** do Blob service phát hành dựa trên danh tính **Microsoft Entra ID**. Loại này dành cho **Blob Storage** (bao gồm các trường hợp được hỗ trợ của Data Lake Storage Gen2), không phải cơ chế SAS chung cho Queue, Table hoặc Azure Files.

### 4.1. Bảng so sánh cốt lõi

| Tiêu chí | Service SAS | Account SAS | User delegation SAS |
|---|---|---|---|
| Vật liệu ký | Account key | Account key | User delegation key lấy bằng Entra ID |
| Phạm vi điển hình | Blob, container hay tài nguyên một dịch vụ | Nhiều dịch vụ và resource types khai báo trong token | Blob/container theo phạm vi hỗ trợ |
| Cần sở hữu account key khi phát hành? | Có | Có | Không |
| Cần Microsoft Entra ID khi phát hành? | Không bắt buộc | Không bắt buộc | **Có** |
| Hỗ trợ stored access policy | **Có** cho service SAS hỗ trợ | Không | Không |
| Cách thu hồi chủ yếu | Hết hạn, sửa/xóa stored access policy, hoặc xoay account key | Hết hạn hoặc xoay account key | Hết hạn hoặc thu hồi user delegation keys ở account |
| Phạm vi dịch vụ | Theo một dịch vụ | Có thể nhiều dịch vụ | Blob Storage |
| Khuyến nghị cho Blob Storage | Dùng khi yêu cầu tương thích hoặc chính sách đặc thù | Chỉ khi thật sự cần phạm vi account SAS | **Ưu tiên** khi có thể |

**Không nhầm service SAS với user delegation SAS** chỉ vì cả hai cùng cấp quyền đọc một blob. Điểm khác biệt quan trọng là ai có thể tạo chữ ký và quyền dùng để ký.

### 4.2. Service SAS

Service SAS hữu ích khi cần ủy quyền cho tài nguyên trong một dịch vụ, ví dụ tải một blob hoặc ghi vào một container được chỉ định. Token được ký bằng storage account key, vì vậy người phát hành vẫn phải có quyền truy cập khóa mạnh ở mức storage account.

Ví dụ tình huống:

- Hệ thống cũ cần phát hành URL tải một blob cho đối tác.
- Một quy trình phát hành SAS dùng **stored access policy** của container để quản lý thời gian/quyền hoặc hỗ trợ thu hồi thông qua policy.

**Stored access policy** là một chính sách đặt tại container, có identifier và các điều kiện được hỗ trợ. Khi service SAS tham chiếu identifier bằng `si`, thay đổi hoặc xóa policy đó có thể ảnh hưởng các SAS phụ thuộc vào nó (có thể có độ trễ để thay đổi có hiệu lực). Không phải SAS nào cũng dùng stored access policy; **ad hoc SAS** chứa điều kiện ngay trong token.

Một SAS có thể chọn cách xác định quyền/thời gian qua stored access policy theo quy tắc dịch vụ, nhưng không nên khai báo trùng/không hợp lệ giữa token và policy. Hãy dùng SDK/CLI chính thức và đọc lại quyền thực tế của policy.

### 4.3. Account SAS

Account SAS có thể mô tả phạm vi bằng `ss` (**services**) và `srt` (**resource types**), ngoài quyền `sp` và thời hạn. Nó hữu ích khi cần một nhóm thao tác mà service SAS không bao phủ, chẳng hạn một số thao tác ở phạm vi account/service theo khả năng Storage API.

Do account SAS có thể được cấp phạm vi rộng, rủi ro khi phát hành quá tay lớn hơn so với một service SAS chỉ đọc một blob. Nó cũng **không** hỗ trợ stored access policy. Nếu account SAS bị phát tán, các lựa chọn thu hồi có giới hạn: đợi hết hạn hoặc xử lý account key dùng để ký, việc sau có thể gây tác động rộng.

### 4.4. User delegation SAS

User delegation SAS là phương án nên ưu tiên khi client cần truy cập Blob Storage qua một URL tạm thời và backend có thể xác thực bằng Microsoft Entra ID.

Quy trình tổng quát:

1. Workload đăng nhập bằng Microsoft Entra ID, ưu tiên **managed identity** nếu chạy trên Azure.
2. Workload được gán quyền phù hợp để yêu cầu **user delegation key** từ Blob service.
3. Blob service cấp khóa ủy quyền có thời hạn cho principal đã được xác thực.
4. Workload dùng khóa ủy quyền ký SAS với phạm vi/quyền/thời hạn đã chọn.
5. Client nhận SAS URL rồi truy cập trực tiếp Blob Storage; client **không cần** giữ account key hay nhận Entra ID token của backend.

```text
Backend (managed identity)
          |
          | Token Microsoft Entra ID
          v
Blob service: yêu cầu user delegation key
          |
          | User delegation key có thời hạn
          v
Backend ký user delegation SAS
          |
          | SAS URL đọc 1 blob
          v
Browser / đối tác ---> Blob Storage xác minh SAS ---> Blob được phép truy cập
```

Khóa ủy quyền có thời hạn tối đa **7 ngày** theo giới hạn của dịch vụ. SAS được ký bằng khóa đó không thể có hiệu lực lâu hơn khóa; thực tế nên dùng SAS ngắn hơn nhiều, ví dụ vài phút cho một lượt tải xuống. User delegation SAS **không thể liên kết với stored access policy**.

Một ưu điểm quan trọng là backend không cần đọc storage account key. Quyền có hiệu lực khi dùng user delegation SAS được ràng buộc với các quyền dữ liệu thích hợp của principal Entra ID đã dùng để xin khóa, cùng các quyền/giới hạn trong SAS; không thể coi một principal chỉ có quyền đọc là có thể tùy ý cấp SAS xóa dữ liệu. Cách kết hợp Azure RBAC, ACL khi bật hierarchical namespace và những điều kiện khác phụ thuộc dịch vụ/REST API nên cần kiểm thử theo đối tượng dữ liệu thật.

## 5. Những quyền nào cần có để tạo user delegation SAS?

Để xin user delegation key, principal cần action quản lý sau:

```text
Microsoft.Storage/storageAccounts/blobServices/generateUserDelegationKey/action
```

Action này phải được gán ở **scope storage account hoặc scope cha phù hợp** (resource group/subscription); gán chỉ tại một container không đủ cho yêu cầu xin user delegation key ở cấp account.

Vai trò tích hợp **Storage Blob Delegator** cung cấp quyền yêu cầu khóa ủy quyền. Với những thao tác dữ liệu như đọc blob, người phát hành còn cần quyền data plane phù hợp, ví dụ **Storage Blob Data Reader** tại phạm vi container cần đọc. Có thể sử dụng một vai trò tích hợp khác có đủ các action cần thiết, nhưng phải xem quyền và scope thực tế chứ không suy ra chỉ từ tên role.

Ví dụ yêu cầu:

| Tác vụ | Phân quyền cần đánh giá | Phạm vi |
|---|---|---|
| Xin user delegation key | `generateUserDelegationKey/action` | Storage account hoặc scope cha |
| Đọc blob | Quyền data plane đọc blob | Container/blob ở phạm vi được hỗ trợ |
| Viết hoặc xóa blob | Quyền data plane ghi/xóa phù hợp | Chỉ nơi nghiệp vụ thực sự cần |
| Xác thực workload | Entra ID token, ví dụ managed identity | Danh tính đang chạy backend |

**Reader** ở lớp Azure Resource Manager không mặc nhiên cho phép đọc nội dung blob. **Contributor** ở lớp quản lý cũng không nên được coi là thay thế rõ ràng cho quyền dữ liệu. Chọn role data plane chính xác và tránh gán quyền rộng ở subscription chỉ để phát hành một SAS cho một file.

Một danh tính có thể được phép yêu cầu delegation key ở cấp account nhưng chỉ có quyền đọc dữ liệu ở một container; đây là lý do nên kết hợp scope phù hợp thay vì cấp data permissions trên toàn storage account một cách không cần thiết.

## 6. Quy trình phát hành SAS an toàn

Trước khi tạo SAS, backend phải trả lời:

1. **Ai yêu cầu?** Người dùng đã được xác thực hay một hệ thống được ủy quyền?
2. **Tài nguyên nào?** Một blob, một container hay thao tác ở cấp account?
3. **Hành động gì?** Chỉ đọc (`r`), hay có lý do nghiệp vụ cần ghi (`w`), tạo (`c`), xóa (`d`)?
4. **Trong bao lâu?** Từ vài phút cho lượt tải đến khoảng thời gian phù hợp với tác vụ, không mặc định nhiều ngày.
5. **Điều kiện mạng?** Bắt buộc HTTPS; có nên giới hạn `sip` hay không?
6. **Ai phát hành?** Managed identity/Entra principal nào, với RBAC và scope nào?
7. **Nếu bị lộ?** Có phương án thu hồi khả thi và giám sát bất thường không?

Đối với bài toán hóa đơn, các điều kiện đề xuất:

| Điều kiện | Giá trị đề xuất |
|---|---|
| Tài nguyên | Đúng blob `invoices/2026/INV-1042.pdf` |
| Quyền | `Read` |
| TTL | 10 phút |
| Protocol | HTTPS |
| Đối tượng phát hành | Backend có managed identity, được phép đọc container |
| Đối tượng nhận | Client đã được backend xác thực và kiểm tra quyền sở hữu hóa đơn |
| Phương án khi thất lạc | Hết hạn nhanh; nếu cần thu hồi khẩn cấp, xem tác động của revoke delegation keys |

Không phát hành một SAS container có quyền List và Delete chỉ vì frontend cần tải một file PDF.

## 7. Thực hành: tạo user delegation SAS bằng Azure CLI

Bài thực hành sử dụng **Azure CLI trên Bash** (chẳng hạn Azure Cloud Shell), một **Blob Storage account** và một blob riêng tư đã tồn tại. Các lệnh dưới đây chỉ là mẫu cấu hình; không giả định đã có tài nguyên hoặc danh tính trong tenant của bạn.

**Điều kiện đầu vào:**

- Có storage account `stordersdev001` trong resource group `rg-orders-dev` với container `invoices`.
- Container chứa một blob có tên `2026/INV-1042.pdf` (thư mục hiển thị trong Blob Storage chỉ là phần của tên blob nếu không dùng hierarchical namespace).
- Người thực hiện đã đăng nhập vào Azure CLI bằng Microsoft Entra ID và có quyền đọc blob cần thiết.
- Người dùng hoặc quản trị viên có quyền tạo role assignments đã cấp quyền `generateUserDelegationKey/action` tại đúng scope.
- Storage account cho phép request qua mạng từ môi trường đang thực hành; nếu dùng firewall hoặc private endpoint, phải đáp ứng các điều kiện mạng tương ứng.

### 7.1. Xác nhận subscription và tài nguyên

```bash
az login
az account show --output table
az account set --subscription "<subscription-id>"

RG="rg-orders-dev"
ACCOUNT="stordersdev001"
CONTAINER="invoices"
BLOB="2026/INV-1042.pdf"

az storage account show \
  --resource-group "$RG" \
  --name "$ACCOUNT" \
  --query "{name:name,id:id,allowSharedKeyAccess:allowSharedKeyAccess}" \
  --output json
```

Kết quả `allowSharedKeyAccess` phản ánh cấu hình cho phép xác thực Shared Key. Nếu thuộc tính không được đặt tường minh, không suy ra đây là bằng chứng account đã được khóa Shared Key; phải kiểm tra trạng thái hiệu lực theo tài liệu của loại account và chính sách tổ chức.

### 7.2. Chuẩn bị quyền cho người phát hành

Với một **người dùng Entra ID** đang đăng nhập Azure CLI, quản trị viên có quyền tạo role assignments có thể minh họa bằng:

```bash
STORAGE_SCOPE=$(az storage account show \
  --resource-group "$RG" --name "$ACCOUNT" \
  --query id --output tsv)

CONTAINER_SCOPE="$STORAGE_SCOPE/blobServices/default/containers/$CONTAINER"
USER_OBJECT_ID=$(az ad signed-in-user show --query id --output tsv)

# Cần quyền RBAC quản trị thích hợp để chạy hai lệnh dưới đây.
az role assignment create \
  --assignee-object-id "$USER_OBJECT_ID" \
  --assignee-principal-type User \
  --role "Storage Blob Delegator" \
  --scope "$STORAGE_SCOPE"

az role assignment create \
  --assignee-object-id "$USER_OBJECT_ID" \
  --assignee-principal-type User \
  --role "Storage Blob Data Reader" \
  --scope "$CONTAINER_SCOPE"
```

Nếu người phát hành là **managed identity/service principal**, thay `USER_OBJECT_ID` bằng **principal Object ID** của danh tính đó và sử dụng `--assignee-principal-type ServicePrincipal` khi phù hợp. Với hệ thống production, nên cấp quyền qua IaC hoặc một quy trình quản trị có phê duyệt, không phải để backend tự tạo role assignment.

Role assignment có thể cần thời gian để lan truyền. Azure RBAC cho phép người dùng yêu cầu delegation key không đồng nghĩa cho phép người dùng lấy account key; hãy giữ hai quyền này tách biệt.

### 7.3. Sinh SAS đọc một blob trong 10 phút

Sử dụng Azure CLI lấy token từ Microsoft Entra ID:

```bash
# Cloud Shell Bash / GNU date: thời gian hết hạn theo UTC.
EXPIRY=$(date -u -d '+10 minutes' '+%Y-%m-%dT%H:%MZ')

# Lưu token vào biến trong phiên shell để hạn chế in token ra terminal.
SAS=$(az storage blob generate-sas \
  --account-name "$ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "$BLOB" \
  --permissions r \
  --expiry "$EXPIRY" \
  --https-only \
  --auth-mode login \
  --as-user \
  --output tsv)
```

Tùy phiên bản Azure CLI, cú pháp tùy chọn có thể thay đổi; hãy kiểm tra trợ giúp của lệnh tại môi trường đang dùng. Tham số quan trọng là `--auth-mode login --as-user`: **phát hành user delegation SAS bằng Entra ID**, không âm thầm lấy account key để ký kiểu Shared Key.

Nếu cần ghép URL để backend trả về qua HTTPS cho người dùng đã được kiểm tra quyền:

```bash
# Ví dụ chỉ dùng tên blob đơn giản, không có ký tự cần URL-encode.
SAS_URL="https://$ACCOUNT.blob.core.windows.net/$CONTAINER/$BLOB?$SAS"

# Không in SAS_URL hoặc SAS vào log, terminal hay pipeline output.
# Backend phải chuyển URL qua kênh an toàn sau khi xác thực người nhận.
```

Với tên blob chứa khoảng trắng, dấu `#`, `?` hoặc ký tự đặc biệt, cần URL-encode **phần đường dẫn blob** đúng quy tắc (không encode toàn bộ query string SAS). Trong ứng dụng thật, nên dùng Azure Storage SDK để xây URL thay vì tự ghép chuỗi.

SAS sẽ hết hiệu lực theo thời hạn đã ký. Bạn không thể “gia hạn” một SAS cũ bằng cách sửa tham số `se` trong URL vì chữ ký bảo vệ nội dung token. Khi cần thời hạn mới, backend phải tạo SAS mới.

### 7.4. Vì sao chỉ nên phát hành SAS sau khi kiểm tra quyền nghiệp vụ?

Tài nguyên blob có thể chứa dữ liệu của nhiều khách hàng. Nếu API nhận `invoiceId` từ client rồi lập tức tạo SAS mà không kiểm tra quan hệ khách hàng-hóa đơn, người dùng có thể thử ID khác để lấy tài liệu không thuộc về họ. Quy trình đúng:

1. Backend xác thực user bằng hệ thống danh tính ứng dụng.
2. Backend tra cứu hóa đơn, kiểm tra user có quyền truy cập bản ghi và tài liệu hay không.
3. Backend xác định blob path từ dữ liệu server-side đáng tin cậy, không dùng trực tiếp path tùy ý do client gửi.
4. Backend phát hành user delegation SAS đọc **một blob** và thời hạn ngắn.
5. Backend trả URL cho client qua HTTPS, không lưu URL đầy đủ trong nhật ký.

Trong một số kiến trúc yêu cầu thu hồi ở từng lượt tải hoặc chống chia sẻ URL, cách phù hợp hơn là **backend làm proxy tải dữ liệu**: client xác thực vào backend, backend dùng managed identity đọc blob rồi truyền dữ liệu; không trả bearer SAS cho client. Đổi lại, backend phải chịu chi phí xử lý và băng thông cao hơn.

## 8. Ví dụ ký bằng Shared Key: khi nào dùng và cần tránh gì?

Các hệ thống cũ đôi khi phát hành **service SAS** từ account key. Azure CLI có thể sử dụng chế độ xác thực theo key khi tài khoản và quyền của người thực hiện cho phép:

```bash
# Chỉ minh họa trong sandbox / storage account thử nghiệm.
# Tránh để Azure CLI hoặc pipeline tự lấy account key trong production.
EXPIRY=$(date -u -d '+15 minutes' '+%Y-%m-%dT%H:%MZ')

SERVICE_SAS=$(az storage blob generate-sas \
  --account-name "$ACCOUNT" \
  --container-name "$CONTAINER" \
  --name "$BLOB" \
  --permissions r \
  --expiry "$EXPIRY" \
  --https-only \
  --auth-mode key \
  --output tsv)
```

Không phải mọi người dùng đăng nhập CLI đều có quyền đọc account key. Nếu SDK hoặc CLI tự gọi thao tác **List Keys**, đó là một hành vi có đặc quyền cần được kiểm soát. **Không mở rộng quyền đọc account key để giải quyết nhanh lỗi phát hành SAS** khi user delegation SAS đáp ứng yêu cầu.

Với **account SAS**, CLI có thao tác ở phạm vi storage account như `az storage account generate-sas`. Cơ chế này ký bằng account key, có thể khai báo signed services (`ss`), resource types (`srt`) và permissions (`sp`). Vì phạm vi có thể lớn hơn service SAS, hãy lập bảng các thao tác được phép và đánh giá tác động trước khi dùng. Không dùng account SAS làm giải pháp mặc định cho việc chia sẻ một blob.

### 8.1. Shared Key authorization và policy chặn Shared Key

Với các dịch vụ hỗ trợ **disallow Shared Key authorization**, tổ chức có thể đặt cấu hình `allowSharedKeyAccess=false` để chặn những request được xác thực bằng Shared Key. Đối với **Blob Storage**, việc này cũng làm cho **service SAS/account SAS được ký bằng account key** không còn được chấp nhận theo cơ chế Shared Key; **user delegation SAS** và các yêu cầu được xác thực bằng Microsoft Entra ID vẫn có thể hoạt động khi điều kiện và quyền phù hợp.

Không kết luận rằng cấu hình này áp dụng giống nhau cho **mọi dịch vụ trong storage account**; tác động tới Azure Files và các giao thức hoặc tính năng tương thích cần được xác minh theo tài liệu dịch vụ cụ thể. Chuyển đổi sang `allowSharedKeyAccess=false` có thể làm gián đoạn ứng dụng cũ, mount/file share hoặc pipeline hiện tại nếu không kiểm kê.

Trước khi bật chặn Shared Key, hãy:

1. Kiểm kê mọi ứng dụng, connection string và thao tác `List Keys` đang sử dụng.
2. Tìm các service/account SAS được ký bằng account key và nơi chúng đang được phân phối.
3. Kiểm tra SDK/CLI, hệ thống backup, ETL, công cụ tích hợp và các dịch vụ khác phụ thuộc vào account.
4. Chuyển workload phù hợp sang Microsoft Entra ID/managed identity và user delegation SAS.
5. Thử nghiệm ở môi trường không production, có phương án rollback và giám sát lỗi `403` sau thay đổi.

Không coi việc tắt Shared Key là biện pháp chống lộ dữ liệu toàn diện: vẫn phải quản lý RBAC, SAS tồn tại, firewall/network rules, private endpoint, logging và vòng đời dữ liệu.

## 9. Thu hồi quyền: điểm khác biệt quan trọng

Khi SAS đã được phát hành, Azure Storage xác minh chữ ký mà không cần liên hệ lại backend ứng dụng cho mỗi lần tải. Điều này giúp hiệu năng tốt nhưng làm **thu hồi một token cụ thể** khó hơn so với một hệ thống kiểm tra phiên truy cập ở mỗi request.

| Loại truy cập | Thu hồi thông thường | Ảnh hưởng cần chú ý |
|---|---|---|
| Shared Key trực tiếp | Regenerate account key đang dùng | Làm gián đoạn mọi client còn giữ khóa cũ |
| Service SAS dạng ad hoc | Hết hạn hoặc regenerate account key ký nó | Có thể ảnh hưởng nhiều SAS/client |
| Service SAS tham chiếu stored access policy | Sửa/xóa stored access policy tương ứng; cũng có thể thay account key | Thay đổi policy có thể ảnh hưởng **mọi SAS cùng tham chiếu** policy đó |
| Account SAS | Hết hạn hoặc regenerate account key ký nó | Không có stored access policy để thu hồi từng nhóm token |
| User delegation SAS | Hết hạn hoặc **revoke user delegation keys** ở storage account | Có thể làm mất hiệu lực **nhiều SAS** được ký bằng các delegation keys bị thu hồi |

Trong tình huống dữ liệu nhạy cảm, nên thiết kế **TTL rất ngắn**, vì việc vô hiệu hóa tức thời *riêng một URL* thường không có sẵn. User delegation SAS không hỗ trợ stored access policy.

### 9.1. Thu hồi user delegation key không phải thu hồi riêng một token

Giả sử backend phát hành 100 user delegation SAS trong một khoảng thời gian bằng khóa ủy quyền. Nếu phát hiện một SAS bị lộ, thao tác thu hồi delegation keys ở storage account có thể ảnh hưởng các SAS khác sử dụng các khóa bị thu hồi. Vì thế, hãy đánh giá phạm vi ảnh hưởng và truyền thông cho hệ thống liên quan trước khi thực hiện thu hồi khẩn cấp.

Thu hồi hoặc xóa quyền RBAC của principal phát hành có thể ngăn cấp khóa mới, nhưng **không nên giả định rằng mọi SAS đã ký sẽ lập tức ngừng hoạt động**. Các khóa/token đã cấp có thời hạn và trạng thái độc lập; sử dụng thao tác revoke delegation keys khi cần vô hiệu hóa những SAS liên quan theo cơ chế của dịch vụ.

### 9.2. Stored access policy không áp dụng cho user delegation SAS

Stored access policy giúp **service SAS** được ký bằng account key tham chiếu một chính sách trên container. Khi thay quyền hoặc thời hạn trong policy, các SAS liên kết sẽ chịu ảnh hưởng theo cơ chế Storage. Đây là công cụ hữu ích cho hệ thống cũ cần thu hồi theo nhóm, nhưng vẫn phụ thuộc account key.

Nếu yêu cầu đồng thời là:

- Không muốn dùng account key, và
- Phải có khả năng thu hồi *riêng từng đường dẫn* ngay lập tức,

thì user delegation SAS với TTL rất ngắn và cơ chế kiểm soát phát hành có thể chưa đủ. Hãy cân nhắc **proxy qua backend**, kiến trúc token/ủy quyền riêng do ứng dụng kiểm soát hoặc thiết kế đổi tên/di chuyển dữ liệu có chủ đích trong phạm vi thích hợp, thay vì kỳ vọng SAS có chức năng thu hồi từng URL.

## 10. Các lỗi cấu hình và nguyên nhân thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| `403 AuthorizationPermissionMismatch` | SAS không có quyền cần thiết hoặc người phát hành user delegation SAS thiếu quyền dữ liệu | Đối chiếu `sp`, RBAC/ACL và thao tác Blob API thực tế |
| `403 AuthenticationFailed` | Chữ ký không hợp lệ, token bị sửa, sai version hoặc SAS đã hết hạn | Kiểm tra cách dựng URL, `sig`, `sv`, `st`, `se`, clock UTC |
| Không xin được user delegation key | Principal thiếu `generateUserDelegationKey/action` hoặc scope cấp role quá hẹp | Kiểm tra role `Storage Blob Delegator` ở storage account/scope cha |
| `--as-user` thất bại | Không đăng nhập Entra ID đúng tenant/subscription, quyền chưa áp dụng hoặc SDK/CLI không phù hợp | Xác nhận `az account show`, role assignment, network và CLI version |
| SAS dạng Shared Key không truy cập được | `allowSharedKeyAccess` bị tắt cho Blob Storage | Xem cấu hình account; chuyển sang user delegation SAS |
| SAS vừa tạo đã bị coi là chưa có hiệu lực | `st` ở tương lai do clock skew | Bỏ `st` khi không cần hoặc đặt khoảng đệm phù hợp |
| SAS đọc một blob nhưng client thử List container | Chỉ có quyền `r` ở blob, không có `l` ở container | Kiểm tra đúng thao tác và tài nguyên được ký |
| SAS hợp lệ nhưng bị firewall chặn | Storage firewall, private endpoint, IP restriction `sip` hoặc DNS | Kiểm tra mạng độc lập với chữ ký và RBAC |
| URL bị lỗi sau khi copy vào trình duyệt | Query string bị encode sai, cắt bớt, thay `&` hoặc `+` | Dùng URL builder/SDK; không chỉnh token thủ công |
| Service SAS mất hiệu lực sau rotate key | Chữ ký được tạo bằng key vừa bị regenerate | Kiểm kê và phát hành lại SAS theo kế hoạch |

### 10.1. Quy trình chẩn đoán có thứ tự

Khi tải một blob bằng SAS thất bại:

1. **Phân biệt loại SAS:** user delegation, service hay account SAS; xem tập tham số, nhưng không công bố chữ ký.
2. **Xác minh đích:** storage account, container, tên blob, endpoint, HTTP method và tên/đường dẫn chính xác.
3. **Xác minh thời gian:** yêu cầu được gửi trong khoảng `st`–`se` và trước khi delegation key hết hạn hay không?
4. **Xác minh quyền:** `sp` có cho phép thao tác? Với user delegation SAS, principal phát hành có RBAC/ACL tương ứng không?
5. **Xác minh cơ chế authorization:** account có chặn Shared Key? Người phát hành có permission yêu cầu user delegation key không?
6. **Xác minh networking:** firewall, private endpoint, DNS, `sip`, HTTPS và tuyến kết nối.
7. **Xem log an toàn:** xác định mã lỗi, thời gian, request ID và IP nguồn; **không** copy nguyên SAS URL chứa `sig` vào log/ticket.
8. **Khắc phục tối thiểu:** điều chỉnh đúng scope/permission/thời hạn, không mở account key hoặc cấp quyền toàn account để tránh lỗi tức thời.

Có thể sử dụng thông tin `x-ms-request-id` hoặc các trường chẩn đoán trong phản hồi để liên hệ với logs dịch vụ. Cấu hình Storage diagnostic settings và retention phù hợp giúp truy vết những request thành công hoặc bị từ chối.

## 11. Mô hình an toàn cho backend Java trên Azure

Giả sử API Java chạy trên Azure App Service, còn Blob Storage chứa tài liệu khách hàng:

```text
App Service (managed identity: mi-orders-api)
     |
     | Entra ID token + Storage Blob Delegator
     | + quyền dữ liệu tại container invoices
     v
Blob Storage: yêu cầu user delegation key
     |
     v
API tạo SAS cho một blob, quyền Read, TTL 10 phút
     |
     v
API trả URL sau khi đã kiểm tra quyền sở hữu hóa đơn
     |
     v
Browser tải qua HTTPS trực tiếp từ Storage
```

Các trách nhiệm cần tách:

**Backend** xác thực người dùng cuối, ánh xạ người dùng đến invoice, chọn blob path, xin khóa và ký SAS. **Managed identity** là danh tính của workload Azure, không phải danh tính của khách hàng tải hóa đơn. **Storage** kiểm tra SAS được gửi kèm request, chứ không thay backend xác định chủ sở hữu hóa đơn.

Với Azure SDK cho Java, các thành phần thường sử dụng gồm `DefaultAzureCredentialBuilder` hoặc `ManagedIdentityCredentialBuilder` từ `azure-identity` cùng `BlobServiceClientBuilder` và các loại cấu hình SAS của `azure-storage-blob`. Luồng lập trình khái niệm:

```text
credential = Microsoft Entra credential của backend
blobServiceClient = BlobServiceClient(endpoint, credential)
delegationKey = yêu cầu khóa ủy quyền có thời hạn
blobClient = client tham chiếu đúng container/blob
sasValues = quyền Read + thời điểm hết hạn + HTTPS
sas = ký sasValues bằng delegationKey
return blob URL + "?" + sas sau khi kiểm tra quyền nghiệp vụ
```

Đây là **pseudocode**, không phải cú pháp Java hoàn chỉnh. Khi hiện thực, dùng API SDK tương ứng phiên bản đang sử dụng, truyền thời gian hết hạn và delegation key đúng kiểu dữ liệu. Không giữ delegation key hoặc SAS lâu hơn nhu cầu; hạn chế caching có thể khiến token vẫn được tái sử dụng ngoài dự kiến.

Nếu backend **không cần cung cấp URL tạm cho client** mà chỉ cần tự đọc/ghi blob, hãy gọi Blob Storage SDK trực tiếp bằng managed identity + RBAC. Việc phát hành SAS lúc này là không cần thiết và chỉ tăng thêm một bearer credential phải bảo vệ.

## 12. Bảo mật, logging và vận hành SAS

### 12.1. Kiểm soát phát hành

Tạo SAS nên là một chức năng bảo mật có owner và kiểm soát:

- Chỉ các backend/danh tính được phê duyệt mới được xin delegation key hoặc truy cập account keys.
- Mỗi request phát hành phải đi qua xác thực và kiểm tra quyền sở hữu tài nguyên.
- Giới hạn TTL, permission và tài nguyên ở cấu hình server-side; không để client tự yêu cầu `d` hoặc thời hạn tùy ý.
- Nếu có API phát hành SAS công khai, giới hạn tốc độ để chống lạm dụng.
- Có chính sách theo dõi số lượng và loại SAS đã phát hành **ở hệ thống phát hành**, vì không thể dựa vào Storage để liệt kê đầy đủ mọi SAS ad hoc từng được phát hành.

### 12.2. Truyền token an toàn

- Chỉ sử dụng HTTPS (`spr=https`).
- Không lưu SAS URL trong mã nguồn, git, ảnh chụp, dashboard, logs hoặc công cụ analytics.
- Với trang web, thiết lập chính sách tránh để URL chứa SAS bị gửi qua referrer đến website bên ngoài; cân nhắc `Referrer-Policy` và cách tải file.
- Không gửi SAS đến client trước khi kiểm tra quyền; không để token dài hạn nằm trong local storage hoặc hàng đợi công khai.
- Hạn chế `sip` khi IP client ổn định và mô hình mạng phù hợp. Với mobile client, NAT hoặc private endpoints, IP restriction có thể gây lỗi khó dự đoán nên phải thử nghiệm.
- Khi không thể tránh token trong URL, hạn chế thời gian sống và giảm khả năng ghi lại URL trong hệ thống quan sát.

### 12.3. Logging và giám sát

Azure Storage có thể cung cấp logs/metrics thông qua Azure Monitor và diagnostic settings. Khi điều tra, lưu các trường như request ID, thời điểm, endpoint, phương thức, mã lỗi và thông tin mạng phù hợp. Không ghi tham số `sig` và không công bố toàn bộ query string.

Một số câu hỏi kiểm toán:

- Hệ thống nào có quyền **List Keys** hoặc `generateUserDelegationKey/action`?
- Có SAS nào được backend phát hành với TTL vượt chính sách hay quyền ghi/xóa không?
- Việc truy cập blob có tăng đột biến từ nguồn IP lạ hoặc ngoài giờ không?
- Những luồng nào vẫn đang dùng Shared Key thay vì Microsoft Entra ID?
- Đã có kế hoạch xoay account keys và thu hồi user delegation keys khi xảy ra sự cố chưa?

Nhiều storage account hỗ trợ **SAS expiration policy** để giám sát hoặc thực thi giới hạn khoảng hiệu lực theo khả năng cấu hình của dịch vụ; hãy kiểm tra điều kiện áp dụng, loại SAS, mức độ hỗ trợ và cách xử lý `st` trước khi bật. Chính sách hết hạn không thay thế quy trình kiểm tra quyền ở backend.

### 12.4. Tác động chi phí

Việc tạo SAS không tự động tạo một lớp dịch vụ lưu trữ mới, nhưng **các thao tác Storage vẫn có chi phí** theo mô hình account: dung lượng, transaction, dữ liệu đọc/ghi và data transfer có thể phát sinh. Nếu phát hành SAS quá rộng hoặc bị lộ, lượng request ngoài dự kiến có thể tăng cả rủi ro và hóa đơn.

Khi dùng backend proxy, chi phí và năng lực xử lý của App Service/Function còn phải gánh luồng truyền file. Khi dùng SAS URL tải trực tiếp, băng thông đi từ Storage đến client nhưng cần bảo vệ chặt hơn bearer URL. Đánh giá chi phí và bảo mật đồng thời thay vì chỉ chọn phương án có ít bước nhất.

## 13. Những ngộ nhận thường gặp

**“SAS là account key ở dạng ngắn hơn.”** Sai. SAS là token có chữ ký và các điều kiện truy cập riêng. Service/account SAS dùng account key để *ký*, còn user delegation SAS dùng user delegation key.

**“Nếu dùng SAS thì người nhận phải đăng nhập Microsoft Entra ID.”** Sai trong mô hình sử dụng SAS thông thường. Người cầm SAS hợp lệ có thể gửi request theo điều kiện đã ký; Entra ID được dùng ở bước phát hành user delegation SAS chứ không bắt buộc cho client tải blob qua SAS.

**“User delegation SAS dùng được cho Azure Files, Queue và Table.”** Sai. Loại này dành cho Blob Storage và các kịch bản tương thích của Data Lake Storage Gen2. Dịch vụ Storage khác cần cơ chế xác thực được hỗ trợ riêng.

**“Có thể thu hồi ngay đúng một SAS bất kỳ.”** Không mặc định. Việc thu hồi phụ thuộc loại SAS, stored access policy, khóa ký và phạm vi tác động. User delegation SAS không hỗ trợ stored access policy.

**“Chỉ cấp Storage Blob Data Reader ở container là đủ để xin user delegation key.”** Không nhất thiết. Cần `generateUserDelegationKey/action` tại scope storage account hoặc cha.

**“Đổi role RBAC là mọi SAS cũ lập tức vô hiệu.”** Không nên giả định. Token và delegation key đã phát hành có vòng đời riêng; phải có kế hoạch hết hạn hoặc thu hồi delegation keys.

**“Có user delegation SAS là không cần kiểm tra invoice thuộc khách hàng nào.”** Sai. Authorization của ứng dụng vẫn phải xác minh người nhận được phép truy cập blob trước khi phát hành URL.

**“Tắt Shared Key sẽ chặn cả user delegation SAS.”** Với Blob Storage, không: user delegation SAS được ký dựa trên Entra ID và user delegation key; cần kiểm tra quyền và các điều kiện khác. Dù vậy, phải kiểm kê tác động lên dịch vụ/ứng dụng liên quan trước khi thay đổi account setting.

## 14. Bài tập thực hành và tình huống thiết kế

### Tình huống A: khách hàng tải hóa đơn

Ứng dụng đặt hàng cần cho khách hàng tải một PDF trong 10 phút, không cho phép liệt kê container hoặc xóa blob.

Hãy đề xuất:

1. Dùng account key trực tiếp, service SAS hay user delegation SAS?
2. Ai được xác thực trước khi phát hành token?
3. Tài nguyên, `sp`, `se`, `spr` nên có giá trị gì?
4. RBAC ở phạm vi nào cho principal phát hành?
5. Nếu URL rò rỉ khi còn 3 phút hiệu lực thì hệ thống xử lý ra sao?

**Hướng giải:** ưu tiên user delegation SAS với `sp=r`, đúng blob, HTTPS và TTL 10 phút. API xác thực khách hàng/kiểm tra quyền sở hữu hóa đơn trước khi ký. Managed identity của API cần quyền xin delegation key tại account scope và quyền đọc dữ liệu tại container phù hợp. Khi rò rỉ, cân nhắc mức độ nghiêm trọng: TTL ngắn giúp giảm thời gian lạm dụng; nếu cần thu hồi khẩn cấp, đánh giá thao tác revoke delegation keys vì có thể ảnh hưởng SAS khác.

### Tình huống B: đối tác upload tài liệu

Đối tác cần upload một tệp vào vùng lưu trữ của doanh nghiệp trong thời gian giới hạn. Nhóm bảo mật không muốn đối tác đọc hoặc liệt kê các file khác.

Hãy cân nhắc:

- Quyền tối thiểu để tạo/ghi vào đích theo API Blob thực tế, không cấp quyền Delete/List mặc định.
- Tên blob được backend cấp phát, tránh upload đè tệp có sẵn.
- TTL và kích thước file; liệu cần chia block/tiến độ upload không?
- CORS nếu client là trình duyệt; CORS **không phải** cơ chế authorization thay thế SAS.
- Quét nội dung, kiểm tra định dạng, metadata và quy trình xử lý sau upload.
- Có nên cấp SAS hay backend proxy upload để kiểm soát chặt hơn?

Không dùng `sp=w` cho toàn container trong nhiều ngày chỉ vì cần nhận một tệp. Khi upload hoàn tất, backend cần xác thực kết quả và kiểm tra dữ liệu trước khi đưa vào luồng nghiệp vụ.

### Tình huống C: hệ thống cũ đang dùng account key

Một pipeline ETL và hai ứng dụng đang dùng Shared Key; đội an ninh muốn đặt `allowSharedKeyAccess=false` cho Blob Storage.

Hãy lập kế hoạch chuyển đổi:

1. Kiểm kê các hệ thống/SDK và tất cả SAS ký bằng account key.
2. Phân loại luồng backend-to-Storage để chuyển sang Entra ID + RBAC.
3. Phân loại luồng cần chia sẻ tệp để chuyển sang user delegation SAS.
4. Kiểm tra ảnh hưởng lên Azure Files hoặc các tính năng Storage khác đang sử dụng.
5. Thử trong môi trường không production, theo dõi log/metrics, chuẩn bị rollback.
6. Thực hiện thay đổi theo quy trình phê duyệt và xác nhận luồng cũ không còn phụ thuộc key.

## 15. Câu hỏi tự kiểm tra

**1. Shared Key khác SAS ra sao?** Shared Key dùng account key có phạm vi rất rộng để xác thực request; SAS là token đã ký với phạm vi/quyền/thời hạn được khai báo.

**2. Hai loại SAS nào dùng account key để ký?** Service SAS và account SAS.

**3. User delegation SAS dành cho dịch vụ nào?** Azure Blob Storage, bao gồm các trường hợp Data Lake Storage Gen2 được hỗ trợ.

**4. Vì sao phải kiểm tra `generateUserDelegationKey/action`?** Vì đó là quyền để Entra principal yêu cầu khóa ủy quyền ở cấp Blob service/storage account, độc lập với quyền đọc blob.

**5. User delegation key có thể kéo dài vô hạn không?** Không; thời hạn tối đa là 7 ngày, và SAS dùng khóa đó không thể vượt qua thời hạn khóa.

**6. Stored access policy dùng với account SAS hoặc user delegation SAS được không?** Không; cơ chế này dành cho service SAS được hỗ trợ.

**7. Việc người nhận có SAS URL chứng minh họ có quyền nghiệp vụ đối với tệp không?** Không. Backend phải kiểm tra quyền trước khi phát hành.

**8. Muốn chặn Shared Key trên Blob Storage, điều gì cần làm trước?** Kiểm kê phụ thuộc, chuyển các client sang Entra ID/user delegation SAS, thử nghiệm và có kế hoạch xử lý sự cố.

## 16. Checklist triển khai production

- [ ] Đã chọn cơ chế: Entra ID trực tiếp, user delegation SAS, service SAS hay account SAS dựa trên yêu cầu thật.
- [ ] Đã tránh đưa storage account key và connection string chứa key vào frontend hoặc repository.
- [ ] Backend có xác thực người dùng và kiểm tra quyền nghiệp vụ trước khi phát hành SAS.
- [ ] SAS chỉ cấp resource, permissions, TTL và protocol cần thiết.
- [ ] Với user delegation SAS, principal có quyền xin key ở đúng account scope và quyền dữ liệu ở scope phù hợp.
- [ ] Không dùng stored access policy cho user delegation/account SAS.
- [ ] Đã dự trù clock skew, thời gian lan truyền RBAC, sự khác biệt DNS/firewall/private endpoint.
- [ ] Đã có quy trình kiểm kê, thu hồi, xoay vòng account key và revoke delegation keys khi cần.
- [ ] Đã hạn chế log query string/token, áp dụng HTTPS và cơ chế truyền URL an toàn.
- [ ] Đã kiểm tra rủi ro khi `allowSharedKeyAccess=false` và những dịch vụ tích hợp liên quan.
- [ ] Đã thiết lập metrics/logs, theo dõi lượt tải bất thường và xem xét chi phí giao dịch/băng thông.
- [ ] Đã kiểm thử các trường hợp được phép, không đủ quyền, hết hạn, sai URL và bị chặn mạng.

## Kết luận

**Shared Key** là cơ chế xác thực dùng khóa tài khoản Storage có đặc quyền rộng; **Shared Access Signature** là token có chữ ký để trao quyền hạn chế về hành động, phạm vi và thời gian. **Service SAS** và **account SAS** được ký bằng account key, còn **user delegation SAS** dành cho Blob Storage sử dụng khóa ủy quyền được cấp trên cơ sở Microsoft Entra ID, nên backend không cần giữ account key.

Với ứng dụng Azure hiện đại, ưu tiên **managed identity + Azure RBAC** cho kết nối backend-to-Storage; khi cần cấp quyền tạm thời cho client tải một blob, ưu tiên **user delegation SAS** với quyền tối thiểu và thời hạn ngắn. Luôn kết hợp SAS với kiểm tra quyền nghiệp vụ, bảo vệ URL, giới hạn mạng, log an toàn và kế hoạch thu hồi phù hợp với loại chữ ký đang sử dụng.
