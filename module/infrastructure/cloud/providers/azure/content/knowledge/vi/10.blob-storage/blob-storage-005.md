# Blob versioning, snapshot và soft delete

Một ứng dụng chạy trên Azure ghi các tài liệu, ảnh sản phẩm và kết quả xử lý vào Blob Storage. Vào thứ Hai, một tệp bị ghi đè bằng nội dung sai; thứ Ba, một tệp khác bị xóa; thứ Tư, quản trị viên vô tình xóa cả container. Ba sự cố tưởng giống nhau nhưng **cơ chế khôi phục phù hợp không giống nhau**: **Blob versioning** bảo toàn các phiên bản dữ liệu, **blob snapshot** chụp nội dung một blob tại thời điểm xác định, còn **soft delete** cho phép khôi phục những đối tượng đã xóa trong thời gian giữ lại được cấu hình.

Bài học thuộc chương **Lưu trữ đối tượng với Blob Storage** của module `CLOUD_PROVIDERS_AZURE`. Module bao quát Microsoft Azure từ subscription, resource group và Entra ID đến mạng ảo, tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng. Ở đây, mục tiêu là thiết kế **khả năng quay lại trạng thái dữ liệu trước sự cố**, tách biệt với quyền truy cập, tính sẵn sàng và mã hóa.

> Các ví dụ chủ yếu dùng **block blob** trong storage account loại general-purpose v2. Mức hỗ trợ versioning, snapshots, soft delete, change feed và point-in-time restore có thể khác theo loại blob, loại account, hierarchical namespace (ADLS Gen2), region và các ràng buộc dịch vụ hiện hành. Kiểm tra hỗ trợ trên tài khoản thật trước khi chốt chính sách hoặc chạy lệnh thay đổi dữ liệu.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **blob hiện hành**, **previous version**, **snapshot**, **soft-deleted blob** và **soft-deleted container**.
2. Giải thích vì sao versioning giúp bảo vệ khỏi ghi đè và vì sao snapshot không tự động được tạo trước mọi lần sửa.
3. Bật và quản lý chính sách **versioning**, **blob soft delete** và **container soft delete** cho workload được hỗ trợ.
4. Chọn đúng thao tác **undelete** hay **copy/restore từ version/snapshot** cho từng tình huống.
5. Xác định retention, RPO/RTO, giới hạn của replication và các rủi ro xóa nhầm ở cấp storage account.
6. Sử dụng Azure Portal và các lệnh Azure CLI minh họa để xem recovery points, tải bản cũ và kiểm tra cấu hình.
7. Thiết kế lifecycle management để giữ đủ phiên bản cần thiết mà không tăng chi phí vô hạn.
8. Kết hợp least privilege, logging, immutability và kiểm thử khôi phục khi yêu cầu an toàn dữ liệu cao hơn.
9. Viết runbook xử lý sự cố ghi đè/xóa blob, xóa container hoặc sửa hàng loạt mà không làm mất thêm bản còn giá trị.

## 2. Blob Storage lưu trữ dữ liệu thế nào?

Blob Storage lưu dữ liệu **object** trong các container thuộc một storage account. Một blob có **tên**, **nội dung**, **thuộc tính** và **metadata**; với tính năng được hỗ trợ, blob còn có thể có các **version** hoặc **snapshot**.

```text
Subscription / Resource group
└── Storage account: stdocumentsdemo
    ├── Container: invoices
    │   ├── 2026/invoice-001.pdf
    │   ├── 2026/invoice-002.pdf
    │   └── reports/summary.csv
    └── Container: images
        ├── products/a.png
        └── products/b.png
```

Đường dẫn `2026/invoice-001.pdf` là tên blob trong container `invoices`. Với nhiều tài khoản Blob thông thường, ký tự `/` tạo cấu trúc thư mục ảo trong cách hiển thị; không nên mặc định mọi tên blob là file trong một filesystem POSIX thực. Với hierarchical namespace (ADLS Gen2), ngữ nghĩa thư mục và tính năng khả dụng có khác biệt cần kiểm tra.

### Block blob, append blob và page blob

| Loại | Tình huống sử dụng | Lưu ý về bảo vệ phiên bản |
|---|---|---|
| **Block blob** | Tệp, hình ảnh, video, artifact, data lake objects. | Trọng tâm của ví dụ versioning và phục hồi trong bài. |
| **Append blob** | Các tình huống ghi nối tiếp dữ liệu. | Không được suy diễn có đầy đủ hành vi versioning như block blob. |
| **Page blob** | Dữ liệu truy cập ngẫu nhiên, một số workload đĩa chuyên biệt. | Snapshot/versioning và API có khác biệt; không tự áp dụng mọi lệnh block blob. |

**Điểm quan trọng:** phục hồi tệp trong Azure Files bằng *file share snapshot* là chủ đề khác; ở đây ta làm việc với **Blob Storage**, nơi version và snapshot thường được xác định **cho từng blob**.

## 3. Từ vựng nền tảng: bản hiện hành và các recovery points

| Thuật ngữ | Ý nghĩa | Định danh thường gặp |
|---|---|---|
| **Current blob** | Phiên bản blob mà một yêu cầu GET thông thường theo tên sẽ truy cập khi đối tượng còn tồn tại. | Container + blob name, không cần chỉ định version. |
| **Previous version** | Phiên bản cũ do versioning tạo ra khi dữ liệu thay đổi theo các hoạt động được hỗ trợ. | **Version ID**, thường thể hiện dạng timestamp do dịch vụ cấp. |
| **Snapshot** | Bản chụp **chỉ đọc** tại một thời điểm, thường được yêu cầu tạo rõ ràng. | **Snapshot timestamp**, phân biệt với Version ID. |
| **Soft-deleted blob/snapshot/version** | Đối tượng đã xóa nhưng còn trong thời gian giữ lại của cơ chế soft delete thích hợp. | Tên blob kết hợp thông tin xóa/version/snapshot. |
| **Soft-deleted container** | Cả container đã bị xóa và được giữ lại để có thể phục hồi nếu đã bật container soft delete. | Tên container và thông tin xóa tương ứng. |
| **Recovery point** | Một mốc dữ liệu có thể chọn để phục hồi. | Có thể là version, snapshot hoặc backup được quản lý. |

**Version ID không phải Snapshot ID.** Dù cả hai có thể được thể hiện như chuỗi thời gian, cách tạo, liệt kê, chỉ định tham số API và vòng đời của chúng khác nhau.

### Mã hóa, redundancy và dữ liệu cũ

Azure Storage Service Encryption bảo vệ dữ liệu **at rest**; LRS/ZRS/GRS/GZRS giúp tăng độ bền theo mô hình redundancy. Nhưng khi một thao tác ghi đè hoặc xóa hợp lệ được chấp nhận, bản mới hoặc trạng thái xóa có thể được sao chép. **Mã hóa và redundancy không tự thay thế versioning, snapshots hay backup lịch sử.**

## 4. Blob versioning là gì?

**Blob versioning** cho phép Azure Storage lưu các trạng thái trước của một block blob khi nội dung hoặc trạng thái blob thay đổi qua những thao tác được dịch vụ hỗ trợ. Khi tính năng được bật và blob được ghi đè, trạng thái trước có thể trở thành **previous version** với **Version ID** riêng, còn nội dung mới trở thành **current version**.

