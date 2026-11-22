# Quy trình xử lý sự cố, thu hồi ảnh và giải phóng dung lượng

Trong vận hành Java CRaC, checkpoint image là một artifact có vòng đời riêng. Image có thể bị lỗi, không còn tương thích với runtime mới, chứa credential đã bị thu hồi, hoặc chiếm dung lượng lưu trữ sau nhiều lần tạo và nhân bản. Khi xảy ra sự cố, nhóm vận hành cần vừa khôi phục dịch vụ vừa kiểm soát các bản image, bản sao, snapshot và tài nguyên còn được tham chiếu.

Cần phân biệt **CRaC checkpoint image** với **container image**. Container image chứa filesystem và các layer để tạo container; checkpoint image chứa trạng thái của một tiến trình đang chạy. Hai artifact có thể được lưu ở cùng registry hoặc storage, nhưng có metadata, điều kiện tương thích, rủi ro và quy trình thu hồi khác nhau.

Một quy trình tốt phải trả lời được bốn câu hỏi: image nào đang được sử dụng, image nào còn được phép restore, image nào cần cách ly hoặc thu hồi, và dữ liệu nào thực sự được giải phóng sau khi xóa.

## 1. Phân loại sự cố CRaC

Các sự cố thường gặp có thể chia thành những nhóm sau:

| Nhóm | Dấu hiệu | Mục tiêu xử lý |
|---|---|---|
| Checkpoint thất bại | Callback beforeCheckpoint() ném exception hoặc runtime không ghi được image | Phục hồi tiến trình gốc và xác định bước thất bại |
| Image không hợp lệ | Checksum sai, thiếu file, metadata không khớp | Ngăn restore từ artifact hỏng |
| Restore thất bại | Runtime không khôi phục được process hoặc callback afterRestore() thất bại | Chuyển sang image hợp lệ hoặc cold startup |
| Image không còn tương thích | JDK, native library, kernel hoặc cấu hình đã thay đổi | Chặn restore và tạo image mới |
| Image bị nghi xâm phạm | Quyền truy cập bất thường, image bị sửa hoặc credential có thể bị lộ | Cách ly artifact, thu hồi credential và điều tra |
| Image hết hạn | Không còn phù hợp với release hoặc retention policy | Ngừng phân phối và thu hồi có kiểm soát |
| Storage pressure | Filesystem đầy, inode cạn hoặc quota vượt ngưỡng | Giải phóng đúng artifact hết hạn mà vẫn giữ rollback |
| Restore loop | Instance liên tục restore rồi fail hoặc restart | Dừng vòng lặp và chuyển sang đường phục hồi ổn định |

Không nên xử lý tất cả trường hợp bằng cách xóa image mới nhất. Trước tiên phải xác định phạm vi ảnh hưởng, trạng thái process đang chạy và image còn được dùng làm nguồn rollback hay không.

## 2. Phân biệt artifact và các bản sao

Một checkpoint image có thể tồn tại ở nhiều vị trí:

- Thư mục tạm khi runtime tạo checkpoint.
- Thư mục checkpoint chính trên node.
- Artifact store hoặc object storage.
- Bản sao được cache trên node restore.
- Volume snapshot hoặc backup.
- Bản sao trong môi trường staging hoặc disaster recovery.
- Bản sao phục vụ điều tra sự cố.

Xóa file ở một vị trí không có nghĩa mọi bản sao đã biến mất. Ngược lại, xóa một object trong artifact store có thể không giải phóng dung lượng vật lý ngay nếu storage sử dụng versioning, snapshot, replication hoặc deduplication.

Nên quản lý checkpoint image bằng một định danh bất biến và manifest. Không dùng tên file hoặc thư mục làm bằng chứng duy nhất về danh tính artifact.

### Metadata nên lưu cho mỗi image

| Trường | Mục đích |
|---|---|
| Image ID | Định danh duy nhất của checkpoint image |
| Digest/checksum | Kiểm tra nội dung artifact |
| Signature/key ID | Xác minh nguồn tạo và tính xác thực nếu có ký |
| Application build | Phiên bản ứng dụng được checkpoint |
| JDK vendor/version/build | Phiên bản runtime đã tạo image |
| CRaC implementation | Bản phân phối và phiên bản CRaC |
| OS/kernel/architecture | Điều kiện môi trường quan trọng |
| Native dependency version | Phiên bản thư viện hoặc driver native |
| Configuration generation | Phiên bản cấu hình tương ứng |
| Created at | Thời điểm tạo image |
| Last restored at | Lần restore gần nhất |
| Restore references | Deployment hoặc workload còn sử dụng image |
| Encryption key reference | Khóa mã hóa độc lập dùng bảo vệ image |
| Lifecycle state | Trạng thái hiện tại của artifact |
| Retention deadline | Thời điểm sớm nhất có thể thu hồi theo policy |

