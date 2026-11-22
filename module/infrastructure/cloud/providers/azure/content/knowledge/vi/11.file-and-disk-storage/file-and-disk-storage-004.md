# Snapshot, backup và khôi phục Azure Files

Hãy tưởng tượng một công ty dùng **Azure Files** làm ổ đĩa chia sẻ cho bộ phận kế toán. Lúc 14:00, một nhân viên vô tình ghi đè bảng lương; sáng hôm sau, một thư mục bị xóa; cuối tuần, nhóm vận hành phát hiện storage account không còn truy cập được. Cả ba sự cố đều liên quan đến mất dữ liệu, nhưng **không nhất thiết có cùng cách khôi phục**.

Azure Files cung cấp **file share snapshots** để quay về trạng thái tệp ở một thời điểm trước đó. **Azure Backup** có thể điều phối chính sách sao lưu, lịch tạo điểm khôi phục, thời gian giữ lại và quy trình phục hồi; trong những cấu hình được hỗ trợ còn có khả năng sao lưu vào tầng vault. **Soft delete** giúp cứu file share bị xóa nhầm trong thời hạn bảo vệ. Chọn đúng cơ chế phải dựa vào loại sự cố, phạm vi cần khôi phục, yêu cầu về RPO/RTO và khả năng bảo vệ khỏi rủi ro ở cấp storage account.

Bài học thuộc chương **Lưu trữ tệp và đĩa** của module `CLOUD_PROVIDERS_AZURE`. Module giới thiệu hệ sinh thái Microsoft Azure từ subscription, resource group và Microsoft Entra ID đến mạng ảo, dịch vụ tính toán, lưu trữ và dữ liệu; đồng thời hướng dẫn triển khai, giám sát, bảo vệ và kiểm soát chi phí kiến trúc ứng dụng trên Azure. Ở đây, ta tập trung vào **bảo vệ và phục hồi dữ liệu Azure Files**, không đánh đồng snapshot của file share với snapshot của managed disk hay Azure Blob.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **snapshot**, **backup**, **recovery point**, **soft delete** và **replication**.
2. Giải thích cách một **Azure Files share snapshot** lưu trạng thái chia sẻ theo thời điểm và vì sao nó không phải bản sao độc lập ngoài storage account.
3. Xây dựng chính sách bảo vệ bằng **Azure Backup**: tần suất, retention, phạm vi dữ liệu, recovery point và quyền vận hành.
4. So sánh **snapshot-based backup** với **vaulted backup** khi loại file share và region hỗ trợ.
5. Chọn cách phục hồi **một tệp**, **một thư mục**, **cả file share** hoặc **file share bị xóa nhầm**.
6. Xác định RPO/RTO, kiểm thử restore và thiết lập cảnh báo khi backup thất bại.
7. Phát hiện các nhầm lẫn thường gặp, chẳng hạn coi GRS là backup hoặc coi snapshot là dữ liệu độc lập với storage account.
8. Viết runbook xử lý sự cố mà không ghi đè thêm dữ liệu và không làm mất recovery point còn giá trị.

## 2. Nhắc lại Azure Files và phạm vi bảo vệ

**Azure Files** cung cấp file share được quản lý trên Azure Storage. Ứng dụng và máy chủ có thể truy cập theo giao thức được tài khoản/loại share hỗ trợ, chẳng hạn **SMB** hoặc **NFS**. Một số hệ thống dùng **Azure File Sync** để đồng bộ dữ liệu từ Windows Server lên Azure file share; các hệ thống khác mount trực tiếp share từ máy ảo hoặc máy tại văn phòng qua kết nối mạng phù hợp.

Cấu trúc khái niệm:

```text
Subscription / Resource group
└── Storage account: stcontosofiles01
    ├── File share: finance
    │   ├── reports/
    │   ├── invoices/
    │   └── payroll.xlsx
    └── File share: projects
        ├── designs/
        └── contracts/
```

Khi tạo snapshot của `finance`, bạn chụp trạng thái **file share finance**, không chụp toàn bộ storage account và cũng không tự động tạo snapshot cho `projects`. Khi cấu hình backup, cần xác nhận **file share cụ thể** nào đã được đưa vào phạm vi bảo vệ.

**Lưu ý về tính năng:** khả năng snapshot, backup, snapshot tier/vault tier và quy trình restore có thể khác theo **SMB/NFS**, **standard/premium hoặc loại billing model**, loại storage account, region và thời điểm dịch vụ hỗ trợ. Với môi trường thật, hãy xác minh các tính năng trong Azure Portal và tài liệu dịch vụ áp dụng cho share đang bảo vệ trước khi lập cam kết RPO/RTO.

## 3. Snapshot, backup, soft delete và replication khác nhau thế nào?

| Cơ chế | Bản chất | Giải quyết tốt | Giới hạn quan trọng |
|---|---|---|---|
| **File share snapshot** | Trạng thái chỉ đọc của một file share tại thời điểm tạo snapshot; dữ liệu thay đổi được lưu theo cơ chế snapshot của dịch vụ. | Lấy lại tệp đã sửa/xóa hoặc so sánh trạng thái một share tại các thời điểm. | Snapshot gắn với storage account/share, không tự tạo bản sao độc lập để chống mất cả account. |
| **Azure Backup – snapshot tier** | Azure Backup điều phối và quản lý các recovery point dựa trên share snapshots. | Backup theo lịch, giữ bản trong một số ngày, khôi phục từng mục hoặc cả share theo khả năng hỗ trợ. | Dữ liệu recovery point snapshot vẫn nằm trong phạm vi storage account gốc. |
| **Azure Backup – vaulted tier** | Lưu bản backup vào tầng vault theo loại Azure Files và chính sách được hỗ trợ. | Tăng khả năng khôi phục khi xảy ra sự cố nghiêm trọng tại tài khoản lưu trữ gốc. | Không áp dụng cho mọi kiểu share/SKU/region; có lịch, retention, tính năng và chi phí riêng. |
| **File share soft delete** | Giữ khả năng phục hồi file share bị xóa trong khoảng retention đã cấu hình. | Khôi phục khi ai đó xóa **cả share** ngoài ý muốn. | Không thay thế snapshot để phục hồi một file bị ghi đè hoặc bị xóa trong share đang tồn tại. |
| **Redundancy/replication** | Lưu nhiều bản dữ liệu theo LRS/ZRS/GRS/GZRS hoặc lựa chọn hỗ trợ. | Độ bền dữ liệu, chịu lỗi hạ tầng hoặc vùng theo mô hình. | Thay đổi hoặc xóa dữ liệu hợp lệ có thể được sao chép; không mặc định cung cấp lịch sử bản cũ. |