Ví dụ timeline:

```text
09:00  reports/summary.csv = A       (current)
       │
10:00  Upload ghi đè thành B
       ├── Previous version V1 = A
       └── Current = B
       │
11:00  Upload ghi đè thành C
       ├── Previous version V1 = A
       ├── Previous version V2 = B
       └── Current = C
       │
12:00  Cần lấy lại B
       └── Chọn V2, kiểm tra rồi khôi phục/copy làm bản hiện hành
```

Version ID do dịch vụ cấp, không phải tên tùy ý như `V1` hoặc `V2` trong hình. Ở API, có thể đọc một phiên bản cụ thể mà không thay đổi current blob.

### Điều versioning giải quyết tốt

- Một ứng dụng upload blob cùng tên và **ghi đè nhầm** nội dung trước đó.
- Cần tra lịch sử thay đổi nội dung để phục hồi một phiên bản cũ.
- Muốn có recovery point tự động trong quy trình cập nhật blob mà không phải nhớ tạo snapshot thủ công trước mỗi lần ghi.
- Kết hợp lifecycle policy để giữ các phiên bản cũ trong một khoảng thời gian đã thống nhất.

### Điều versioning không tự bảo đảm

- **Không phải** bản backup tách khỏi storage account.
- **Không tự chống** người có quyền cao xóa toàn bộ dữ liệu/phiên bản hoặc xóa account khi không có lớp bảo vệ khác.
- **Không thay thế** kiểm thử nhất quán ứng dụng, đặc biệt khi một giao dịch cập nhật nhiều blob.
- **Không bảo đảm** giữ phiên bản vô hạn: previous versions có thể bị xóa bằng thao tác được phép hoặc theo lifecycle/retention đã cấu hình.
- **Không đồng nghĩa** file-locking, version control kiểu Git hay transaction nhiều object.

Khi bật versioning trên một account đã có dữ liệu, **đừng giả định hệ thống sẽ tự tạo lịch sử các phiên bản đã tồn tại từ trước thời điểm bật**. Hãy ghi nhận thời điểm chính sách bắt đầu có hiệu lực.

## 5. Blob snapshot là gì?

**Blob snapshot** là bản chụp chỉ đọc của một blob ở một thời điểm được chỉ định. Snapshot thường được tạo rõ ràng bởi người vận hành, SDK, công cụ hoặc workflow, thay vì tự sinh ra bởi từng lần upload như versioning.

Ví dụ trước khi cập nhật file cấu hình:

```text
14:00  configs/appsettings.json = A
       │
14:05  Tạo snapshot S1      → S1 = A
       │
14:10  Deploy ghi current = B
       │
14:15  Phát hiện B sai
       └── Lấy S1 để so sánh, rồi khôi phục bản A theo quy trình
```

Snapshot hữu ích khi bạn cần **chủ động đóng băng một mốc** trước khi thay đổi dự kiến có rủi ro, như nâng cấp ứng dụng, sửa file dữ liệu hoặc chạy tác vụ chuyển đổi.

### Snapshot không phải bản copy hoàn chỉnh độc lập

Azure quản lý snapshot theo cơ chế lưu dữ liệu thay đổi và tái sử dụng phần dữ liệu không đổi theo mô hình dịch vụ. Vì vậy tạo snapshot có thể nhanh và tiết kiệm hơn nhân bản một blob lớn trong nhiều tình huống, nhưng **dữ liệu lịch sử vẫn phát sinh chi phí lưu trữ** theo thay đổi và thời gian giữ lại.

Snapshot **gắn với blob trong storage account nguồn**. Không xem việc có snapshot là bằng chứng bạn đã có bản sao ở account, subscription hay region độc lập.

### Bản chụp chỉ đọc

Bạn không sửa nội dung của chính snapshot như sửa current blob. Muốn quay về nội dung snapshot, cần **sao chép nội dung snapshot** về một blob đích hoặc sử dụng thao tác restore được hỗ trợ. Khi restore đè tên hiện hành, thao tác đó có thể tạo thêm lịch sử version nếu versioning bật.

### Snapshot khác versioning

| Tiêu chí | Versioning | Snapshot |
|---|---|---|
| Khi nào tạo | Tự động qua những thao tác thay đổi blob được hỗ trợ khi đã bật. | Theo yêu cầu tạo snapshot rõ ràng. |
| Định danh | Version ID. | Snapshot timestamp. |
| Trường hợp thường gặp | Bảo vệ khi ghi đè ngoài ý muốn. | Đánh dấu mốc trước deploy, di chuyển hoặc chỉnh dữ liệu. |
| Phạm vi | Các phiên bản của từng blob; phụ thuộc cấu hình account. | Một blob tại một thời điểm. |
| Vòng đời | Giữ/xóa previous versions theo policy và thao tác được phép. | Quản lý snapshot retention/xóa bằng policy và thao tác được phép. |
| Có phải backup độc lập? | Không. | Không. |

Không dùng thuật ngữ “snapshot” để chỉ mọi previous version: cơ chế và các tham số phục hồi cụ thể khác nhau.

## 6. Soft delete: “xóa” chưa chắc là xóa vĩnh viễn

**Blob soft delete** giúp bảo vệ những blob, snapshot hoặc version bị xóa theo các điều kiện được tính năng hỗ trợ bằng cách giữ lại dữ liệu trong **thời gian retention** được cấu hình. Trong khoảng này, đối tượng có thể khôi phục theo các thao tác phù hợp; sau khi hết thời gian hoặc khi đối tượng bị xóa vĩnh viễn qua một cơ chế được phép, khả năng khôi phục có thể mất.

Cần tách rõ hai tính năng:

1. **Blob soft delete:** tập trung vào các blob/versions/snapshots bị xóa trong container.
2. **Container soft delete:** bảo vệ trường hợp **xóa cả container** trong thời hạn giữ lại.

Bật blob soft delete **không đồng nghĩa** container soft delete đã được bật. Một thao tác xóa container có thể cần cơ chế phục hồi khác với thao tác xóa một blob.

### Ví dụ sự cố xóa blob

```text
09:00  images/products/a.png đang tồn tại
09:30  Tác vụ dọn dữ liệu xóa nhầm a.png
10:00  Phát hiện sự cố
       |
       ├── Blob soft delete còn retention?
       |      └── Có: kiểm tra cách undelete/restore được hỗ trợ
       |
       └── Nếu có previous versions:
              chọn phiên bản sạch → copy/promote thành current
```

**Điểm cần kiểm tra:** cách khôi phục khác nhau giữa account **có versioning** và account **không có versioning**. Với versioning, xóa current blob có thể khiến nó không còn current version nhưng các previous versions vẫn tồn tại; để phục hồi một nội dung cũ thành current, thường phải **copy một version còn hợp lệ**. Không mặc định lệnh `undelete` luôn tự biến phiên bản mong muốn thành bản hiện hành.

### Thời gian giữ lại

Retention là khoảng thời gian cơ chế soft delete giữ đối tượng đã xóa để có thể phục hồi. Ví dụ tổ chức chọn **30 ngày** cho blob soft delete và **14 ngày** cho container soft delete; đây là **chính sách minh họa**, không phải mặc định Azure áp dụng cho mọi tài khoản.