Không đưa password, token hoặc nội dung secret vào manifest. Chỉ lưu identifier hoặc version reference cần thiết để kiểm tra và cấp lại secret.

## 3. Quản lý trạng thái vòng đời image

Nên quản lý image bằng trạng thái rõ ràng thay vì chỉ dựa vào sự tồn tại của file:

~~~text
CREATING
   |
   v
VALIDATING
   |
   v
AVAILABLE
   |
   +------> QUARANTINED
   |             |
   |             v
   |          REVOKED
   |             |
   v             v
EXPIRED ------> DELETING
                  |
                  v
                DELETED
~~~

Ý nghĩa:

- **CREATING:** runtime đang tạo image; không được phân phối.
- **VALIDATING:** kiểm tra tính toàn vẹn, metadata và khả năng restore.
- **AVAILABLE:** đã được xác minh và có thể dùng theo policy.
- **QUARANTINED:** tạm thời không cho restore trong khi điều tra.
- **REVOKED:** không còn được phép dùng để tạo instance mới.
- **EXPIRED:** đã hết thời gian sử dụng theo retention policy.
- **DELETING:** quy trình xóa đã bắt đầu và đang xử lý các bản sao.
- **DELETED:** đã xác nhận artifact cùng các bản sao thuộc phạm vi quản lý đã được xử lý.

Một image có thể đang được instance đã restore sử dụng làm trạng thái ban đầu, nhưng không vì vậy mà image gốc còn được phép dùng cho những lần restore mới. Trạng thái phục vụ instance và trạng thái phân phối artifact cần được theo dõi riêng.

Không sửa nội dung image tại chỗ để chuyển nó sang phiên bản mới. Tạo artifact mới với ID và digest mới; giữ lịch sử của image cũ để audit và rollback.

## 4. Quy trình phản ứng ban đầu khi có sự cố

Khi phát hiện sự cố liên quan đến checkpoint hoặc restore:

1. Xác định workload, node, image ID và deployment generation bị ảnh hưởng.
2. Ghi nhận thời điểm, log runtime, exception chain và trạng thái process.
3. Xác định instance nào vẫn đang phục vụ request.
4. Tạm dừng tạo hoặc phân phối image mới nếu nguyên nhân có thể lan rộng.
5. Ngăn orchestration tiếp tục restore từ image đang nghi ngờ.
6. Bảo toàn log, manifest, checksum và artifact cần cho điều tra.
7. Chọn đường phục hồi: image last-known-good đã xác minh hoặc cold startup.
8. Chỉ mở traffic khi readiness và dependency đã được xác nhận.

Nếu sự cố có dấu hiệu xâm phạm bảo mật, cách ly image và thu hồi credential cần được xử lý song song. Không xóa artifact trước khi đã bảo toàn bằng chứng cần thiết theo quy trình incident response của tổ chức.

### Phân loại mức độ ảnh hưởng

| Mức | Ví dụ | Hành động |
|---|---|---|
| Sev 1 | Image production có thể chứa credential bị lộ; nhiều workload bị ảnh hưởng | Cách ly ngay, chặn restore mới, phối hợp thu hồi secret và khôi phục dịch vụ |
| Sev 2 | Image hỏng hoặc restore thất bại trên một nhóm node | Chặn image lỗi, chuyển sang artifact hợp lệ hoặc cold startup |
| Sev 3 | Image cũ, hết hạn hoặc storage sắp đầy nhưng dịch vụ vẫn ổn định | Lên lịch thu hồi, giữ rollback và theo dõi dung lượng |
| Sev 4 | Metadata thiếu hoặc cảnh báo retention chưa ảnh hưởng runtime | Sửa metadata theo quy trình, bổ sung audit và kiểm tra |

Mức độ cụ thể cần tuân theo chính sách vận hành của hệ thống. Bảng trên chỉ là khung phân loại để thống nhất cách phản ứng.

## 5. Xử lý checkpoint thất bại

Nếu beforeCheckpoint() ném exception, quá trình chuẩn bị checkpoint không hoàn tất. Những thao tác trước exception có thể đã thay đổi trạng thái ứng dụng: request gate đã đóng, worker đã dừng hoặc connection pool đã đóng.

Không giả định CRaC tự rollback những side effect đó.

### Nếu ứng dụng gọi Core.checkpointRestore()

Khi ứng dụng điều phối checkpoint qua API, luồng gọi có thể bắt CheckpointException và phục hồi tiến trình gốc:

~~~java
try {
    Core.checkpointRestore();

    // Tiến trình đã được restore và afterRestore() đã xử lý resource.
    markRestored();

} catch (CheckpointException checkpointFailure) {
    try {
        reopenResourcesClosedForCheckpoint();
        restartWorkers();
        resumeRequestGate();
    } catch (Exception recoveryFailure) {
        checkpointFailure.addSuppressed(recoveryFailure);
        markNotReady();
    }

    throw checkpointFailure;

} catch (RestoreException restoreFailure) {
    markNotReady();
    throw restoreFailure;
}
~~~

Ví dụ là khung điều phối. Chỉ mở request gate sau khi mọi resource đã phục hồi thành công. Nếu recovery thất bại, giữ instance ở trạng thái not-ready và để orchestration xử lý.

### Nếu checkpoint được yêu cầu bằng jcmd

Ví dụ kích hoạt checkpoint từ terminal:

~~~bash
jcmd <pid> JDK.checkpoint
~~~

Luồng ứng dụng không có catch block bao quanh lời gọi từ terminal bên ngoài. Cần quan sát kết quả lệnh, log runtime và trạng thái process. Nếu ứng dụng cần rollback ngay trong process gốc, thiết kế một cơ chế recovery độc lập hoặc điều phối qua API trong ứng dụng.

### Image được tạo dở

Nếu runtime thất bại giữa lúc ghi image, artifact có thể chỉ là file một phần. Không đưa file đó vào trạng thái AVAILABLE. Đánh dấu thất bại, giữ log phục vụ điều tra và xóa artifact tạm sau khi xác nhận không có process hoặc runtime operation còn sử dụng nó.

Quy trình tạo image nên ghi ra vùng staging riêng, chỉ chuyển sang vị trí phân phối sau khi runtime báo thành công và bước validation hoàn tất.

## 6. Xử lý restore thất bại

Restore có thể thất bại trước khi ứng dụng gọi được callback, trong runtime, hoặc trong afterRestore() khi mở lại tài nguyên.

Cần phân biệt:

- **Runtime restore failure:** process không được khôi phục đến mức ứng dụng có thể thực thi callback.
- **Application restore failure:** process đã phục hồi nhưng callback hoặc dependency initialization thất bại.
- **Readiness failure:** callback hoàn tất nhưng health check, worker hoặc dependency chưa sẵn sàng.

Không coi process tồn tại là bằng chứng restore thành công.

### Trình tự xử lý

1. Giữ instance khỏi load balancer hoặc traffic router.
2. Thu thập exit code, runtime log và exception chain.
3. Xác định lỗi thuộc image, môi trường hay dependency.
4. Ngăn restart loop bằng retry limit và backoff.
5. Nếu image không hợp lệ, đánh dấu QUARANTINED hoặc REVOKED.
6. Chọn image last-known-good đã xác minh hoặc cold startup.
7. Kiểm tra database, broker, file system, secret và network resource.
8. Chỉ đưa instance vào pool phục vụ khi readiness đạt yêu cầu.

Nếu afterRestore() thất bại sau khi đã mở một phần resource, callback phải cleanup resource vừa tạo hoặc để instance ở trạng thái FAILED. Không nuốt exception rồi đánh dấu READY.

### Chọn giữa image khác và cold startup

| Lựa chọn | Khi phù hợp |
|---|---|
| Restore image last-known-good | Có artifact đã xác minh, tương thích với môi trường và dữ liệu hiện tại |
| Cold startup | Không có image phù hợp hoặc cần loại bỏ trạng thái memory cũ |
| Tạo image mới | Ứng dụng đã khởi động ổn định và có thể tạo checkpoint an toàn |
| Dừng workload | Không thể xác minh tính đúng đắn hoặc an toàn của bất kỳ đường phục hồi nào |

Không tự động restore image cũ hơn nếu schema database, event offset hoặc format dữ liệu đã thay đổi không tương thích. Kiểm tra compatibility manifest trước khi rollback.

## 7. Cách ly và thu hồi image

Cách ly (quarantine) và thu hồi (revoke) có mục tiêu khác nhau:

- **Quarantine:** tạm ngăn việc sử dụng image trong khi xác minh hoặc điều tra.
- **Revoke:** chính thức cấm image được dùng cho các lần restore mới.
- **Delete:** xóa artifact khỏi storage theo retention và evidence policy.

Một image có thể được quarantine trước, sau đó được trả lại AVAILABLE nếu điều tra xác nhận an toàn. Một image đã REVOKED không được phân phối lại chỉ bằng cách đổi tên hoặc copy sang thư mục khác.

### Quy trình quarantine

1. Đặt lifecycle state thành QUARANTINED trong catalog/registry.
2. Chặn scheduler và API phân phối image ID đó cho restore mới.
3. Thu hồi quyền đọc đối với workload không cần điều tra.
4. Ghi nhận digest, signature, metadata và nơi có bản sao.
5. Giữ artifact ở vùng lưu trữ hạn chế quyền truy cập.
6. Xác định các instance đã được restore từ image đó.
7. Quyết định có cần dừng hoặc thay thế các instance đang chạy hay không.