**Quy tắc thực hành:** dùng snapshot để phục hồi gần thời điểm xảy ra lỗi; dùng backup policy để quản lý lịch và retention; dùng bảo vệ độc lập ở tầng vault/ngoài account khi có yêu cầu phục hồi khỏi sự cố lớn; và bật soft delete để giảm rủi ro xóa nhầm file share. Các cơ chế bổ sung cho nhau, không phải những tên khác của cùng một tính năng.

### Ví dụ phân biệt

- Một nhân viên sửa nhầm `payroll.xlsx`: ưu tiên **snapshot/recovery point** trước thời điểm sửa, rồi khôi phục một tệp.
- Một quản trị viên xóa share `finance`: kiểm tra **soft delete** và các cơ chế backup còn khả dụng.
- Storage account không còn truy cập được hoặc bị xóa: **share snapshot nằm cùng account** có thể không đủ; cần kế hoạch phục hồi độc lập đã được hỗ trợ và cấu hình trước.
- Lỗi đĩa/hạ tầng Azure: **redundancy** có thể hỗ trợ tính sẵn sàng, nhưng không giúp “quay ngược” một nội dung đã bị ghi đè do thao tác hợp lệ.

## 4. Cơ chế Azure Files share snapshot

Share snapshot là một **bản chụp tại một thời điểm (point-in-time), chỉ đọc** của toàn bộ file share. Snapshot lưu trạng thái tệp, thư mục và metadata theo khả năng của dịch vụ tại thời điểm tạo. Sau khi snapshot được tạo, ứng dụng có thể tiếp tục sửa/xóa file trong share đang hoạt động, còn dữ liệu trong snapshot vẫn tham chiếu trạng thái cũ.

Ví dụ diễn tiến:

```text
09:00  finance/payroll.xlsx  = phiên bản A
        │
        ├── 09:05: tạo Snapshot S1
        │           S1 thấy payroll.xlsx = A
        │
11:00  nhân viên sửa payroll.xlsx → phiên bản B
        │
        ├── 11:05: tạo Snapshot S2
        │           S2 thấy payroll.xlsx = B
        │
13:00  payroll.xlsx bị xóa ở share hiện hành
        │
        └── Khôi phục từ S1 hoặc S2 theo mốc cần thiết
```

Từ snapshot, bạn có thể **duyệt nội dung cũ hoặc sao chép/khôi phục** sang vị trí cho phép; **không ghi đè trực tiếp vào chính snapshot**, vì snapshot là chỉ đọc. Cách mở snapshot có thể thông qua Azure Portal, client SMB/Windows “Previous Versions” trong tình huống hỗ trợ, hoặc Storage API/CLI/SDK.

### Snapshot được lưu trữ như thế nào?

Share snapshots được quản lý theo cơ chế lưu **phần thay đổi** thay vì phải nhân bản vật lý toàn bộ dữ liệu cho mỗi lần chụp. Điều này giúp tạo recovery point nhanh và tiết kiệm hơn một bản sao đầy đủ trong nhiều tình huống.

Tuy nhiên, chi phí vẫn có thể tăng khi:

- Khối lượng dữ liệu thay đổi giữa các snapshot lớn.
- File lớn thường xuyên bị ghi lại.
- Giữ nhiều snapshots trong thời gian dài.
- Có nhiều share với tần suất chụp cao.

**Một snapshot không phải một bản sao độc lập ở storage account khác.** Nếu nhóm muốn khôi phục khỏi tình huống mất account, mất vùng truy cập hoặc sai sót của người có quyền cao, phải đánh giá thêm tầng bảo vệ độc lập và quyền xóa recovery point.

### Snapshot không đồng nghĩa ứng dụng đã nhất quán tuyệt đối

Snapshot cung cấp ảnh chụp trạng thái file share tại thời điểm tạo, nhưng **không tự bảo đảm ứng dụng đã flush xong cache, hoàn tất transaction hoặc đồng bộ trạng thái nhiều tệp**. Ví dụ một phần mềm kế toán đang ghi hai file có quan hệ với nhau; snapshot có thể được tạo giữa các bước ghi.

Đối với dữ liệu yêu cầu tính nhất quán ứng dụng:

1. Xác định các ứng dụng đang đọc/ghi và file nào có phụ thuộc lẫn nhau.
2. Nếu cần, đưa ứng dụng vào trạng thái an toàn/quiesce hoặc dùng khả năng hỗ trợ của ứng dụng.
3. Tạo snapshot hay recovery point theo runbook.
4. Cho ứng dụng tiếp tục và **thử phục hồi** để xác nhận có thể mở dữ liệu.
5. Với hệ thống cơ sở dữ liệu, không mặc định snapshot file share thay thế cơ chế backup nhất quán ở tầng database.

## 5. Tạo và sử dụng snapshot thủ công

Snapshot thủ công phù hợp lab, kiểm thử nâng cấp, sao lưu nhanh trước thay đổi có rủi ro hoặc khi cần một recovery point theo yêu cầu.

### Quy trình trong Azure Portal