Cần đánh giá:

- Thường mất bao lâu mới phát hiện việc xóa nhầm?
- Có cần phục hồi dữ liệu đã bị hỏng từ một tháng trước không?
- Khoảng retention có đáp ứng RPO/RTO, kiểm toán hoặc hợp đồng không?
- Các versions/snapshots và backup khác có đang bị lifecycle policy dọn sớm hơn nhu cầu không?
- Chi phí giữ các object đã xóa trong retention có được dự toán không?

Không giả định tăng retention hôm nay sẽ **khôi phục được** đối tượng đã bị xóa vĩnh viễn hoặc đã hết retention trước khi thay đổi.

## 7. Tình huống kết hợp versioning, snapshot và soft delete

Một kiến trúc thực tế thường bật **nhiều lớp cùng lúc**, bởi các cơ chế bảo vệ trước những sự cố khác nhau.

| Sự cố | Cơ chế ưu tiên | Cần xác minh |
|---|---|---|
| Upload ghi đè blob bằng nội dung sai | **Previous version** nếu versioning đã bật; snapshot trước đó nếu có. | Có version/snapshot trước lúc sai không, còn trong retention không? |
| Cần đóng băng trạng thái trước nâng cấp | **Snapshot** chủ động. | Đúng tên blob, timestamp và đủ các blob liên quan? |
| Xóa nhầm một blob, không bật versioning | **Blob soft delete** nếu được bật và còn retention. | Blob còn trong danh sách soft-deleted; undelete hợp lệ? |
| Xóa nhầm current blob khi có versioning | **Previous version** và thao tác copy/promote phù hợp; kiểm tra soft delete cho versions bị xóa. | Version ID, trạng thái current và quy tắc xóa phiên bản. |
| Xóa nhầm toàn bộ container | **Container soft delete** nếu được bật, hoặc backup độc lập. | Container có trong danh sách deleted containers và còn retention? |
| Tất cả blob bị sửa trong vài phút | Lựa chọn nhiều previous versions hoặc tính năng **point-in-time restore** khi hỗ trợ và đã cấu hình. | Phạm vi, thời điểm sạch, change feed và yêu cầu tính năng. |
| Storage account bị xóa/không còn khả dụng | **Backup/tầng bảo vệ độc lập** nếu đã cấu hình. | Có bản sao độc lập không, restore target hợp lệ không? |
| Ransomware mã hóa nội dung | Versions/snapshots sạch, backup độc lập, bảo vệ immutable theo nhu cầu. | Recovery point có trước lúc tấn công và không bị kẻ tấn công xóa? |

Không nên dùng một câu trả lời chung như “hãy bật soft delete là đủ”. Với workload quan trọng, cần **lớp tự động chống ghi đè + lớp chống xóa + bản sao độc lập hoặc bất biến phù hợp** và runbook kiểm thử.

## 8. Khác biệt giữa xóa current blob và xóa previous version

Đây là điểm dễ nhầm trong xử lý sự cố:

- Khi **versioning tắt**, xóa một blob có thể đưa blob vào trạng thái soft-deleted nếu blob soft delete bật; việc undelete có thể phục hồi blob theo cơ chế hỗ trợ.
- Khi **versioning bật**, thao tác xóa current blob thường để lại dữ liệu trong các phiên bản trước, và **không có current blob** sau thao tác đó. Muốn phục hồi current, cần chọn một previous version phù hợp rồi **copy trở lại tên blob gốc**.
- Khi **xóa một phiên bản cụ thể**, nếu soft delete và thao tác xóa phiên bản đó được hỗ trợ, thời gian giữ lại và hành vi phục hồi có thể khác với xóa current blob.
- **Permanent deletion** hoặc xóa theo policy có thể loại bỏ cơ hội khôi phục; cần hiểu quyền và retention trước khi thao tác.

### Vì sao “đã undelete” nhưng GET blob vẫn báo 404?

Có thể bạn đã phục hồi các đối tượng phụ trợ/versions trong phạm vi soft delete nhưng **chưa tạo lại một current version** tại tên blob. Cần kiểm tra danh sách versions rồi chọn phiên bản đúng để copy/promote thành current.

Đừng sửa lỗi bằng cách upload một file trống lên đúng tên trước khi xác nhận phiên bản cần khôi phục: điều đó có thể tạo thêm version và làm việc điều tra phức tạp hơn.

## 9. Điểm khôi phục nhất quán của nhiều blob

Một blob version/snapshot là mốc dữ liệu **của một object**. Nếu một ứng dụng đồng thời cập nhật `orders.json`, `customers.json` và `manifest.json`, lấy “version gần nhất” của mỗi file có thể tạo ra một trạng thái **không nhất quán**.

Ví dụ:

```text
10:00  orders = A        customers = A        manifest = A
10:05  orders = B
10:06                    customers = B
10:07                                         manifest = B
10:08  Hoàn tất một lần publish dữ liệu hợp lệ
```

Nếu lỗi ở 10:06, việc chọn phiên bản bất kỳ có thể trộn A/B. Để khôi phục cả một tập dữ liệu:

1. Thiết kế ứng dụng xuất dữ liệu theo **job ID/versioned directory** hoặc mô hình manifest/commit marker.
2. Ghi lại tập Version ID hoặc snapshot timestamps thuộc **cùng một lần publish hợp lệ**.
3. Khi có sự cố, chọn trạng thái đã được xác nhận nhất quán thay vì “mới nhất của từng blob”.
4. Khôi phục vào **container/prefix thử nghiệm**, kiểm tra kết quả nghiệp vụ rồi mới chuyển luồng đọc.
5. Nếu yêu cầu phục hồi về một thời điểm trên phạm vi container/account, đánh giá **point-in-time restore** cho loại dữ liệu được hỗ trợ.

Versioning không tự cung cấp ACID transaction bao trùm hàng nghìn blob; ứng dụng vẫn phải quản lý tính nhất quán logic.

## 10. Point-in-time restore là tính năng bổ sung

**Point-in-time restore (PITR) cho block blobs**, trong những tài khoản và cấu hình được hỗ trợ, có thể hỗ trợ đưa một phạm vi block blobs về trạng thái ở thời điểm trước đó. Nó khác việc chọn một previous version hoặc một snapshot cụ thể.

PITR thường có các **điều kiện tiên quyết**, như sự phối hợp với **versioning, change feed và soft delete**, cùng giới hạn về loại account, namespace, phạm vi restore và retention. Những điều kiện này thay đổi theo tính năng hiện hành: hãy kiểm tra khả năng hỗ trợ trong Azure Portal và tài liệu dịch vụ trước khi lập kế hoạch.

Không nên coi “đã bật versioning” là “PITR đã sẵn sàng”. Nếu chưa bật tính năng hoặc thời gian có thể phục hồi không bao phủ sự cố, không thể tự động khôi phục quá khứ bằng PITR.

### Khi nên dùng PITR?

- Một script lỗi ghi đè hàng nghìn block blobs trong một khoảng ngắn.
- Cần phục hồi một phạm vi đã được xác định về mốc sạch nhất quán theo khả năng tính năng.
- Có kế hoạch kiểm tra tác động đến dữ liệu mới, phạm vi restoration, và đủ thời gian để hoàn thành job.