Không di chuyển hoặc đổi tên file đang được runtime đọc trong lúc restore. Trước khi thay đổi storage object, kiểm tra không còn restore operation đang chạy hoặc đang tham chiếu artifact.

### Thu hồi do nghi ngờ lộ secret

Nếu image có thể chứa credential đã bị lộ:

- Chặn mọi lần restore mới từ image.
- Xác định loại credential có thể nằm trong heap hoặc native memory.
- Rotate hoặc revoke password, token, certificate hoặc key theo policy.
- Vô hiệu hóa session hoặc refresh token có thể bị sử dụng lại.
- Kiểm tra audit log để tìm truy cập image bất thường.
- Tạo image mới sau khi workload lấy credential hợp lệ.
- Giữ image cũ ở vùng điều tra hoặc xóa theo quyết định incident response.

Chỉ xóa image không đủ xử lý credential đã bị sao chép. Nếu secret có khả năng bị lộ, phải xử lý secret ở hệ thống cấp phát.

### Bảo toàn bằng chứng

Khi cần điều tra, lưu metadata, digest, audit log, access log và bản artifact được bảo vệ. Hạn chế số người có quyền đọc artifact vì chính image có thể chứa dữ liệu nhạy cảm.

Không tạo thêm bản sao plaintext để tiện debug. Nếu cần phân tích image, dùng môi trường pháp chứng được kiểm soát, audit đầy đủ và retention rõ ràng.

## 8. Thu hồi image cũ hoặc không còn tương thích

Một image có thể không còn phù hợp sau khi:

- Ứng dụng đổi build hoặc dependency.
- JDK vendor, version hoặc CRaC implementation thay đổi.
- Native library hoặc driver thay đổi.
- Kernel, architecture hoặc container runtime thay đổi.
- Cấu hình hoặc secret generation không còn phù hợp.
- Database schema hoặc format dữ liệu đã tiến hóa.
- Certificate, credential hoặc trust policy đã rotate.

Không chỉ dựa vào tuổi image. Một image mới nhưng được tạo từ build lỗi vẫn không hợp lệ; một image cũ có thể vẫn phù hợp nếu mọi điều kiện tương thích được xác nhận.

### Compatibility gate

Trước khi restore, so sánh manifest image với môi trường đích:

| Thành phần | Cần đối chiếu |
|---|---|
| Application build | Build ID và dependency set |
| JDK/CRaC | Vendor, version, build và implementation |
| OS/kernel | Phiên bản và khả năng hỗ trợ checkpoint/restore |
| Architecture | CPU architecture và ABI |
| Native libraries | Phiên bản, đường dẫn và dependency |
| Filesystem | Mount, path và loại filesystem cần thiết |
| Configuration | Generation/version được chấp nhận |
| Data schema | Compatibility với database và persisted state |
| Security | Signature, key reference và policy hiện tại |

Nếu điều kiện bắt buộc không khớp, không thử restore trong production chỉ để xem có chạy được hay không. Dùng môi trường thử nghiệm tương đương hoặc chuyển sang cold startup.

## 9. Retention policy cho checkpoint image

Retention policy xác định image nào phải giữ, giữ trong bao lâu và điều kiện nào cho phép xóa.

Một policy có thể phân loại:

| Loại image | Chính sách gợi ý |
|---|---|
| Current production | Giữ image đang được release sử dụng |
| Last-known-good | Giữ ít nhất một hoặc nhiều bản đã xác minh để rollback |
| Candidate | Giữ trong thời gian rollout/validation |
| Failed checkpoint | Giữ log và artifact cần điều tra; xóa file dở sau khi xác nhận an toàn |
| Quarantined | Giữ trong vùng hạn chế theo incident policy |
| Revoked | Không restore; xóa sau khi hoàn tất điều tra và retention |
| Expired | Xóa khi không còn reference và hết thời gian giữ |
| Test image | TTL ngắn, dọn theo test run hoặc workspace |

Con số thời gian cụ thể cần dựa trên RTO, RPO, tần suất release, chi phí storage, yêu cầu audit và quy định lưu trữ của tổ chức. Không áp dụng một TTL duy nhất cho production, test và forensic artifact.

### Giữ rollback có chủ đích

Trước khi xóa image cũ, xác nhận:

- Release mới đã ổn định.
- Image thay thế đã restore thành công trên môi trường tương đương.
- Không còn rollout hoặc rollback operation tham chiếu image cũ.
- Không có disaster recovery site cần image đó.
- Backup hoặc snapshot cần thiết vẫn được bảo vệ.
- Retention và legal hold đã được kiểm tra.