1. Đăng nhập [Azure Portal](https://portal.azure.com/) vào đúng **tenant/subscription**.
2. Mở **Storage accounts** và chọn account chứa Azure file share.
3. Vào khu vực **File shares**, chọn đúng share, ví dụ `finance`.
4. Tìm mục **Snapshots** hoặc thao tác tạo share snapshot theo giao diện hiện hành.
5. Tạo snapshot và ghi lại **thời điểm/định danh snapshot**, người thực hiện và lý do.
6. Mở danh sách snapshots để xác minh điểm chụp tồn tại.
7. Nếu cần restore, ưu tiên kiểm tra nội dung snapshot trước khi ghi đè dữ liệu đang hoạt động.

Một thao tác tạo snapshot thành công **chỉ xác minh có recovery point**, chưa chứng minh khả năng phục hồi đúng dữ liệu ứng dụng. Phải thử file và kiểm tra toàn vẹn ở bước riêng.

### Ví dụ Azure CLI

Azure CLI có các nhóm lệnh cho **data-plane Azure Files** (`az storage share`, `az storage file`) và các thao tác **Azure Resource Manager/control-plane** (`az storage share-rm`). Tên đối số và phương thức xác thực có thể khác theo phiên bản Azure CLI và loại share, vì vậy hãy đọc `--help` trong môi trường đang sử dụng.

Đầu tiên xác minh subscription và account bằng lệnh chỉ đọc:

```bash
az account show \
  --query "{Name:name,Subscription:id,Tenant:tenantId}" \
  --output table

az storage account show \
  --name "<STORAGE_ACCOUNT>" \
  --resource-group "<RESOURCE_GROUP>" \
  --query "{Name:name,Kind:kind,Location:location}" \
  --output table
```

Khi dùng nhóm lệnh data-plane, cần cơ chế xác thực mà lệnh/loại share hỗ trợ (ví dụ account key/connection string/SAS trong phạm vi cho phép). **Không dán account key hoặc connection string vào shell history, ticket hoặc repository.** Đăng nhập Azure CLI để quản lý tài nguyên không có nghĩa mọi lệnh Azure Files data-plane tự dùng Microsoft Entra OAuth mà không cần cấu hình bổ sung.

Minh họa lệnh tạo snapshot của một share:

```bash
az storage share snapshot \
  --name "<SHARE_NAME>" \
  --account-name "<STORAGE_ACCOUNT>"
```

Nếu lệnh yêu cầu xác thực data-plane, chuẩn bị cơ chế đã được cấp quyền theo hướng dẫn tổ chức; không thêm secret vào ví dụ. Lệnh tạo snapshot **thay đổi trạng thái tài nguyên và có thể phát sinh chi phí**, chỉ chạy trong lab hoặc môi trường đã được cho phép.

Liệt kê share và snapshots:

```bash
az storage share list \
  --account-name "<STORAGE_ACCOUNT>" \
  --include-snapshots \
  --output json
```

Khi đọc kết quả, chú ý tên share và **snapshot timestamp**: nhiều bản chụp có thể cùng share name nhưng khác thời gian. Giữ chính xác chuỗi timestamp để chọn recovery point phù hợp.

### Khi nào dùng thủ công, khi nào cần chính sách?

Snapshot thủ công hữu ích trước một lần thay đổi có kiểm soát. Với dữ liệu nghiệp vụ cần bảo vệ liên tục, phụ thuộc vào việc quản trị viên nhớ bấm snapshot thường không đủ. Dùng **Azure Backup** hoặc một giải pháp được phê duyệt để có lịch, thời gian giữ bản và giám sát.

## 6. Azure Backup dành cho Azure Files

**Azure Backup** giúp quản lý tập trung các lần sao lưu và restore theo chính sách thay vì chỉ tạo snapshots thủ công. Với loại share và tính năng được hỗ trợ, bạn cấu hình bảo vệ Azure file share trong **Recovery Services vault**, đăng ký/nhận diện storage account, chọn file share rồi gán **backup policy**.

Một số triển khai hỗ trợ các lớp recovery point:

- **Snapshot tier (operational):** phục hồi nhanh từ snapshots được Backup quản lý tại storage account nguồn.
- **Vaulted tier:** sao lưu vào tầng vault độc lập hơn với account nguồn, nhằm mở rộng kịch bản bảo vệ. Tính năng, phương thức khôi phục và giới hạn thay đổi theo kiểu Azure Files và chính sách được hỗ trợ.

Không phải mọi Azure Files share đều có cùng tập khả năng. Trước khi cam kết bảo vệ **premium, NFS hoặc workload đặc thù**, xác minh sự hỗ trợ của **từng tầng backup** trong account/region thực tế, cùng giới hạn retention, lịch, restore target và yêu cầu dịch vụ.

### Azure Backup quản lý điều gì?

| Năng lực | Ý nghĩa đối với người vận hành |
|---|---|
| **Backup policy** | Quy định lịch tạo backup và retention theo nhu cầu tổ chức. |
| **Recovery point** | Mốc dữ liệu có thể chọn để phục hồi theo chính sách/tính năng đã hỗ trợ. |
| **Protected item** | File share đang nằm trong phạm vi được Azure Backup quản lý. |
| **Backup job** | Một lần chạy backup, có trạng thái và thông tin lỗi nếu có. |
| **Restore job** | Quá trình khôi phục file/share được theo dõi và kiểm tra kết quả. |
| **Alerts và monitoring** | Hỗ trợ phát hiện job thất bại hoặc thay đổi trạng thái bảo vệ. |
| **Retention** | Số lượng/khoảng thời gian recovery points được giữ theo cấu hình. |

**Recovery Services vault không mặc nhiên chứa một bản sao dữ liệu độc lập chỉ vì bạn thấy một protected item.** Nếu cấu hình chỉ dùng snapshot tier, dữ liệu snapshot vẫn thuộc account nguồn. Muốn đánh giá khả năng chịu sự cố phá hủy account, phải xác nhận **vaulted backup có thực sự được bật và hỗ trợ**.

### Snapshot do Azure Backup tạo và snapshot thủ công

Hai loại recovery point có thể xuất hiện cạnh nhau nhưng **khác trách nhiệm vòng đời**:

- Snapshot thủ công: nhóm vận hành tạo/xóa và tự quản lý retention.
- Snapshot do Azure Backup tạo: backup policy và dịch vụ quản lý để đáp ứng lịch, retention, restore.

Không tự xóa hoặc thay đổi các snapshots đang do Azure Backup quản lý chỉ để giải phóng dung lượng; hành động đó có thể làm hỏng khả năng khôi phục hoặc làm trạng thái backup không nhất quán. Hãy điều chỉnh thông qua policy/protected item và quy trình hỗ trợ.

## 7. RPO, RTO và retention: biến yêu cầu nghiệp vụ thành policy

Một hệ thống có “backup hằng ngày” vẫn có thể không đạt yêu cầu nếu nghiệp vụ chỉ chấp nhận mất tối đa một giờ dữ liệu.

- **RPO (Recovery Point Objective):** lượng dữ liệu tối đa chấp nhận mất, đo bằng độ lùi thời gian của recovery point phù hợp.
- **RTO (Recovery Time Objective):** thời gian tối đa cho phép đến khi hệ thống/dữ liệu phục vụ được trở lại.
- **Retention:** thời gian lưu recovery point để còn khả năng quay lại các trạng thái cũ.
- **Backup frequency:** tần suất tạo điểm chụp; ảnh hưởng trực tiếp RPO trong tình huống không có backup thất bại.

Ví dụ:

| Dữ liệu | RPO mục tiêu | RTO mục tiêu | Retention tham khảo | Điều cần xem |
|---|---|---|---|---|
| Hồ sơ làm việc nhóm | 24 giờ | 4 giờ | 30 ngày | Snapshot theo lịch, khả năng khôi phục file. |
| Hóa đơn nhạy cảm | 4 giờ | 2 giờ | Theo quy định | Kiểm tra policy có hỗ trợ đủ tần suất và yêu cầu bảo vệ độc lập. |
| Thư mục tài liệu dự án | 24 giờ | 8 giờ | 90 ngày | Nhu cầu phục hồi phiên bản cũ sau nhiều tuần. |
| File dùng làm dữ liệu ứng dụng liên tục | Phút hoặc rất thấp | Ngắn | Theo ứng dụng | Có thể cần cơ chế bảo vệ nhất quán/chuyên dụng ngoài snapshots thông thường. |

Các con số chỉ **minh họa yêu cầu**, không phải cam kết rằng Azure Backup Azure Files hỗ trợ mọi tần suất và RPO nêu trên. Chọn policy thực tế phải dựa trên **lịch và retention được dịch vụ hỗ trợ**, khả năng tạo recovery point thành công và thử nghiệm phục hồi. Nếu yêu cầu RPO ngắn hơn lịch backup hỗ trợ, cần bổ sung cơ chế riêng hoặc thiết kế lại workload.

### Ví dụ tính RPO thực tế

Nếu backup thành công cuối cùng lúc 01:00 và file bị hỏng lúc 08:30, chọn recovery point 01:00 có thể làm mất những thay đổi hợp lệ từ 01:00 đến 08:30. RPO thực tế của sự cố là **7 giờ 30 phút**, không phải chỉ tiêu “backup hằng ngày”.

Nếu có điểm khác lúc 08:00 được xác minh an toàn, phần dữ liệu mất có thể chỉ khoảng **30 phút**. Mốc gần nhất không luôn là mốc **đúng nhất**: với ransomware, snapshot mới nhất có thể đã chứa tệp bị mã hóa. Cần chọn recovery point trước khi sự cố bắt đầu.

## 8. Cấu hình backup policy và protection bằng Azure Portal

Quy trình tổng quát dưới đây dành cho môi trường **đủ điều kiện hỗ trợ Azure Backup for Azure Files**; tên mục có thể thay đổi theo Portal/tính năng mới.

### Giai đoạn A: Chuẩn bị

1. Xác nhận subscription, tenant, resource group và storage account đang chứa file share.
2. Kiểm tra giao thức share (SMB/NFS), loại account, tier, region và khả năng backup của dịch vụ.
3. Ghi yêu cầu RPO, RTO, retention và phân loại dữ liệu.
4. Kiểm tra quyền Azure RBAC và dữ liệu cần thiết để cấu hình bảo vệ; tránh cấp quyền rộng khi không bắt buộc.
5. Xem cấu hình soft delete, redundancy, network restriction, private endpoint và chính sách bảo mật liên quan.

### Giai đoạn B: Tạo hoặc chọn vault

1. Mở [Azure Portal](https://portal.azure.com/).
2. Tìm **Recovery Services vaults** và chọn một vault phù hợp với vùng/điều kiện dịch vụ hoặc tạo mới nếu được phép.
3. Mở chức năng **Backup**, chọn workload tương ứng với **Azure FileShare/Azure Files** theo giao diện.
4. Chọn storage account và file share cụ thể cần bảo vệ.
5. Tạo hoặc chọn **backup policy**, đặt lịch và retention theo những khả năng được dịch vụ hỗ trợ.
6. Nếu có lựa chọn snapshot/vault tiers, chỉ bật những tính năng đã được xác nhận hỗ trợ và đáp ứng yêu cầu phục hồi.

### Giai đoạn C: Kiểm tra sau khi bảo vệ

1. Xác minh file share xuất hiện là **protected item**.
2. Thực hiện backup theo lịch hoặc một lần **Backup now** khi được phép.
3. Theo dõi **Backup Jobs** đến khi trạng thái hoàn tất thành công.
4. Mở **Recovery points**, xác minh thời điểm điểm khôi phục có thể chọn.
5. Ghi nhận policy, vault, protected item, lịch, retention và người chịu trách nhiệm.
6. Thực hiện **restore test** trên một thư mục riêng trước khi tuyên bố công tác bảo vệ đã hoàn tất.

**Điểm cần phân biệt:** trạng thái policy được tạo thành công chưa chứng minh dữ liệu từng được backup thành công. Cần có **recovery point thực** và kiểm thử được.

## 9. Khôi phục một file hoặc thư mục từ share snapshot

Đây là tình huống phổ biến nhất: một tệp bị xóa, ghi đè hoặc hỏng, nhưng file share và storage account vẫn hoạt động.

Giả sử `finance/reports/summary.xlsx` bị ghi đè lúc 10:20, và có snapshot lúc 10:00.

### Phương án an toàn: khôi phục ra tên khác trước

1. Xác định **share và đường dẫn file** bị ảnh hưởng.
2. Ghi lại thời gian sự cố và các recovery points có trước đó.
3. Mở snapshot 10:00, xem file cần tìm có tồn tại và đúng kích thước/nội dung không.
4. **Sao chép hoặc tải về** phiên bản trong snapshot sang tên/vị trí khác, ví dụ `restored/summary-1000.xlsx`.
5. Nhờ người phụ trách nghiệp vụ xác minh phiên bản được phục hồi.
6. Khi được phê duyệt, mới thay thế file đang hoạt động hoặc cung cấp lại bản cũ cho người dùng.
7. Ghi nhận snapshot ID, file path, người xác minh và hành động cuối cùng.

Lợi ích: không ghi đè phiên bản mới có thể còn chứa thay đổi hợp lệ sau snapshot. Nếu cần, so sánh các phần khác biệt trước khi hợp nhất dữ liệu.

### Truy cập qua Windows “Previous Versions”

Trong các môi trường **SMB/Windows** tương thích, Windows Explorer có thể hiển thị **Previous Versions** của file hoặc folder từ share snapshots. Quy trình thường là:

1. Mount Azure file share hoặc duyệt đường dẫn UNC bằng quyền được cấp.
2. Chọn file/folder, mở **Properties → Previous Versions**.
3. Chọn snapshot có thời điểm phù hợp.
4. Dùng **Open/Copy** để kiểm tra trước; tránh chọn **Restore** trực tiếp nếu chưa xác minh khả năng ghi đè.

Khả năng hiển thị và thao tác phụ thuộc phiên bản Windows, SMB, cách mount, quyền dữ liệu và tính năng snapshot. Với NFS hoặc môi trường không hỗ trợ Previous Versions, dùng Portal/API hoặc công cụ phù hợp.

### Minh họa CLI: tải file từ snapshot

Sau khi biết chính xác snapshot timestamp, một cách lấy bản cũ là tải file về rồi kiểm tra trước khi ghi lại:

```bash
az storage file download \
  --account-name "<STORAGE_ACCOUNT>" \
  --share-name "<SHARE_NAME>" \
  --path "reports/summary.xlsx" \
  --snapshot "<SNAPSHOT_TIMESTAMP>" \
  --dest "./summary-recovered.xlsx"
```

Kiểm tra cú pháp `az storage file download --help` trong phiên bản Azure CLI đang dùng và chuẩn bị cơ chế xác thực data-plane được phép. Đường dẫn `--dest` là **file local**, chưa phải ghi đè vào share. Lệnh đọc từ snapshot; tránh tải dữ liệu nhạy cảm về máy cá nhân không được quản lý.

Nếu muốn đưa lại file vào share, thực hiện bằng công cụ hỗ trợ và quy trình có phê duyệt; ưu tiên upload sang một đường dẫn phục hồi riêng để xác minh rồi mới thực hiện thay thế.

## 10. Khôi phục cả file share từ recovery point

Khi một lượng lớn file bị sửa/xóa hoặc cả cây thư mục bị hỏng, việc phục hồi từng tệp riêng lẻ có thể quá chậm. **Azure Backup** có thể cung cấp chức năng khôi phục **toàn bộ share** hoặc các mục được chọn theo cách backup tier và loại share hỗ trợ.

Quy trình tổng quát:

1. Xác định phạm vi dữ liệu cần đưa về trạng thái cũ và thời điểm sự cố bắt đầu.
2. Mở Recovery Services vault → Protected items/Backup items → chọn Azure file share.
3. Chọn **Restore** và recovery point phù hợp.
4. Kiểm tra phương án **Original location** hoặc **Alternate location** nếu tính năng cho phép.
5. Nếu restore đè lên dữ liệu hiện hành, đánh giá dữ liệu mới phát sinh kể từ recovery point và đóng/quiesce ứng dụng ghi file theo runbook.
6. Thử khôi phục vào **vị trí thay thế** khi khả thi để xác minh cấu trúc file, quyền và metadata.
7. Theo dõi Restore Job, kiểm tra log và xác nhận phục hồi với owner ứng dụng.
8. Mở lại quyền ghi hoặc dịch vụ khi đã xác minh dữ liệu và quyền truy cập.

### Original location và alternate location

| Phương án | Lợi ích | Rủi ro/điều kiện |
|---|---|---|
| **Original location** | Đưa dữ liệu về nơi ứng dụng đang sử dụng. | Có thể ghi đè hoặc tương tác với dữ liệu mới; cần quy trình thay đổi. |
| **Alternate location** | Dễ so sánh và xác minh trước khi thay thế; giảm nguy cơ mất thêm dữ liệu. | Cần không gian, quyền, networking và tính năng hỗ trợ restore target phù hợp. |

Không giả định mọi backup tier cho phép restore trực tiếp sang **bất kỳ storage account, region hoặc giao thức** nào. Tập đích hợp lệ phụ thuộc cơ chế backup và các giới hạn dịch vụ. Hãy kiểm tra khả năng mục tiêu trong wizard trước khi xây runbook dựa vào nó.

### Dữ liệu ứng dụng và quyền chia sẻ

Phục hồi file content là chưa đủ nếu ứng dụng còn phụ thuộc vào:

- NTFS ACL hoặc quyền file/share tùy giao thức.
- SMB share-level permissions và Azure RBAC phù hợp.
- File locking/các phiên đang mở.
- Tên đường dẫn, DNS/UNC path và cấu hình mount của client.
- Trạng thái ứng dụng, chỉ mục, database hoặc job đang đồng bộ.

Kiểm thử restore phải bao gồm **mở file bằng đúng tài khoản nghiệp vụ** và đọc/ghi theo quyền dự kiến, không chỉ xem file tồn tại trong Portal.

## 11. Khôi phục file share bị xóa nhầm bằng soft delete

**Azure Files share soft delete** bảo vệ một file share đã bị xóa ở phạm vi thời gian retention được cấu hình trên storage account. Trong thời gian này, hệ thống có thể cho phép **undelete/restore** file share theo chức năng hỗ trợ.

Điều quan trọng:

- Soft delete chủ yếu xử lý trường hợp **xóa chính file share**.
- Nó **không phải** thùng rác cho mọi file bị xóa hoặc ghi đè trong share vẫn còn tồn tại.
- Có **thời hạn retention**; sau khi hết hạn, không thể mặc định khôi phục từ soft delete.
- Không thay thế vault backup để chống các sự cố có quy mô account hoặc kiểm soát quyền cao.

### Quy trình khi share biến mất

1. Xác minh storage account vẫn tồn tại và share không chỉ bị mất kết nối do DNS/network.
2. Kiểm tra danh sách **deleted file shares** trong Portal nếu soft delete đã bật.
3. Xác minh tên share và thời điểm bị xóa.
4. Dùng chức năng **Undelete/Restore** tương ứng với share cần phục hồi, có quyền quản trị được cấp.
5. Kiểm tra share xuất hiện lại và các mount/ứng dụng có truy cập được không.
6. Nếu soft delete không có bản để phục hồi, đánh giá các backup recovery points độc lập còn khả dụng.
7. Ghi log thao tác xóa/khôi phục và xem xét hạn chế quyền xóa share trong tương lai.

**Không thử xóa cả share để “test soft delete” trên dữ liệu Production.** Dùng share lab và quy trình được phép, vì hành động xóa có thể làm gián đoạn người dùng và các tiến trình đang mount.

## 12. Ransomware, lỗi xóa hàng loạt và rủi ro cấp account

Một chiến lược backup tốt không chỉ tối ưu cho “xóa nhầm một file”. Cần xem xét **người tấn công hoặc tài khoản bị chiếm quyền** có thể sửa/xóa dữ liệu và recovery point nào.

### Ba cấp độ rủi ro

| Sự cố | Snapshots cùng account | Vaulted backup độc lập (nếu hỗ trợ) | Điều cần làm |
|---|---|---|---|
| Một file bị ghi đè | Thường là lựa chọn phục hồi nhanh. | Có thể là lựa chọn bổ sung. | Chọn bản trước khi file bị sửa. |
| Nhiều file bị mã hóa bởi ransomware | Hữu ích nếu còn snapshots sạch và quyền không bị lạm dụng để xóa chúng. | Tăng khả năng có bản sạch tách biệt khi được cấu hình đúng. | Xác định thời điểm xâm nhập, ngắt nguồn gây hại, kiểm tra recovery point. |
| Storage account bị xóa/hỏng hoặc không truy cập được | Không phải lớp bảo vệ độc lập đủ tin cậy. | Có thể hữu ích nếu backup dữ liệu thực sự được lưu trong vault và restore được theo điều kiện hỗ trợ. | Dùng runbook cấp account/region và kiểm tra quyền khôi phục. |

**Snapshot không tự chống ransomware**: người có quyền quản trị thích hợp vẫn có thể can thiệp vào dữ liệu, chính sách hoặc recovery points tùy quyền và bảo vệ đã bật. Cần phối hợp:

- Nguyên tắc **least privilege** và xác thực mạnh cho tài khoản quản trị.
- Phân tách nhóm vận hành file share với nhóm quản trị backup/vault.
- Soft delete, retention và các tính năng bảo vệ backup được hỗ trợ.
- Log, alert và quy trình ứng phó sự cố.
- Thử nghiệm restore từ những recovery points **trước khi dữ liệu bị ảnh hưởng**.
- Kho lưu trữ độc lập/immutable backup khi yêu cầu và tính năng hỗ trợ, với chính sách bảo vệ phù hợp.

Không khẳng định chỉ cần bật một lựa chọn “immutable” bất kỳ là mọi Azure Files backup đã chống xóa; phải kiểm tra cụ thể **backup tier, vault, tính năng immutable và quyền quản trị** của triển khai.

### Phát hiện bản sạch

Nếu ransomware bắt đầu mã hóa lúc 09:00 nhưng chỉ được phát hiện lúc 14:00, snapshot 13:00 có thể chứa nhiều file đã hỏng. Recovery point 08:00 có khả năng an toàn hơn, nhưng cũng cần **quét/kiểm tra dữ liệu** vì tác nhân độc hại có thể đã có mặt trước khi hành vi mã hóa được phát hiện.

Khi khôi phục sau tấn công:

1. Cô lập tác nhân gây hại và kiểm soát tài khoản/thiết bị bị xâm nhập.
2. Xác định recovery points còn được tin cậy.
3. Khôi phục vào môi trường cách ly hoặc alternate location khi khả thi.
4. Kiểm tra nội dung, quyền, ứng dụng và dữ liệu phụ thuộc.
5. Chỉ đưa lại vào Production khi qua quy trình phê duyệt an ninh.

## 13. Azure File Sync và vấn đề snapshot/backup

**Azure File Sync** cho phép Windows Server đồng bộ với Azure file share, có thể dùng cloud tiering. Khi sử dụng File Sync, cần phân biệt **dữ liệu của cloud share** và **những thay đổi cục bộ chưa đồng bộ** tại server endpoint.

Ví dụ:

```text
Windows Server (server endpoint)
       │
       │ Azure File Sync
       ▼
Azure file share (cloud endpoint)
       │
       ├── Share snapshot / Azure Backup
       └── Dữ liệu cloud share theo thời điểm recovery point
```

Một snapshot trên Azure file share phản ánh những gì đã có ở **cloud share tại thời điểm đó**. Nếu Windows Server có dữ liệu chưa kịp đồng bộ, không nên mặc định snapshot của cloud share đã chứa những thay đổi này.

Các bước kiểm tra:

- Xác minh trạng thái đồng bộ, lỗi sync và backlog theo công cụ giám sát Azure File Sync.
- Đánh giá dữ liệu mở, ứng dụng sử dụng file và kế hoạch nhất quán.
- Hiểu ảnh hưởng của thao tác restore trong cloud share đối với server endpoints và cơ chế đồng bộ sau đó.
- Nếu cần phục hồi một file chỉ có ở server chưa đồng bộ, có thể phải dùng cơ chế backup/restore cục bộ của server.
- Không thao tác trực tiếp trên snapshot rồi kỳ vọng File Sync tự đồng bộ như một thư mục đang hoạt động; snapshot là chỉ đọc.

Một chiến lược phục hồi đầy đủ cho File Sync có thể cần cả **bảo vệ Azure file share** và **bảo vệ dữ liệu/cấu hình tại Windows Server**, tùy mục tiêu nghiệp vụ.

## 14. Giám sát backup jobs, snapshots và khả năng khôi phục

**Backup đã được cấu hình** không đồng nghĩa **backup đã thành công**. Thiết lập quy trình theo dõi tối thiểu:

| Tín hiệu | Vì sao quan trọng? | Phản ứng cần thiết |
|---|---|---|
| **Backup job failed/warning** | Recovery point mới không được tạo như mong đợi. | Điều tra lỗi, quyền, dịch vụ và thử lại theo quy trình. |
| **Last successful backup time** | Có thể đã vượt RPO cho phép. | Cảnh báo khi tuổi recovery point vượt ngưỡng. |
| **Recovery point count/retention** | Số bản và thời điểm có thể khôi phục thay đổi theo policy. | Xác minh retention và điểm khôi phục cũ cần thiết. |
| **Restore job duration/result** | Đánh giá RTO thực tế. | Ghi thời gian hoàn tất và khả năng mở dữ liệu. |
| **Storage capacity/transactions** | Snapshots và backup làm thay đổi tiêu thụ dung lượng/chi phí. | Dự báo tăng trưởng và tối ưu lịch/retention. |
| **Protected items state** | Share có thể vô tình bị ngừng bảo vệ hoặc thay đổi policy. | Kiểm tra thay đổi cấu hình và phạm vi bảo vệ. |
| **Soft delete policy** | Share xóa nhầm có thể không còn trong retention. | Xác nhận thời hạn và quy trình restore. |
| **Identity/permission changes** | Quyền backup/restore có thể bị thu hồi hoặc cấp quá rộng. | Theo dõi quản trị và nguyên tắc tối thiểu. |

Có thể sử dụng **Azure Backup Center/Backup reports**, **Azure Monitor**, **Recovery Services vault**, Log Analytics và Azure Activity Log theo khả năng tích hợp. Azure Activity Log thường hỗ trợ xem thay đổi **control plane**, còn dữ liệu chi tiết về các job/recovery point cần xem tại dịch vụ backup.

### Test restore định kỳ

Một lịch kiểm thử có thể bao gồm:

1. Hằng tháng: khôi phục một file ngẫu nhiên vào thư mục thay thế.
2. Hằng quý: phục hồi cả thư mục/file share thử nghiệm để đo RTO.
3. Định kỳ theo yêu cầu DR: kiểm thử kịch bản mất khả năng truy cập account hoặc region với cơ chế backup đã cấu hình.
4. Sau thay đổi policy, network, identity hoặc ứng dụng: kiểm tra lại khả năng tạo recovery point và restore.

Đây chỉ là **cadence minh họa**, không phải lịch bắt buộc của Azure. Tần suất phải dựa trên mức độ quan trọng, quy định và ngân sách của tổ chức.

Kết quả nghiệm thu phải có bằng chứng **dữ liệu đọc được, quyền đúng và ứng dụng có thể sử dụng**, không chỉ trạng thái “Restore completed”.

## 15. Bảo mật và phân quyền cho thao tác khôi phục

Các khả năng quản trị khác nhau cần quyền khác nhau:

- **Quản lý Storage account/file share:** tạo, sửa, xóa share và cấu hình soft delete.
- **Azure Files data plane:** đọc/ghi nội dung file, xem snapshot hoặc thực hiện thao tác file theo cơ chế xác thực được hỗ trợ.
- **Quản lý backup:** tạo policy, bật/ngừng bảo vệ, tạo backup on demand.
- **Thực hiện restore:** chọn recovery point, đích phục hồi và theo dõi job.
- **Kiểm toán:** đọc cấu hình, lịch job, hoạt động thay đổi nhưng không nhất thiết được sửa dữ liệu.

Không nên trao toàn bộ quyền quản trị Storage và vault cho cùng một tài khoản vận hành thông thường. Chọn Azure RBAC roles theo trách nhiệm, dùng Microsoft Entra ID, PIM/MFA khi tổ chức có cấu hình, và ghi log các thao tác có tác động dữ liệu.

### Nguyên tắc khi khôi phục dữ liệu nhạy cảm

- Khôi phục vào vị trí **có phân quyền tương đương hoặc chặt hơn** vị trí gốc.
- Không tải file nhạy cảm về laptop cá nhân hoặc máy không quản lý.
- Nếu dùng alternate location, kiểm soát thời gian lưu bản phục hồi và việc dọn dẹp sau xác minh.
- Ghi người phê duyệt, thời điểm, phạm vi file, lý do, recovery point và checksum/cách đối chiếu nếu phù hợp.
- Không xóa snapshot/backup cũ trước khi chứng minh restore mới thành công và đã hết nhu cầu giữ bản.

## 16. Chi phí snapshot, backup và restore

Khả năng bảo vệ dữ liệu có chi phí; không nên chọn retention chỉ vì mức phí thấp nhất.

| Thành phần | Tác động chi phí cần đánh giá |
|---|---|
| Share snapshot | Lượng dữ liệu đã thay đổi được giữ qua snapshots, thời gian retention và loại share. |
| Azure Backup snapshot tier | Snapshot storage và các thành phần liên quan theo mô hình giá hỗ trợ. |
| Azure Backup vaulted tier | Bản dữ liệu trong vault, chính sách retention, tính năng và giao dịch liên quan. |
| Storage redundancy | LRS/ZRS/GRS/GZRS theo lựa chọn và khu vực. |
| Restore | Dung lượng đích, giao dịch, egress/cross-region nếu phát sinh trong mô hình hỗ trợ. |
| Monitoring | Log ingestion/retention, cảnh báo, công cụ theo dõi. |
| Vận hành | Thời gian kiểm thử, đối chiếu dữ liệu, phê duyệt và diễn tập khôi phục. |

**Ví dụ định tính:** hai share cùng có 1 TB dữ liệu, nhưng share A hiếm khi sửa, share B mỗi ngày ghi lại nhiều file lớn. Mức tăng dung lượng snapshot của share B có thể cao hơn đáng kể dù dung lượng live tương tự. Vì vậy dự toán phải xem **change rate**, không chỉ dung lượng hiện tại.

Trước khi triển khai, dùng **Azure Pricing Calculator** và giá theo region/SKU/backup tier hiện hành. Dữ liệu trong ví dụ không phải báo giá.

## 17. Quy trình xử lý sự cố: quyết định cơ chế khôi phục

Một runbook tốt bắt đầu bằng câu hỏi **đã mất gì và mất từ khi nào?**

```text
Phát hiện thiếu/sai dữ liệu Azure Files
                 |
                 v
         Storage account còn truy cập?
           /                       \
         Có                        Không
         |                           |
         v                           v
       Share còn tồn tại?       Kiểm tra phạm vi sự cố
       /              \            account/region
     Có               Không              |
     |                  |                v
     v                  v          Đánh giá vaulted/off-account
  File/folder        Soft delete          backup đã cấu hình
  bị sửa/xóa?        của share?           và khả năng restore
     |                  |
     v                  v
  Chọn snapshot       Undelete share
  /recovery point    nếu còn retention
     |
     v
  Khôi phục sang vị trí thay thế
     |
     v
  Kiểm tra tính đúng, quyền, ứng dụng
     |
     v
  Phê duyệt thay thế dữ liệu hiện hành
```

### Checklist hành động trong 15 phút đầu

1. **Ghi lại hiện tượng:** tên storage account/share, đường dẫn, thời điểm UTC, người phát hiện.
2. **Ngăn mất thêm dữ liệu:** tạm dừng tác vụ/ứng dụng gây ghi đè, cô lập thiết bị nghi bị tấn công theo quy trình.
3. **Không xóa recovery point:** giữ snapshot và backup liên quan, kiểm tra chính sách retention.
4. **Phân loại sự cố:** mất một tệp, cả share, mất account, lỗi quyền/mạng hay ransomware.
5. **Chọn recovery point an toàn:** mốc gần nhưng phải trước sự cố.
6. **Ưu tiên restore vào vị trí kiểm chứng:** không ghi đè ngay file hiện hành.
7. **Thông báo owner:** nêu mức dữ liệu có thể mất và thời gian phục hồi dự kiến theo runbook, không cam kết RTO chưa kiểm chứng.
8. **Ghi nhật ký:** thao tác và quyết định của từng nhóm để phục vụ kiểm toán.

### Khi restore không thành công

Lần lượt kiểm tra:

- Recovery point có tồn tại và **thuộc đúng file share** không?
- Đang dùng snapshot tier hay vaulted tier và restore target có được hỗ trợ?
- Share/storage account/vault có đủ quyền và trạng thái hoạt động?
- Client có thể kết nối Storage qua SMB/NFS/REST, DNS và firewall/private endpoint?
- Đích có đủ quota/dung lượng, tên đường dẫn hợp lệ và quyền ghi?
- Với File Sync, dữ liệu mong đợi đã được đồng bộ lên cloud chưa?
- Job đã thất bại do network, quyền, thời gian, loại dữ liệu hay trạng thái protected item?

Nếu chưa rõ, **không chạy nhiều lần restore đè lên cùng vị trí Production**. Thu thập lỗi và thử lại trên đích lab có kiểm soát.

## 18. Bài thực hành: khôi phục dữ liệu kế toán

**Bối cảnh:** Share `finance` trên Azure Files lưu hóa đơn và bảng lương. Backup theo chính sách tạo recovery point lúc 01:00 và 13:00. Lúc 14:15, nhân viên báo file `reports/payroll.xlsx` đã bị ghi đè lúc khoảng 13:40.

**Thông tin giả định:**

| Mục | Giá trị |
|---|---|
| Storage account | `stcontosofiles01` |
| Share | `finance` |
| Tệp | `reports/payroll.xlsx` |
| Recovery points | 01:00 và 13:00 |
| Thời điểm lỗi | 13:40 |
| Thời điểm phát hiện | 14:15 |
| Mục tiêu | Lấy lại file trước khi bị sửa, không ghi đè dữ liệu mới khi chưa xác minh |

### Nhiệm vụ

1. Chọn recovery point nào hợp lý hơn và giải thích.
2. Nêu sự khác biệt giữa tìm file từ snapshot và khôi phục cả share.
3. Lập kế hoạch khôi phục an toàn, có người xác nhận nội dung.
4. Giải thích nếu sau đó share `finance` bị xóa thì nên kiểm tra cơ chế nào.
5. Đánh giá khả năng bảo vệ nếu toàn bộ storage account không còn truy cập được.
6. Viết ít nhất ba cảnh báo hoặc chỉ số nên giám sát.
7. Nêu cách kiểm tra rằng hệ thống sử dụng Azure File Sync sẽ thấy dữ liệu sau khi restore.

### Lời giải tham khảo

**Chọn recovery point 13:00:** vì đây là mốc mới nhất **trước khi ghi đè lúc 13:40**. File được phục hồi có thể thiếu thay đổi hợp lệ giữa 13:00 và 13:40, nên cần xác nhận với người phụ trách nghiệp vụ.

**Các bước:**

1. Kiểm tra snapshot/recovery point 13:00 có file `reports/payroll.xlsx`.
2. Tải hoặc copy file sang vị trí riêng như `restored/payroll-1300.xlsx`.
3. Kiểm tra mở file, các sheet, công thức và dữ liệu quan trọng.
4. Xin xác nhận từ kế toán trước khi thay thế bản hiện hành.
5. Sau thay thế, kiểm tra các chương trình liên quan đọc file đúng và quyền truy cập không thay đổi.
6. Lưu bằng chứng recovery point, thời gian, người phê duyệt và kết quả.

**Nếu share bị xóa:** kiểm tra file share soft delete và thời hạn lưu; sau đó đánh giá backup còn phục hồi được không. **Nếu account bị mất:** snapshot nằm cùng account không phải bản sao độc lập; cần xác minh có vaulted backup hoặc phương án lưu ngoài account thực sự được thiết lập.

**Theo dõi:** thời gian backup thành công gần nhất, số job lỗi, số recovery points còn khả dụng, thời gian restore thử nghiệm, trạng thái soft delete và dung lượng snapshots.

**Azure File Sync:** xác minh trạng thái sync, server endpoint và những thay đổi đã đồng bộ; thử đọc file ở máy người dùng và theo dõi đồng bộ sau phục hồi theo runbook.

### Tiêu chí hoàn thành

Bài thực hành đạt khi có:

- Recovery point được chọn dựa trên **thời điểm sự cố**.
- Cách phục hồi không gây mất thêm dữ liệu hợp lệ.
- Bằng chứng file có thể mở và quyền truy cập chính xác.
- Phương án riêng cho file deletion, share deletion và account-level disaster.
- Kế hoạch giám sát và kiểm thử RPO/RTO.

## 19. Tự kiểm tra kiến thức

**Câu 1.** Share snapshot của Azure Files có phải bản sao độc lập ở storage account khác không?

A. Có, mọi snapshot tự lưu vào Recovery Services vault.  
B. Không, snapshot gắn với file share/storage account nguồn.  
C. Có, vì snapshot là chỉ đọc.

**Đáp án: B.** “Chỉ đọc” không đồng nghĩa “bản sao độc lập”. Snapshot cần được bổ sung bằng chính sách backup thích hợp khi muốn chống sự cố cấp account.

**Câu 2.** Một nhân viên xóa một file bên trong share vẫn còn tồn tại. Soft delete của file share có phải cách khôi phục chính không?

**Đáp án:** Không. Share soft delete tập trung vào thao tác **xóa cả file share**. Để phục hồi một file, dùng share snapshot, recovery point hoặc cơ chế version/backup phù hợp.

**Câu 3.** Azure Backup đã tạo protected item nhưng chưa có recovery point thành công. Đã đủ bằng chứng dữ liệu được bảo vệ chưa?

**Đáp án:** Chưa. Cần backup job thành công, recovery point có thể chọn và restore test.

**Câu 4.** Công ty có recovery point lúc 01:00 và 07:00; phát hiện ransomware lúc 14:00. Nên mặc định chọn 07:00 vì gần nhất không?

**Đáp án:** Không. Phải xác định thời điểm bắt đầu bị xâm nhập/mã hóa, chọn recovery point **sạch**, kiểm tra dữ liệu trước khi phục hồi Production.

**Câu 5.** Vì sao Azure Storage GRS/GZRS không tự thay thế backup phiên bản cũ?

**Đáp án:** Redundancy giúp tăng độ bền dữ liệu và khả năng chịu sự cố hạ tầng, nhưng thay đổi hoặc xóa dữ liệu hợp lệ vẫn có thể được sao chép. Backup/snapshot cung cấp các recovery points để chọn trạng thái cũ.

**Câu 6.** “Backup hằng ngày” có chắc chắn đạt RPO 30 phút không?

**Đáp án:** Không. RPO phụ thuộc vào thời điểm recovery point thành công gần nhất và thời điểm lỗi. Cần cơ chế bảo vệ có tần suất đủ ngắn và phù hợp khả năng dịch vụ.

**Câu 7.** Khi restore file quan trọng, vì sao nên phục hồi ra tên khác trước?

**Đáp án:** Để kiểm tra nội dung, tránh ghi đè những thay đổi hợp lệ mới hơn và giảm tác động nếu chọn nhầm snapshot.

**Câu 8.** Nếu client SMB dùng Windows, có thể xem share snapshots ở đâu trong một số môi trường hỗ trợ?

**Đáp án:** Trong **Previous Versions** của file/folder; khả năng sử dụng phụ thuộc hệ điều hành, SMB, mount, quyền và hỗ trợ dịch vụ.

**Câu 9.** Khi dùng Azure File Sync, một snapshot trên cloud share có chắc chứa mọi dữ liệu vừa ghi ở Windows Server nhưng chưa đồng bộ không?

**Đáp án:** Không. Snapshot ghi trạng thái cloud share tại thời điểm tạo; các thay đổi chưa đồng bộ có thể chưa xuất hiện.

**Câu 10.** Vì sao không nên tự xóa snapshots đang do Azure Backup quản lý?

**Đáp án:** Có thể phá vỡ recovery points, retention hoặc trạng thái bảo vệ. Cần dùng chính sách và quy trình quản trị của dịch vụ backup.

**Câu 11.** Những điểm nào phải xác minh trước khi dùng vaulted backup cho một file share premium hoặc NFS?

**Đáp án:** Khả năng hỗ trợ theo protocol, kiểu/tier share, region, backup policy, recovery target, retention, quyền và chi phí thực tế.

**Câu 12.** Khi restore job báo hoàn tất, có thể kết luận RTO và tính toàn vẹn ứng dụng đã đạt chưa?

**Đáp án:** Chưa. Cần đo thời gian đến khi **người dùng/ứng dụng sử dụng dữ liệu trở lại**, kiểm tra file, quyền, mount/DNS và những phụ thuộc của ứng dụng.

**Tóm lại**, file share snapshots giúp quay lại một thời điểm trong quá khứ, Azure Backup tổ chức recovery points và retention, soft delete hỗ trợ cứu file share bị xóa, còn các lựa chọn vaulted backup được hỗ trợ có thể bổ sung khả năng chống sự cố ở phạm vi rộng hơn. Một kế hoạch bảo vệ Azure Files chỉ được coi là đáng tin cậy khi **có recovery points phù hợp, đã thử phục hồi, biết ai được phép thực hiện và đo được RPO/RTO trong thực tế**.