Khi một ứng dụng đang ghi dữ liệu liên tục, phải cân nhắc **quiesce/đóng băng ghi** và cách xử lý các thay đổi phát sinh trong lúc restore. Không chạy PITR trực tiếp trên Production nếu chưa đánh giá phạm vi và khả năng ghi đè dữ liệu hợp lệ.

## 11. Cấu hình chính sách bảo vệ trong Azure Portal

Các bước sau mô tả một storage account **hỗ trợ tính năng** và chỉ nên thực hiện trong subscription được phép. Cách bố trí menu có thể khác theo giao diện Portal.

### Bước 1: Chọn đúng account và workload

1. Mở [Azure Portal](https://portal.azure.com/) và xác nhận tenant/subscription.
2. Mở **Storage accounts**, chọn account chứa Blob Storage.
3. Xem **Account kind**, redundancy, access tier và việc bật hierarchical namespace nếu có.
4. Đối chiếu loại blob, workload và yêu cầu bảo vệ với các tính năng tương thích.

### Bước 2: Vào Data protection

1. Từ storage account, tìm **Data protection** hoặc nhóm cài đặt bảo vệ dữ liệu phù hợp.
2. Trong mục dành cho blobs, xem **Enable versioning for blobs**, **Enable soft delete for blobs**, **Enable soft delete for containers** và các lựa chọn khác nếu được hỗ trợ.
3. Bật versioning cho những workload cần lưu lịch sử ghi đè.
4. Đặt retention blob soft delete và container soft delete theo yêu cầu.
5. Nếu cần PITR, kiểm tra và cấu hình thêm các điều kiện tiên quyết/tính năng hỗ trợ.
6. Lưu thay đổi và đọc lại cấu hình để xác nhận.

**Lưu ý:** bật tính năng ở cấp account có thể ảnh hưởng dữ liệu và chi phí của nhiều container. Trước khi bật cho tài khoản Production, cần dự toán dung lượng previous versions/snapshots và xem lifecycle policies hiện có.

### Bước 3: Thử với container riêng

1. Tạo một container lab, ví dụ `recovery-lab`.
2. Upload một blob thử `reports/weekly.csv` chứa nội dung A.
3. Ghi đè bằng nội dung B; xem phần **Versions** để xác minh phiên bản trước.
4. Tạo **snapshot** và ghi lại timestamp.
5. Xóa blob thử, kiểm tra current blob và các previous versions/soft-deleted entries.
6. Phục hồi theo đúng cơ chế, xác minh nội dung bằng download.
7. Dọn dữ liệu lab sau khi xác nhận không còn yêu cầu retention/immutable policy.

Không thử trên dữ liệu khách hàng thật, không chạy xóa hàng loạt và không thay đổi chính sách account đang dùng chung mà chưa có phê duyệt.

## 12. Azure CLI: kiểm tra cấu hình account

Dùng Azure CLI để quan sát bảo vệ Blob Storage. Các lệnh dưới đây chủ yếu là **read-only**, ngoại trừ ví dụ tạo snapshot và thay đổi chính sách được đánh dấu rõ ràng.

### Xác nhận context

```bash
az account show \
  --query "{Subscription:id,Tenant:tenantId,Name:name}" \
  --output table
```

Kiểm tra đúng subscription và tenant trước khi làm việc với storage account.

### Đọc cấu hình data protection

```bash
az storage account blob-service-properties show \
  --account-name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --output json
```

Trong JSON, tìm những trường liên quan đến:

- `isVersioningEnabled` hoặc tên thuộc tính versioning của API hiện hành.
- `deleteRetentionPolicy` và retention của blob soft delete.
- `containerDeleteRetentionPolicy` cho container soft delete.
- `restorePolicy` và `changeFeed` nếu các tính năng này hiện diện.
- Những thuộc tính khác theo tài khoản, SDK và phiên bản CLI.

Không đánh giá trạng thái chỉ bằng việc một trường **vắng mặt**. Tên/schema có thể thay đổi; kiểm tra phiên bản CLI hoặc cấu hình Portal nếu cần.

### Kiểm tra container và blob theo quyền dữ liệu

```bash
az storage container list \
  --account-name "<STORAGE_ACCOUNT>" \
  --auth-mode login \
  --output table

az storage blob list \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "recovery-lab" \
  --auth-mode login \
  --output table
```

Lệnh đọc data plane với `--auth-mode login` cần tài khoản đã đăng nhập có **Azure RBAC data role** phù hợp, ví dụ `Storage Blob Data Reader` hoặc cao hơn. Quyền quản lý account ở Azure control plane **không mặc nhiên** cho phép đọc nội dung blob qua Microsoft Entra OAuth.

### Liệt kê versions và snapshots

Azure CLI có tùy chọn `--include` cho các loại bản ghi bổ sung. Các giá trị ký hiệu và cách nhập có thể khác theo phiên bản CLI; trong một số phiên bản, `v` dùng cho versions và `s` dùng cho snapshots.

```bash
az storage blob list \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "recovery-lab" \
  --include v \
  --auth-mode login \
  --output json

az storage blob list \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "recovery-lab" \
  --include s \
  --auth-mode login \
  --output json
```

Xem kỹ tên blob, version ID, snapshot timestamp, trạng thái hiện hành và các bản đã xóa. Không coi `--include v` là cách bảo đảm hiển thị **tất cả soft-deleted objects**; cần tùy chọn deleted items được CLI/API hỗ trợ và quyền phù hợp khi điều tra xóa.

Để xác minh cú pháp thực tế, sử dụng:

```bash
az storage blob list --help
```

## 13. Azure CLI: tạo snapshot và tải một bản cũ

Phần này dùng **container lab đã được phép**, không chạy trên blob Production quan trọng.

### Tạo snapshot (thay đổi dữ liệu metadata)

Khi blob hiện hành có sẵn:

```bash
az storage blob snapshot \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "recovery-lab" \
  --name "reports/weekly.csv" \
  --auth-mode login \
  --output json
```

Ghi lại trường snapshot timestamp từ kết quả. Snapshot tạo **recovery point** và có thể phát sinh chi phí lưu trữ, nhưng không tự mã hóa lại dữ liệu thành bản sao độc lập.

### Tải blob snapshot để kiểm tra

```bash
az storage blob download \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "recovery-lab" \
  --name "reports/weekly.csv" \
  --snapshot "<SNAPSHOT_TIMESTAMP>" \
  --file "./weekly-from-snapshot.csv" \
  --auth-mode login
```

Tệp đích ở **máy chạy CLI**, không ghi đè current blob. Đừng tải dữ liệu nhạy cảm xuống thiết bị cá nhân không được tổ chức quản lý.

### Tải một previous version

```bash
az storage blob download \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "recovery-lab" \
  --name "reports/weekly.csv" \
  --version-id "<VERSION_ID>" \
  --file "./weekly-from-version.csv" \
  --auth-mode login
```

`--snapshot` và `--version-id` đại diện cho **hai kiểu định danh khác nhau**. Không truyền cả hai cho cùng một yêu cầu nếu công cụ/API không cho phép.

### Khôi phục làm current: ý tưởng an toàn

Sau khi tải bản cũ, ưu tiên:

1. Kiểm tra checksum/nội dung của bản cũ và đối chiếu owner dữ liệu.
2. Tạo một **blob đích khác** như `restored/weekly-reviewed.csv` để cho người dùng kiểm chứng.
3. Chỉ khi được phê duyệt mới copy/ghi đè vào tên `reports/weekly.csv`.
4. Nếu versioning bật, xác minh có **current version mới** và bản lịch sử cần giữ vẫn còn.
5. Ghi lại Version ID hoặc timestamp nguồn, người thực hiện và thời điểm thao tác.

Cũng có thể dùng các thao tác **server-side copy** từ version/snapshot được hỗ trợ để tránh tải dữ liệu về máy quản trị. Cú pháp phụ thuộc nguồn/đích, tài khoản, xác thực và API: kiểm tra `az storage blob copy --help` hoặc SDK đang dùng thay vì ghép URL tùy ý rồi đưa secret vào script.

## 14. Xóa và undelete một blob: chọn đúng thao tác

Ví dụ blob `reports/weekly.csv` bị xóa lúc 10:00. Việc đầu tiên là **không vội upload lại một file rỗng** hoặc xóa những phiên bản còn thấy.

### Trường hợp A: Không bật versioning, có blob soft delete

Trong Portal hoặc API phù hợp:

1. Bật chế độ hiển thị soft-deleted blobs.
2. Tìm đúng container/blob và thời gian xóa.
3. Kiểm tra blob còn retention hay không.
4. Thực hiện **Undelete** để phục hồi nếu tình huống và loại blob được hỗ trợ.
5. Xác minh bằng cách download/đọc lại nội dung.

Ví dụ CLI minh họa trong account hỗ trợ:

```bash
az storage blob undelete \
  --account-name "<STORAGE_ACCOUNT>" \
  --container-name "recovery-lab" \
  --name "reports/weekly.csv" \
  --auth-mode login
```

Lệnh này **thay đổi trạng thái dữ liệu**. Chỉ chạy khi đã xác minh blob cần phục hồi và quyền dữ liệu cho phép.

### Trường hợp B: Có versioning

1. Liệt kê các previous versions của blob.
2. Chọn Version ID đúng mốc thời gian **trước khi sự cố xảy ra**.
3. Xem/tải về bản đó để xác nhận dữ liệu.
4. **Copy/promote** nội dung được chọn trở lại tên hiện hành theo thao tác được hỗ trợ.
5. Xác minh current blob truy cập được; kiểm tra version history và quyền của ứng dụng.

Nếu thao tác xóa một version riêng biệt đã tạo soft-deleted version, cần kiểm tra điều kiện phục hồi version đó. **Undelete và promote không phải một thao tác đồng nghĩa**.

### Trường hợp C: Đã hết retention hoặc bị xóa vĩnh viễn

Nếu không còn version/snapshot/soft-deleted entry hợp lệ, không có cơ chế nội tại nào bảo đảm phục hồi. Cần tìm nguồn khác: bản sao độc lập, backup, object replication với dữ liệu còn nguyên hoặc artifact gốc của ứng dụng. Không hứa có thể phục hồi mọi blob chỉ vì storage account đang bật GRS.

## 15. Xóa container: phải có container soft delete

Khi ai đó xóa container `invoices`, các thao tác phục hồi **một blob** có thể không truy cập được vì container nguồn đã biến mất. Nếu **container soft delete** đã được bật trước đó và container còn trong retention, Azure Storage có thể cho phép **restore/undelete container** theo API/Portal được hỗ trợ.

Quy trình:

1. Xác nhận storage account còn tồn tại và lỗi không chỉ do quyền hoặc DNS/network.
2. Kiểm tra account đã bật container soft delete ở thời điểm xóa chưa.
3. Xem danh sách **deleted containers**, đối chiếu tên và thời điểm.
4. Chọn đúng container để phục hồi theo thao tác được hỗ trợ.
5. Xác minh container hiện diện và blob dữ liệu/metadata/permissions theo nhu cầu ứng dụng.
6. Kiểm tra current blobs, versions, snapshots và soft-deleted entries nếu trước đó dùng nhiều lớp bảo vệ.
7. Ghi lại thay đổi, thời gian khôi phục và biện pháp ngăn xóa nhầm.

**Không bật container soft delete sau sự cố rồi kỳ vọng khôi phục được một container đã bị xóa trước đó.** Cơ chế bảo vệ chỉ có ích khi chính sách đã có hiệu lực trước thao tác xóa tương ứng.

## 16. Lifecycle management: giữ dữ liệu cũ nhưng không giữ vô hạn

Khi versioning và snapshots được dùng rộng rãi, **dung lượng lịch sử** có thể tăng nhanh. Azure Blob lifecycle management cho phép đặt các rule theo điều kiện như tuổi dữ liệu, loại blob và phạm vi prefix/tags được hỗ trợ để **chuyển access tier hoặc xóa** những đối tượng thuộc phạm vi cho phép.

Các nhóm đối tượng có thể được quản lý theo cách khác nhau:

- **Base/current blobs**.
- **Previous versions**.
- **Snapshots**.

Không giả định một rule đặt cho current blobs tự áp dụng giống hệt cho snapshots và versions. Phải xem **filters, actions, điều kiện age và loại object** trong policy thật.

### Ví dụ chính sách minh họa

Tổ chức muốn:

| Nhóm dữ liệu | Mục tiêu giữ bản | Phương án |
|---|---|---|
| Artifacts tạm | Bản hiện hành 30 ngày; ít cần lịch sử | Rule xóa theo lifecycle sau khi được phép. |
| Hóa đơn | Previous versions tối thiểu 90 ngày theo yêu cầu nghiệp vụ | Versioning + rule retention rõ ràng; kiểm tra điều kiện luật/quy định. |
| Cấu hình ứng dụng | Snapshot trước mỗi lần deploy, giữ các mốc đáng chú ý | Snapshot có tên/quy trình và lifecycle theo ngày tạo. |
| Dataset nghiên cứu | Giữ lịch sử theo release, không giữ mọi bước trung gian | Versioning hoặc export định kỳ vào prefix/versioned dataset riêng. |

Đây là **mục tiêu thiết kế**, không phải một policy đã được chạy và kiểm chứng. Khi yêu cầu pháp lý quy định giữ dữ liệu lâu hơn, lifecycle phải tuân theo luật và chính sách tổ chức.

### Dọn bản cũ có thể gây mất khả năng phục hồi

Ví dụ retention mềm là 30 ngày nhưng lifecycle xóa previous versions sau 7 ngày: sự cố ghi đè bị phát hiện sau 15 ngày có thể **không còn previous version**, dù blob soft delete vẫn giữ một số đối tượng bị xóa theo cơ chế riêng. Vì vậy phải kiểm tra cả:

- thời điểm tạo các versions/snapshots;
- các action xóa có thể tác động lên chúng;
- xung đột giữa rule và retention;
- trạng thái immutable/hold nếu có;
- lượng dữ liệu thay đổi hằng ngày.

**Lifecycle không thay thế backup**; nó quản lý vòng đời object, kể cả hành động xóa có thể ảnh hưởng recovery points.

## 17. Cost model: vì sao versioning có thể đắt?

Giả sử một blob 10 GiB được cập nhật lại mỗi ngày. Nếu mỗi ngày ứng dụng thay đổi phần lớn nội dung và giữ 30 previous versions, dữ liệu lịch sử có thể lớn đáng kể so với chỉ 10 GiB của bản hiện hành.

Dùng ví dụ minh họa:

- Dung lượng current blob: 10 GiB.
- Mỗi lần cập nhật làm phát sinh **xấp xỉ 4 GiB dữ liệu thay đổi cần giữ** theo mô hình giả định.
- Giữ 20 lần cập nhật trước.

```text
Dữ liệu lịch sử ước tính ≈ 20 × 4 GiB = 80 GiB
Tổng current + lịch sử ≈ 10 + 80 = 90 GiB
```

Đây là phép tính **minh họa**, không phải quy tắc tính phí chính thức: dung lượng snapshot/version thực tế phụ thuộc loại blob, kiểu thay đổi, cách dịch vụ lưu trữ, access tier và cơ chế tính phí áp dụng.

Ngoài dung lượng:

- Giao dịch tạo/đọc/xóa versions hoặc snapshots có thể phát sinh phí.
- Dữ liệu ở tier khác nhau có chi phí lưu trữ, truy xuất và các điều kiện tối thiểu khác nhau.
- Replication, điểm lưu trữ độc lập và egress có thể làm tăng tổng chi phí.
- Lifecycle có thể giúp kiểm soát tăng trưởng nhưng phải tránh xóa bản còn cần.

Để dự toán thật, dùng Azure Pricing Calculator, dữ liệu change rate thực tế, số objects, retention và mức giá đúng region/SKU. **Đừng tối ưu chi phí bằng cách giảm retention mà chưa đối chiếu thời gian phát hiện sự cố của tổ chức.**

## 18. Bảo mật: hạn chế khả năng xóa recovery points

Nếu một tài khoản ứng dụng có quyền ghi/xóa mọi blob và người dùng quản trị có quyền thay đổi chính sách data protection, versioning và soft delete chỉ bảo vệ ở mức nhất định. Để giảm thiểu rủi ro:

1. Dùng Microsoft Entra ID và **Azure RBAC** theo nguyên tắc **least privilege** cho cả control plane và data plane.
2. Tránh chia sẻ account key, SAS không giới hạn hoặc credential có quyền xóa khi chỉ cần đọc.
3. Tách **nhóm quản trị cấu hình storage** khỏi nhóm **ứng dụng chỉ cần thao tác dữ liệu**.
4. Giới hạn truy cập mạng bằng private endpoints/firewall khi yêu cầu.
5. Bật và giám sát log cho các thao tác tạo/xóa object, thay đổi retention, lifecycle và role assignments.
6. Đánh giá **immutable storage** và **legal hold** cho dữ liệu cần chống sửa/xóa theo chính sách.
7. Có bản backup/replica độc lập hơn ở cấp account/region nếu bài toán yêu cầu khôi phục khỏi sự cố lớn.
8. Dùng cơ chế phê duyệt/PIM/MFA cho quyền quản trị cao khi được tổ chức hỗ trợ.

### Immutability không phải soft delete

| Tính năng | Mục tiêu |
|---|---|
| Versioning | Lưu các trạng thái cũ của blob qua thay đổi. |
| Snapshot | Đóng băng một mốc blob theo yêu cầu. |
| Soft delete | Cho phép phục hồi object/container bị xóa trong retention. |
| **Immutability policy / legal hold** | Hạn chế sửa/xóa dữ liệu được bảo vệ theo quy tắc và khả năng dịch vụ. |
| Backup độc lập | Tăng khả năng phục hồi khi tài nguyên nguồn không còn hoặc bị phá hủy. |

Version-level immutability và các lựa chọn WORM/retention lock có các giới hạn về account, container, versions/snapshots và thao tác quản trị. Không bật trong Production khi chưa hiểu tác động tới xóa, lifecycle, chi phí và khả năng thay đổi chính sách. **Bản immutable không tự bảo đảm ứng dụng phục hồi được** nếu thiếu quyền, runbook hoặc hệ thống đích.

### Nguồn nhật ký phù hợp

- **Azure Activity Log:** thay đổi control plane của storage account, policy hoặc cấu hình tài nguyên.
- **Storage resource logs/diagnostic settings:** thao tác data plane và mã lỗi khi nguồn log được bật, có thể gửi Log Analytics/Storage/Event Hubs.
- **Azure Monitor metrics:** giao dịch, lỗi, dung lượng và lưu lượng theo khả năng thu thập.
- **Microsoft Entra sign-in/audit logs:** truy vết hoạt động danh tính và thay đổi quản trị Entra khi liên quan.

Không mặc định Azure Activity Log có nội dung mọi lần upload/xóa blob. Phải cấu hình **data-plane logging** nếu cần điều tra thao tác ở mức blob.

## 19. Recovery runbook: tìm bản đúng trước khi khôi phục

Khi người dùng báo “file bị hỏng”:

1. **Xác nhận object:** storage account, container, blob name, loại blob và time zone.
2. **Khoanh vùng thời gian:** hỏi lần cuối dữ liệu còn đúng, thời điểm phát hiện và các lần deploy/job gần nhất.
3. **Tránh gây hại thêm:** tạm dừng job ghi đè/xóa liên quan; giữ nguyên versions/snapshots hiện có.
4. **Kiểm tra Data protection:** versioning/soft delete/container soft delete/PITR/retention đã được bật khi sự cố xảy ra chưa?
5. **Liệt kê recovery points:** current blob, Version IDs, snapshot timestamps, soft-deleted items.
6. **Chọn bản sạch:** so sánh nội dung và metadata, tránh dùng mốc sau khi dữ liệu đã hỏng.
7. **Khôi phục sang đích khác trước:** tải/copy về `restored/<incident-id>/...` hoặc container cô lập.
8. **Xác minh:** checksum, cấu trúc file, quyền truy cập, nội dung nghiệp vụ, các blob liên quan.
9. **Phê duyệt và chuyển đổi:** copy/promote thành current hoặc thay đổi manifest/đường dẫn ứng dụng khi an toàn.
10. **Theo dõi sau restore:** xác nhận client GET được đúng nội dung, không bị cache/CDN trả bản cũ và job ghi không tái tạo lỗi.
11. **Ghi bằng chứng:** nguồn, Version ID/timestamp, thời gian, người thực hiện và kết quả kiểm thử.
12. **Ngăn tái diễn:** điều chỉnh policy, quyền, lifecycle và cơ chế kiểm soát ứng dụng.

### Vì sao kiểm tra cache/CDN?

Ngay cả khi current blob đã được phục hồi, ứng dụng có thể tiếp tục thấy nội dung cũ hoặc sai do **cache của client, proxy hay CDN**. Cần kiểm tra URL, ETag, Cache-Control và cách ứng dụng invalidation; đừng lặp lại thao tác restore chỉ vì cache chưa hết hạn.

### Restore vào tên gốc có thể thay đổi metadata

Một số cách copy/restore có thể ảnh hưởng metadata, content type, tags, ACL/authorization semantics, ETag hoặc thời điểm sửa. Runbook phải kiểm tra những thuộc tính quan trọng cho ứng dụng, không chỉ so sánh bytes.

## 20. Tình huống thực tế A: upload ghi đè báo cáo

**Hiện tượng:** Ứng dụng phân tích xuất `reports/weekly.csv` lúc 09:00 với dữ liệu đúng, nhưng job lúc 10:00 ghi đè bằng một bảng thiếu dòng.

**Điều tra:**

1. Xác minh container, blob name và mốc thời gian.
2. Mở **Versions** của blob nếu account đã bật versioning.
3. Chọn previous version trước 10:00, tải về và so sánh số dòng/hash.
4. Kiểm tra có bản snapshot chủ động trước job không.
5. Đưa bản đúng vào prefix phục hồi, nhờ owner dữ liệu phê duyệt.
6. Copy/promote trở lại current, theo dõi job tiếp theo.

**Kết luận:** versioning thường nhanh và trực tiếp hơn khi bảo vệ khỏi ghi đè; snapshot cũng dùng được nếu bản phù hợp đã được tạo. Soft delete không nên được coi là cơ chế duy nhất cho ghi đè, đặc biệt khi chưa có lịch sử phiên bản.

## 21. Tình huống thực tế B: xóa nhầm một blob và một container

**Hiện tượng:** script dọn dẹp xóa `images/products/a.png` rồi xóa luôn container `images-archive`.

**Điều tra và xử lý:**

- Với `a.png`: kiểm tra versioning/soft delete, danh sách previous versions hoặc deleted blobs và retention.
- Với `images-archive`: kiểm tra **container soft delete** và danh sách deleted containers.
- Nếu không có phiên bản/soft-deleted object còn hạn, tìm bản sao ngoài nguồn hoặc artifact pipeline.
- Sau khi restore, xác minh URL/cấu hình ứng dụng, quyền và CDN cache.

**Bài học:** blob soft delete và container soft delete phải được xem là **hai thiết lập riêng**. Test khôi phục một blob không chứng minh đã có bảo vệ cho thao tác xóa cả container.

## 22. Tình huống thực tế C: một job làm hỏng hàng nghìn blobs

**Hiện tượng:** script triển khai sai cấu hình ghi đè 8.000 JSON blobs trong container `datasets`. Các blob tạo vào nhiều thời điểm, và một số dữ liệu mới sau sự cố vẫn hợp lệ.

Cách ứng phó:

1. Dừng script gây lỗi, đóng băng luồng ghi có nguy cơ tiếp tục phá dữ liệu.
2. Xác định phạm vi prefix/blob và mốc thời gian bắt đầu bị sai.
3. Nếu đã cấu hình **PITR** đáp ứng điều kiện, đánh giá phạm vi restore và tác động tới thay đổi hợp lệ.
4. Nếu không có PITR, xây danh sách version ID sạch của từng blob từ manifest/log trước khi copy.
5. Khôi phục một mẫu vào container riêng, so sánh schema, record count và hash.
6. Lập kế hoạch phục hồi hàng loạt có kiểm soát, theo dõi lỗi và khả năng rollback.
7. Kiểm tra liệu lifecycle rule đã dọn một phần versions cần thiết chưa.
8. Mở lại ứng dụng sau khi xác nhận dữ liệu và kiểm thử end-to-end.

**Không khôi phục hàng loạt mù quáng theo “version gần nhất”** khi job sai có thể đã ghi nhiều lần; có blob cần quay lại hơn một phiên bản và có blob không nên thay đổi.

## 23. RPO/RTO, backup và kế hoạch chịu sự cố lớn

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa có thể mất tính theo thời điểm recovery point.
- **RTO (Recovery Time Objective):** thời gian tối đa đến khi ứng dụng sử dụng dữ liệu được phục hồi.
- **Retention:** khoảng thời gian giữ object/recovery point để còn khả năng quay lại.
- **Backup độc lập:** cơ chế có khả năng giữ bản sao ra ngoài phạm vi hỏng của storage account nguồn theo thiết kế hỗ trợ.

Ví dụ:

| Workload | Mục tiêu minh họa | Biện pháp |
|---|---|---|
| Hình sản phẩm cập nhật hằng tuần | Phục hồi ghi đè/xóa trong 30 ngày. | Versioning, blob soft delete, container soft delete và lifecycle. |
| Hồ sơ tài chính | Giữ lịch sử dài, kiểm soát sửa/xóa. | Versions/snapshots, immutable policy phù hợp và backup độc lập. |
| Dữ liệu pipeline được tái tạo | Giữ ít bản cũ, ưu tiên chi phí. | Retention ngắn hơn nếu có thể tái tạo từ nguồn gốc. |
| Dữ liệu bị sửa hàng loạt | Khả năng quay lại cả tập blob. | PITR nếu hỗ trợ hoặc manifest/versioned dataset và restore workflow. |

Các ngày retention là **giá trị thiết kế**, không phải bảo đảm tính năng tự động đáp ứng mọi RPO/RTO. Với Blob Storage, một previous version có thể được tạo khi ghi đè nhưng **RTO để phục hồi 100.000 blobs** vẫn có thể dài nếu thiếu công cụ tự động và kinh nghiệm vận hành.

### Tại sao replication không đủ?

GRS/GZRS giúp bảo vệ khả năng tồn tại dữ liệu theo phạm vi địa lý, nhưng một thao tác xóa/ghi sai được chấp nhận **có thể được replicate**. Versioning/snapshot bảo vệ lịch sử trong account; backup độc lập hoặc cơ chế immutable phù hợp giúp giảm rủi ro mất mọi recovery point khi nguồn gặp sự cố nghiêm trọng.

Đối với nhu cầu khôi phục khi **storage account bị xóa**, phải chứng minh trước có bản dữ liệu độc lập thực sự và có quy trình phục hồi sang account mới. Không dựa vào tính năng soft delete blob/container như phương án duy nhất cho account-level disaster.

## 24. Bài thực hành: thiết kế, thử lỗi và khôi phục

**Bối cảnh:** một nhóm vận hành lưu báo cáo tháng vào Blob Storage. Môi trường lab có một storage account hỗ trợ các tính năng cần thiết và một container tên `recovery-lab`.

Mục tiêu:

- Giữ lịch sử ghi đè bằng **Blob versioning**.
- Bảo vệ xóa nhầm blob bằng **blob soft delete** 30 ngày.
- Bảo vệ xóa nhầm container bằng **container soft delete** 14 ngày.
- Tạo một **snapshot** trước bước cập nhật dữ liệu.
- Khôi phục một phiên bản cũ mà không phá hỏng dữ liệu hiện hành trong khi kiểm thử.

### Dữ liệu thử

Blob `reports/weekly.csv` ban đầu:

```csv
week,totalOrders
2026-W45,120
```

Sau cập nhật:

```csv
week,totalOrders
2026-W45,130
```

### Nhiệm vụ

1. Xác minh đúng tenant, subscription, storage account và container lab.
2. Kiểm tra storage account **hỗ trợ** versioning, snapshots và soft delete cho loại blob đang dùng.
3. Bật hoặc xác minh versioning; đặt hai retention theo yêu cầu khi được cho phép.
4. Upload dữ liệu đầu tiên rồi tạo snapshot S1.
5. Ghi đè dữ liệu bằng bản thứ hai và liệt kê previous versions.
6. Chỉ ra sự khác nhau giữa **Version ID** và **snapshot timestamp**.
7. Tải previous version/snapshot về đích riêng và kiểm tra nội dung.
8. Xóa blob thử, thực hành phân biệt **undelete** và **copy/promote previous version**.
9. Nếu có quyền và quy trình lab cho phép, thử xóa/undelete một **container riêng biệt**, không phải container dùng chung.
10. Ghi kế hoạch lifecycle sao cho các recovery points quan trọng không bị dọn sớm.
11. Đề xuất một biện pháp bảo vệ khi toàn bộ account không còn khả dụng.
12. Tính số phiên bản trung bình tăng mỗi tháng nếu job ghi đè một blob mỗi ngày, và đánh giá chi phí lưu lịch sử.

### Lời giải định hướng

- **Sau ghi đè:** current blob có dữ liệu `130`, previous version giữ nội dung `120` nếu versioning hoạt động trên loại blob đó.
- **Snapshot S1:** trỏ tới nội dung thời điểm chụp, độc lập về định danh với previous version; bản S1 vẫn chỉ đọc.
- **Sau xóa:** kiểm tra danh sách versions và soft-deleted records; với versioning bật có thể cần copy previous version về current.
- **Khi xóa container:** cần container soft delete được bật **trước** thao tác xóa và container còn trong retention.
- **Với 1 lần ghi đè/ngày:** sau 30 ngày có thể phát sinh khoảng 30 previous versions cho một blob, nếu không có dọn phiên bản và mỗi hoạt động tạo version như dự kiến; dung lượng tính phí phụ thuộc dữ liệu thay đổi.
- **Sự cố cấp account:** cần bản sao độc lập/backup phù hợp, không coi versions và snapshots trong cùng account là bản backup riêng.

**Tiêu chí nghiệm thu:** có thể chỉ ra chính xác Version ID, snapshot timestamp, current blob và bản đã xóa; download được nội dung cần khôi phục; không ghi đè dữ liệu hiện hành khi chưa xác minh; và có bằng chứng chính sách retention/lifecycle.

## 25. Tự kiểm tra kiến thức

**Câu 1.** Khi versioning đã bật và block blob bị ghi đè, điều nào thường xảy ra?

A. Bản cũ luôn bị xóa vĩnh viễn.  
B. Bản cũ có thể được lưu dưới dạng previous version với Version ID.  
C. Cả storage account tự sao chép sang region khác.

**Đáp án: B.** Versioning giữ lịch sử qua các thao tác thay đổi blob được hỗ trợ.

**Câu 2.** Blob snapshot khác previous version ở điểm nào?

**Đáp án:** Snapshot thường được tạo theo yêu cầu tại một thời điểm; previous version do cơ chế versioning tự tạo khi blob thay đổi qua thao tác được hỗ trợ. Chúng dùng định danh và vòng đời riêng.

**Câu 3.** Bật blob soft delete có tự bảo vệ việc xóa cả container không?

**Đáp án:** Không. Cần **container soft delete** hoặc một cơ chế backup khác phù hợp.

**Câu 4.** Vì sao xóa current blob khi có versioning không nhất thiết dùng một lệnh undelete là xong?

**Đáp án:** Current blob có thể không còn trong khi previous versions vẫn tồn tại; phải chọn phiên bản hợp lệ rồi copy/promote thành current.

**Câu 5.** Version ID và snapshot timestamp có thể dùng lẫn nhau trong câu lệnh download không?

**Đáp án:** Không. Chúng đại diện cho hai loại recovery point khác nhau; API/CLI dùng tham số riêng.

**Câu 6.** GRS/ZRS có thay thế blob versioning khi một ứng dụng ghi đè dữ liệu sai không?

**Đáp án:** Không. Redundancy bảo vệ độ bền theo mô hình lưu trữ nhưng có thể sao chép thay đổi sai; versioning giữ bản cũ nếu được bật và còn tồn tại.

**Câu 7.** Vì sao một snapshot của một blob không đảm bảo cả bộ 1.000 blobs ở trạng thái nhất quán?

**Đáp án:** Snapshot/versions thường là recovery point theo object. Nhiều blob cập nhật ở thời điểm khác nhau cần cơ chế manifest, commit marker, PITR được hỗ trợ hoặc quy trình nhất quán riêng.

**Câu 8.** Bật versioning có mặc định cho phép restore toàn bộ block blobs theo một thời điểm tùy ý không?

**Đáp án:** Không. PITR là tính năng riêng, có điều kiện và retention; phải bật/cấu hình đúng nếu được hỗ trợ.

**Câu 9.** Tại sao không nên chỉ dựa vào lifecycle policy “xóa previous versions sau 7 ngày” cho dữ liệu cần quay lại 90 ngày?

**Đáp án:** Rule có thể loại bỏ recovery points trước thời hạn nghiệp vụ cần. Retention của versions/snapshots phải được phối hợp với thời gian phát hiện sự cố và policy thực tế.

**Câu 10.** Immutability và soft delete có giống nhau không?

**Đáp án:** Không. Immutability hạn chế sửa/xóa theo chính sách, trong khi soft delete giữ lại một số đối tượng đã xóa để có thể phục hồi trong retention.

**Câu 11.** Khi một blob bị ghi đè, tại sao nên tải previous version sang tên mới trước khi khôi phục chính thức?

**Đáp án:** Để kiểm tra dữ liệu đúng, tránh phá hủy thay đổi hợp lệ mới hơn, dễ được owner phê duyệt và giảm rủi ro chọn sai Version ID.

**Câu 12.** Có account đang bật blob soft delete 30 ngày, nhưng container soft delete đang tắt. Admin xóa container hôm qua. Có chắc khôi phục được không?

**Đáp án:** Không. Blob soft delete không tự thay thế container soft delete; phải tìm một bản sao/phương án khôi phục khác nếu không có deleted container còn có thể phục hồi.

**Câu 13.** Microsoft Entra RBAC role trên control plane có tự động cho phép download blob bằng `--auth-mode login` không?

**Đáp án:** Không. Cần quyền **data plane** phù hợp để truy cập nội dung Blob qua OAuth.

**Câu 14.** Vì sao tài khoản có phiên bản cũ nhưng ứng dụng vẫn thấy 404 sau khi xóa current blob?

**Đáp án:** Có thể không còn current blob. Ứng dụng gọi tên blob không chỉ định version; cần copy một previous version hợp lệ để tạo lại current.

**Câu 15.** Khi nào cần một bản backup độc lập thay vì chỉ giữ snapshots trong account?

**Đáp án:** Khi phải chịu được rủi ro mất/corrupt/xóa tài khoản nguồn hoặc việc người có quyền cao phá hủy recovery points; lựa chọn backup phải được cấu hình và kiểm thử khôi phục từ trước.

**Tóm lại:** Blob versioning là lớp bảo vệ tự động trước nhiều thao tác ghi đè; snapshot chủ động ghi lại mốc dữ liệu của một blob; blob/container soft delete giúp giảm rủi ro xóa nhầm trong khoảng retention. Kết hợp chúng với lifecycle, least privilege, monitoring, immutability và backup độc lập khi cần sẽ tạo ra phương án **khôi phục có bằng chứng, đúng phiên bản, đúng phạm vi và không gây mất thêm dữ liệu**.