Giữ đủ số bản last-known-good theo chính sách, không giữ vô hạn mọi image chỉ vì storage chưa đầy.

## 10. Giải phóng dung lượng an toàn

Dung lượng có thể bị tiêu thụ ở nhiều lớp:

- Checkpoint image gốc.
- Bản sao local trên từng node.
- Image staging và file tạm.
- Snapshot volume.
- Backup và object version.
- Log, core dump và diagnostic bundle.
- Filesystem metadata và inode.

Trước khi xóa, xác định filesystem nào đang đầy và thành phần nào chiếm dung lượng.

### Kiểm tra trên Linux

~~~bash
df -h
df -i
findmnt
du -xhd1 /var/lib/myapp/checkpoints
du -xhd1 /var/tmp
~~~

Ý nghĩa:

- df -h hiển thị dung lượng filesystem.
- df -i hiển thị inode còn trống.
- findmnt cho biết mount chứa đường dẫn.
- du -xhd1 ước lượng dung lượng theo thư mục, không đi xuyên filesystem khác.
- Kiểm tra riêng thư mục staging, cache và artifact store.

Lệnh cụ thể có thể khác theo bản phân phối Linux. Chạy trên node hoặc container sở hữu filesystem đang gặp áp lực, không chỉ trên host quản trị.

### Kiểm tra file đã xóa nhưng vẫn được process mở

Trên Linux, file bị unlink nhưng còn được process giữ descriptor vẫn chiếm dung lượng cho đến khi descriptor được đóng:

~~~bash
lsof +L1
~~~

Nếu thấy file lớn có link count bằng 0, xác định process đang giữ file và thực hiện đóng/restart theo quy trình vận hành. Không kill process tùy tiện khi chưa đánh giá ảnh hưởng tới workload.

### Kiểm tra trên PowerShell

Trong môi trường Windows, có thể xem dung lượng volume bằng:

~~~powershell
Get-Volume
Get-PSDrive -PSProvider FileSystem
~~~

Cách kiểm tra file lock và storage snapshot phụ thuộc công cụ của hệ điều hành và storage provider. Với CRaC deployment trên Linux, ưu tiên kiểm tra từ đúng node Linux thực hiện checkpoint/restore.

## 11. Quy trình xóa image an toàn

Không xóa theo wildcard rộng hoặc chỉ vì tên file có vẻ cũ. Xóa phải dựa trên image ID, digest và lifecycle state đã được xác nhận.

Trình tự:

1. Chọn image ở trạng thái EXPIRED hoặc REVOKED và hết retention.
2. Kiểm tra image không có restore operation đang chạy.
3. Kiểm tra không còn deployment, rollback plan hoặc disaster recovery reference.
4. Kiểm tra không có legal hold hoặc yêu cầu bảo toàn evidence.
5. Đặt state thành DELETING để chặn consumer mới.
6. Xóa object gốc theo API của storage provider.
7. Xóa cache và staging copy theo image ID.
8. Xử lý replica, version, snapshot và backup theo retention policy.
9. Ghi audit event và kết quả từng bước.
10. Xác minh artifact không còn được catalog phân phối.
11. Kiểm tra dung lượng thực tế đã được thu hồi hoặc ghi nhận lý do chưa thu hồi.
12. Đặt state thành DELETED khi các bước bắt buộc hoàn tất.

### Idempotency

Quy trình cleanup cần có thể chạy lại an toàn. Nếu object đã bị xóa, lần chạy tiếp theo nên nhận diện trạng thái đó và tiếp tục xử lý bản sao còn lại.

Không đánh dấu DELETED chỉ vì lệnh xóa file gốc trả về thành công. Có thể còn object version, snapshot, replica hoặc file descriptor đang mở.

### Không xóa image đang được restore

Một image có thể đang được đọc bởi runtime hoặc đang được phân phối tới node khác. Trước khi xóa, cần có reference tracking hoặc trạng thái operation để xác nhận không còn restore in-flight.

Nếu hệ thống chưa có reference tracking, hãy dùng một khoảng drain/quiescence được điều phối rõ ràng và xác nhận các restore operation đã kết thúc trước khi cleanup.

## 12. Giải phóng dung lượng từ snapshot và object storage

Xóa một checkpoint image có thể không làm dung lượng vật lý giảm ngay:

- Object storage có versioning giữ phiên bản cũ.
- Volume snapshot có thể tham chiếu block dữ liệu dùng chung.
- Backup retention có thể giữ bản sao.
- Deduplication hoặc compression làm số liệu logical và physical khác nhau.
- Storage provider có quá trình garbage collection bất đồng bộ.

Vì vậy, phân biệt:

- **Logical size:** kích thước artifact được hiển thị trong catalog.
- **Allocated size:** dung lượng đã cấp phát trên filesystem hoặc volume.
- **Physical usage:** dung lượng backend thực sự sử dụng sau deduplication/compression.
- **Reclaimable space:** dung lượng có thể được giải phóng khi không còn reference.

Sau cleanup, đo lại bằng metric của storage provider hoặc filesystem. Nếu logical size giảm nhưng physical usage chưa giảm, kiểm tra versioning, snapshot và garbage collection trước khi tiếp tục xóa dữ liệu khác.

Không xóa snapshot toàn volume chỉ để thu hồi vài image nếu snapshot đó còn chứa dữ liệu nghiệp vụ hoặc là điểm rollback của hệ thống.

## 13. Xử lý disk pressure theo mức độ

### Cảnh báo dung lượng

Khi dung lượng bắt đầu tăng nhanh:

1. Xác định filesystem và mount bị ảnh hưởng.
2. Tìm thư mục tăng trưởng lớn nhất.
3. Kiểm tra tốc độ tạo image và số bản sao.
4. Dừng tạo checkpoint thử nghiệm không cần thiết.
5. Xác định image hết hạn đã đủ điều kiện cleanup.
6. Kiểm tra quota và inode.
7. Lên lịch dọn theo retention policy.

### Dung lượng gần cạn

Khi filesystem gần đầy:

1. Tạm dừng checkpoint creation mới nếu có nguy cơ làm đầy filesystem.
2. Giữ các artifact cần cho rollback và disaster recovery.
3. Xóa staging file thất bại đã xác nhận không còn được sử dụng.
4. Thu hồi cache image local không còn reference.
5. Cleanup image hết hạn theo từng ID.
6. Theo dõi dung lượng sau mỗi batch.
7. Mở lại checkpoint workflow khi còn đủ headroom.

### Filesystem đã đầy

Khi filesystem đầy:

1. Giữ nguyên artifact last-known-good.
2. Dừng tác vụ tạo image và copy không thiết yếu.
3. Xác định file tạm, log hoặc artifact đã hết hạn.
4. Xóa từng mục đã xác minh đủ điều kiện.
5. Kiểm tra inode và file descriptor bị giữ.
6. Xác nhận ứng dụng có thể ghi log và dữ liệu cần thiết.
7. Không tạo checkpoint mới cho đến khi có đủ dung lượng an toàn.

Không xóa ngẫu nhiên thư mục checkpoint để làm trống disk. Có thể xóa nhầm image duy nhất dùng để rollback hoặc image đang được một restore operation tham chiếu.

## 14. Ngăn restore loop và checkpoint loop

Một instance có thể restore từ image, thất bại trong afterRestore(), bị orchestration restart rồi lại restore cùng image. Vòng lặp này vừa làm dịch vụ gián đoạn vừa tiêu thụ CPU, I/O và log.

Nên ghi nhận:

- Image ID và digest.
- Restore attempt number.
- Node và deployment generation.
- Callback cuối cùng đã chạy.
- Exception class và cause.
- Resource thất bại.
- Thời gian từ lần thử trước.
- Quyết định retry hoặc fallback.

Áp dụng:

- Retry limit.
- Exponential backoff có jitter.
- Circuit breaker hoặc trạng thái image tạm ngừng phân phối.
- Chuyển sang last-known-good nếu được xác minh.
- Cold startup khi không có image phù hợp.
- Alert khi cùng image thất bại lặp lại.

Không retry vô hạn một image có lỗi xác định như checksum sai hoặc compatibility mismatch. Đánh dấu image QUARANTINED hoặc REVOKED để scheduler không tiếp tục chọn nó.

## 15. Thu hồi image khi phát hiện rủi ro bảo mật

Nếu có bằng chứng image bị sửa, bị tải xuống trái phép hoặc chứa credential có thể bị lộ, xử lý theo incident response:

~~~text
Phát hiện image đáng ngờ
          |
          v
Chặn restore mới từ image
          |
          v
Cách ly artifact và bảo toàn bằng chứng
          |
          v
Xác định instance và credential bị ảnh hưởng
          |
          v
Rotate / revoke secret
          |
          v
Đánh giá instance đang chạy
          |
          v
Tạo image mới từ workload tin cậy
          |
          v
Xác minh và phân phối image mới
          |
          v
Xóa artifact cũ theo evidence / retention policy
~~~

Một chữ ký hợp lệ không chứng minh image an toàn nếu signing key hoặc build pipeline đã bị xâm phạm. Cần xem xét nguồn tạo, quyền truy cập, build provenance, digest và audit trail.

Nếu image bị sửa nhưng checksum trong manifest cũng bị thay đổi, checksum đơn thuần không đủ. Dùng chữ ký được xác minh bằng trust root độc lập và kiểm soát quyền cập nhật metadata.

## 16. Phục hồi dịch vụ sau khi thu hồi image

Sau khi image bị thu hồi, cần đảm bảo workload không còn phụ thuộc vào image đó cho lần restart tiếp theo.

Các bước:

1. Chọn image thay thế đã được xác minh hoặc cold startup.
2. Xác nhận tương thích với JDK, kernel, native library và cấu hình.
3. Kiểm tra secret và credential hiện hành.
4. Restore trong một nhóm nhỏ hoặc môi trường canary.
5. Chờ resource reopen và readiness hoàn tất.
6. Kiểm tra request, error rate và dependency.
7. Mở rộng rollout khi canary ổn định.
8. Cập nhật catalog để image mới là artifact được phép phân phối.
9. Giữ image cũ ở trạng thái revoked/quarantine theo policy.
10. Xác minh orchestration không còn chọn image cũ.

Không thay đổi image ID của deployment đang chạy mà không cập nhật catalog hoặc release metadata. Cần có một nguồn sự thật duy nhất để scheduler biết image nào được phép dùng.

## 17. Giám sát vòng đời image và dung lượng

Nên theo dõi cả trạng thái artifact lẫn tác động lên storage.

### Metric gợi ý

| Metric | Ý nghĩa |
|---|---|
| crac_checkpoint_images_available | Số image đang được phép dùng |
| crac_checkpoint_images_quarantined | Số image đang cách ly |
| crac_checkpoint_image_bytes | Logical size theo image hoặc nhóm |
| crac_checkpoint_create_failures_total | Số lần tạo checkpoint thất bại |
| crac_restore_failures_total | Số lần restore thất bại |
| crac_restore_retries_total | Số lần retry |
| crac_image_cleanup_total | Số artifact đã cleanup |
| crac_image_cleanup_failures_total | Số lần cleanup thất bại |
| checkpoint_storage_free_bytes | Dung lượng còn trống |
| checkpoint_storage_free_inodes | Inode còn trống |
| checkpoint_storage_reclaimable_bytes | Dung lượng có thể thu hồi nếu provider hỗ trợ |

Metric theo image ID có thể tạo cardinality lớn. Dùng log hoặc inventory catalog cho từng ID; metric nên nhóm theo environment, lifecycle state hoặc storage class.

### Alert gợi ý

- Restore failure tăng bất thường.
- Cùng image thất bại nhiều lần liên tiếp.
- Image ở trạng thái CREATING quá lâu.
- Image QUARANTINED vẫn được yêu cầu restore.
- Dung lượng hoặc inode xuống dưới ngưỡng.
- Cleanup job thất bại liên tục.
- Artifact không có owner hoặc retention metadata.
- Image cũ vẫn được deployment tham chiếu.
- Restore từ image có digest không khớp catalog.

## 18. Ví dụ runbook cho image hỏng

Tình huống: một nhóm instance không restore được từ image mới.

**Phát hiện:** restore failure tăng, các instance chưa đạt READY.

**Ứng phó:**

1. Tạm dừng rollout và ngăn scheduler tạo thêm instance từ image đó.
2. Ghi lại image ID, digest, runtime version và log.
3. Đặt image thành QUARANTINED.
4. Xác nhận các instance đang chạy từ image trước đó có bị ảnh hưởng không.
5. Chọn image last-known-good đã restore thành công trên cùng môi trường.
6. Nếu không có image phù hợp, chuyển sang cold startup.
7. Kiểm tra readiness, dependency và request trên canary.
8. Chỉ tiếp tục rollout khi tỷ lệ restore và request ổn định.

**Sau sự cố:**

- Xác định nguyên nhân là image corruption, incompatibility hay dependency.
- Tạo image mới sau khi ứng dụng chạy ổn định.
- Kiểm tra image mới trước khi đánh dấu AVAILABLE.
- Giữ artifact lỗi theo thời gian điều tra cần thiết rồi cleanup.
- Bổ sung kiểm tra để ngăn cùng lỗi lặp lại.

## 19. Ví dụ runbook cho disk pressure

Tình huống: filesystem chứa checkpoint image đạt ngưỡng cảnh báo.

**Phát hiện:** free bytes hoặc free inodes giảm nhanh.

**Ứng phó:**

1. Xác định filesystem bằng df và findmnt.
2. Xác định thư mục chiếm dung lượng bằng du.
3. Tạm dừng tạo checkpoint mới nếu không đủ headroom.
4. Liệt kê image theo lifecycle state, tuổi và reference.
5. Giữ current production và last-known-good.
6. Xóa staging artifact thất bại đã xác nhận không còn được dùng.
7. Xóa image EXPIRED đã hết retention và không còn reference.
8. Dọn cache local theo image ID.
9. Kiểm tra object version, snapshot và backup retention.
10. Đo lại logical và physical usage.
11. Mở lại checkpoint workflow khi có headroom an toàn.

Không xóa log hoặc diagnostic evidence đang cần cho incident. Nếu log là nguyên nhân chiếm dung lượng, áp dụng rotation hoặc chuyển sang storage riêng theo policy.

## 20. Checklist trước khi xóa một image

Trước khi chuyển image sang DELETING, xác nhận:

- Image ID và digest đã được xác định chính xác.
- State là EXPIRED hoặc REVOKED.
- Không có restore operation đang đọc image.
- Không có deployment hoặc rollback plan tham chiếu image.
- Đã có artifact thay thế nếu workload cần restore.
- Retention period đã hết.
- Không có legal hold hoặc forensic hold.
- Bản backup cần giữ đã được xác nhận.
- Các bản sao local, remote và cache đã được liệt kê.
- Audit event đã được ghi.
- Có thể kiểm tra dung lượng sau cleanup.

Nếu bất kỳ điều kiện bắt buộc nào chưa rõ, giữ image và chuyển sang bước điều tra. Không dùng disk pressure làm lý do bỏ qua kiểm soát reference và retention.

## 21. Quy trình vận hành tổng thể

### Khi tạo checkpoint

1. Ghi manifest và image ID duy nhất.
2. Tạo artifact trong staging area.
3. Chờ runtime báo checkpoint thành công.
4. Xác minh checksum, signature và compatibility metadata.
5. Chạy restore test trên môi trường phù hợp.
6. Chuyển state sang AVAILABLE.
7. Ghi owner, retention deadline và vị trí các bản sao.

### Khi restore

1. Chọn image state AVAILABLE.
2. Kiểm tra digest, signature và compatibility gate.
3. Xác nhận mount, secret và dependency cần thiết.
4. Bắt đầu restore trong giới hạn retry.
5. Theo dõi runtime và afterRestore().
6. Chỉ đưa instance vào phục vụ khi readiness thành công.
7. Ghi lại restore generation và image reference.

### Khi có sự cố

1. Dừng phân phối image đáng ngờ.
2. Cách ly artifact và bảo toàn bằng chứng.
3. Xác định instance, dependency và credential bị ảnh hưởng.
4. Phục hồi bằng image last-known-good hoặc cold startup.
5. Kiểm tra dịch vụ trước khi mở traffic.
6. Thu hồi credential nếu có khả năng bị lộ.
7. Ghi lại nguyên nhân và hành động khắc phục.

### Khi giải phóng dung lượng

1. Kiểm tra filesystem, inode và quota.
2. Liệt kê image hết hạn và reference.
3. Giữ image hiện tại, rollback và forensic artifact cần thiết.
4. Chuyển candidate sang DELETING.
5. Xóa artifact gốc, cache, replica và bản sao hết hạn.
6. Kiểm tra snapshot/version retention.
7. Đo lại dung lượng vật lý.
8. Đặt DELETED sau khi xác nhận hoàn tất.

## 22. Nguyên tắc cần ghi nhớ

- CRaC checkpoint image khác container image và cần lifecycle policy riêng.
- Dùng image ID, digest và manifest để quản lý artifact; không chỉ dựa vào tên file.
- Phân biệt QUARANTINED, REVOKED và DELETED.
- Checkpoint failure có thể để lại side effect trong tiến trình gốc; phải phục hồi resource đã thay đổi.
- Restore failure không được đánh dấu READY hoặc tiếp tục nhận traffic.
- Không retry vô hạn cùng một image lỗi.
- Quarantine image trước khi điều tra; bảo toàn evidence nếu có dấu hiệu xâm phạm.
- Nếu secret có thể bị lộ, rotate hoặc revoke credential; xóa image đơn thuần không đủ.
- Giữ last-known-good và kiểm tra compatibility trước khi rollback.
- Retention phải tính cả artifact gốc, cache, replica, snapshot, backup và staging.
- Không xóa image đang được restore hoặc còn reference.
- Dùng cleanup idempotent và audit từng bước.
- Xác minh dung lượng thực tế sau khi xóa; logical deletion không luôn giải phóng physical blocks ngay.
- Khi disk pressure, dọn từng artifact đã xác minh thay vì xóa wildcard.
- Theo dõi restore failure, image state, storage bytes, inode và cleanup failure.

Quản lý checkpoint image là một phần của vận hành production. Khi image có định danh, trạng thái, compatibility metadata và retention rõ ràng, nhóm vận hành có thể cách ly artifact lỗi, phục hồi bằng image tin cậy hoặc cold startup, thu hồi credential khi cần và giải phóng dung lượng mà vẫn giữ được đường rollback cùng bằng chứng phục vụ điều tra.
