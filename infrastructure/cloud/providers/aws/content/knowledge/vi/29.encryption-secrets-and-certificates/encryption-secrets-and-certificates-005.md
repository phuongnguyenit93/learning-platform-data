# Rotation, disable, scheduled deletion và khôi phục quyền dùng key

AWS Key Management Service (AWS KMS) quản lý các khóa dùng để bảo vệ dữ liệu trong hệ sinh thái AWS. Một KMS key là tài nguyên logic có mã định danh, chính sách, quyền truy cập và vật liệu mật mã (key material). Khi xoay vòng khóa, KMS có thể thay vật liệu mật mã mà vẫn giữ nguyên tài nguyên logic. Khi vô hiệu hóa hoặc lên lịch xóa, KMS thay đổi trạng thái của tài nguyên và ảnh hưởng trực tiếp đến khả năng thực hiện thao tác mật mã.

Trong một ứng dụng Java hoặc Spring Boot, ứng dụng thường gọi KMS để mã hóa hoặc giải mã data key theo mô hình envelope encryption. Các dịch vụ như Amazon S3, Amazon EBS, Amazon RDS và nhiều dịch vụ AWS khác cũng có thể dùng KMS key để bảo vệ data key. Vì vậy, quản lý vòng đời key cần phối hợp AWS KMS với IAM, chính sách key, CloudTrail, CloudWatch và cấu hình mã hóa của từng dịch vụ.

Bài học này giải thích cách chọn phương thức rotation, khi nào nên disable hoặc scheduled deletion, và cách khôi phục key sau khi thao tác nhầm hoặc khi quyền truy cập bị gián đoạn.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Phân biệt rotation của key material với việc tạo một KMS key mới.
- Chọn automatic rotation, on-demand rotation hoặc manual rotation theo loại key.
- Dự đoán tác động của trạng thái Disabled và PendingDeletion lên ứng dụng, dữ liệu và dịch vụ AWS.
- Lên lịch xóa key có kiểm soát và nhận diện các trường hợp cần xử lý riêng với multi-Region keys.
- Khôi phục khả năng sử dụng key bằng cách sửa trạng thái hoặc quyền truy cập phù hợp.
- Theo dõi thay đổi vòng đời key bằng AWS CloudTrail, Amazon EventBridge và CloudWatch.

## 1. Hiểu trạng thái key trước khi thao tác

KMS key có một trạng thái (key state). Trạng thái cho biết key có thể thực hiện thao tác mật mã hay không. Một thao tác có thể bị từ chối do trạng thái key, do quyền truy cập, hoặc do cả hai nguyên nhân.

| Trạng thái | Ý nghĩa | Hướng xử lý thường gặp |
|---|---|---|
| `Enabled` | Key có thể thực hiện thao tác mật mã nếu principal được cấp quyền. | Kiểm tra chính sách và quyền nếu thao tác vẫn thất bại. |
| `Disabled` | Key vẫn tồn tại nhưng không thể thực hiện thao tác mật mã. | Dùng `EnableKey` sau khi xác nhận có thể mở lại an toàn. |
| `PendingDeletion` | Key đang trong thời gian chờ xóa và không thể thực hiện thao tác mật mã. | Dùng `CancelKeyDeletion` trước khi hết thời gian chờ nếu cần giữ key. |
| `PendingReplicaDeletion` | Multi-Region primary key đang chờ các replica key được xóa. | Kiểm tra và xử lý các replica liên quan. |
| `PendingImport` | Key có nguồn vật liệu mật mã bên ngoài nhưng hiện không có vật liệu hợp lệ để sử dụng. | Nhập lại key material theo quy trình import. |
| `Unavailable` | Key trong custom key store không truy cập được kho khóa nền. | Khôi phục kết nối tới AWS CloudHSM cluster hoặc external key store. |

Hầu hết key được tạo ở trạng thái `Enabled`. Key sử dụng imported key material có thể ở `PendingImport` cho đến khi vật liệu được nhập. `Creating`, `Updating` và `PendingReplicaDeletion` là các trạng thái liên quan đến multi-Region keys. Không nên xử lý mọi lỗi KMS bằng cách bật key: nếu trạng thái là `PendingImport` hoặc `Unavailable`, nguyên nhân nằm ở vật liệu hoặc kho khóa nền.

Cần phân biệt ba lớp thông tin:

1. **KMS key:** tài nguyên logic được tham chiếu bằng key ID hoặc key ARN. Key có chính sách, grants, mô tả, alias và cấu hình.
2. **Key material:** bí mật mật mã thực hiện thao tác mã hóa, giải mã, ký hoặc xác thực. Rotation có thể thay key material mà không tạo tài nguyên logic mới.
3. **Data key và dữ liệu ứng dụng:** data key thường mã hóa dữ liệu thực tế; KMS key thường bảo vệ data key. Rotation của KMS key không tự xoay vòng data key và không tự mã hóa lại dữ liệu.

Hiểu đúng ba lớp này giúp tránh nhầm lẫn giữa rotation, disable và deletion.

## 2. Rotation: thay vật liệu mật mã có kiểm soát

### 2.1. Automatic rotation

Automatic rotation cho phép AWS KMS tự tạo key material mới theo lịch. Tính năng này được hỗ trợ cho customer managed key có loại symmetric encryption và nguồn key material là `AWS_KMS`.

Mặc định, KMS xoay vòng key material sau mỗi 365 ngày. Có thể đặt chu kỳ tùy chỉnh từ 90 đến 2.560 ngày bằng `RotationPeriodInDays`. Chu kỳ được tính từ thời điểm bật rotation và lặp lại theo số ngày đã cấu hình.

AWS managed keys được AWS KMS tự động xoay vòng hằng năm; người dùng không thể bật hoặc tắt lịch rotation của chúng. AWS owned keys do dịch vụ AWS sở hữu và quản lý theo chính sách của dịch vụ đó. Với customer managed keys, automatic rotation là tùy chọn và cần được bật rõ ràng.

Ví dụ bật rotation với chu kỳ 180 ngày:

~~~bash
aws kms enable-key-rotation \
  --key-id <KEY_ID_OR_ARN> \
  --rotation-period-in-days 180

aws kms get-key-rotation-status \
  --key-id <KEY_ID_OR_ARN>
~~~

Lệnh thứ hai giúp kiểm tra `KeyRotationEnabled`, `RotationPeriodInDays` và `NextRotationDate`. Để bật rotation, principal cần quyền `kms:EnableKeyRotation`; việc kiểm tra trạng thái cần quyền `kms:GetKeyRotationStatus`. Quyền hiệu lực còn phụ thuộc key policy và cách tài khoản cấu hình ủy quyền IAM.

Automatic rotation có các đặc điểm quan trọng:

- Key ID, key ARN, Region, key policy và permissions của KMS key được giữ nguyên.
- Ứng dụng và dịch vụ AWS tiếp tục tham chiếu cùng KMS key.
- Khi mã hóa, KMS dùng key material hiện tại.
- Khi giải mã ciphertext cũ, KMS tự chọn phiên bản key material đã dùng để mã hóa ciphertext đó.
- KMS giữ lại key material cũ để có thể giải mã dữ liệu được tạo trước lần rotation.
- Rotation không tự mã hóa lại dữ liệu và không thay thế data key đã được tạo trước đó.

Vì vậy, automatic rotation thường ít gây thay đổi cho ứng dụng đang dùng KMS key làm wrapping key. Tuy nhiên, nó không giải quyết mọi sự cố lộ lọt dữ liệu. Nếu một data key đã bị lộ, chỉ xoay vòng KMS key không làm cho bản data key đã lộ trở nên an toàn; cần đánh giá việc tạo data key mới và mã hóa lại dữ liệu liên quan.

Khi customer managed key bị disable, KMS tạm dừng rotation vật liệu. Sau khi key được enable lại, nếu đã quá ngày rotation theo lịch, KMS sẽ thực hiện rotation ngay; nếu chưa quá hạn, lịch cũ được tiếp tục. Trong thời gian key ở `PendingDeletion`, rotation bị tạm dừng. Nếu hủy lịch xóa, trạng thái rotation trước đó được khôi phục và KMS xử lý rotation nếu đã quá hạn.

### 2.2. On-demand rotation

On-demand rotation khởi tạo việc thay key material ngay khi được yêu cầu, không cần đợi lịch automatic rotation. Có thể dùng tính năng này kể cả khi automatic rotation chưa được bật. Một lần on-demand rotation không thay đổi lịch automatic rotation đã cấu hình.

On-demand rotation hỗ trợ customer managed symmetric encryption keys có nguồn `AWS_KMS` hoặc `EXTERNAL`. Với key có imported key material, cần nhập vật liệu mới trước; vật liệu mới phải ở trạng thái chờ rotation (`Pending rotation`) thì mới có thể chuyển thành vật liệu hiện hành. KMS cho phép tối đa 25 lần on-demand rotation trên mỗi KMS key.

Ví dụ:

~~~bash
aws kms rotate-key-on-demand \
  --key-id <KEY_ID_OR_ARN>

aws kms get-key-rotation-status \
  --key-id <KEY_ID_OR_ARN>
~~~

Thao tác cần quyền `kms:RotateKeyOnDemand`; để kiểm tra tiến trình cần `kms:GetKeyRotationStatus`. Rotation được xử lý nền nên có thể có độ trễ ngắn trước khi hoàn tất. Dùng `ListKeyRotations` để xem thông tin các lần rotation đã hoàn thành.

On-demand rotation không áp dụng cho asymmetric keys, HMAC keys hoặc key trong custom key store. Với các loại này, hãy cân nhắc manual rotation. Đối với một bộ multi-Region keys, chỉ khởi tạo rotation tại primary key. Với imported key material trong multi-Region keys, cần nhập cùng vật liệu mới vào từng Region liên quan trước khi thực hiện rotation trên primary key.

### 2.3. Manual rotation

Manual rotation tạo một KMS key mới rồi chuyển ứng dụng hoặc dịch vụ sang key mới. Đây là phương án cần dùng khi loại key không hỗ trợ automatic hoặc on-demand rotation, hoặc khi tổ chức cần thay đổi thuật toán, key usage, tài khoản, Region hay ranh giới quản trị.

Quy trình tổng quát:

1. Tạo KMS key mới với key spec, key usage, Region và chính sách phù hợp.
2. Cấp quyền cho workload cần sử dụng key mới.
3. Cập nhật alias hoặc cấu hình ứng dụng để các thao tác mã hóa mới dùng key mới.
4. Kiểm thử mã hóa và giải mã qua đúng đường đi của ứng dụng.
5. Lập kế hoạch chuyển đổi ciphertext cũ, data key đã bọc và bản sao lưu. Dữ liệu cũ vẫn có thể cần key cũ để giải mã.
6. Chỉ disable hoặc lên lịch xóa key cũ sau khi xác minh không còn dữ liệu, bản sao lưu hay workload phụ thuộc vào key đó.

Nếu ứng dụng tham chiếu alias, có thể chuyển alias sang key mới để điều hướng các thao tác mới. Việc đổi alias không tự chuyển đổi ciphertext đã được mã hóa bằng key cũ. Cần giữ key cũ khả dụng cho đến khi dữ liệu cũ được giải mã, mã hóa lại hoặc hết thời hạn lưu trữ.

### 2.4. Theo dõi rotation

Có thể xác minh rotation qua nhiều nguồn:

- `GetKeyRotationStatus` cho biết trạng thái automatic rotation và tiến trình on-demand rotation.
- `ListKeyRotations` cho biết lịch sử rotation đã hoàn thành.
- AWS CloudTrail ghi nhận sự kiện `RotateKey` và các thao tác quản trị key.
- Amazon EventBridge phát sự kiện `KMS CMK Rotation` khi key material được xoay vòng.

Với multi-Region keys, KMS đồng bộ key material mới giữa primary và replicas trước khi dùng vật liệu mới cho thao tác mật mã. Cần theo dõi trạng thái trên primary key và xác minh các Region liên quan đã đồng bộ.

## 3. Disable key để tạm dừng sử dụng

`DisableKey` chuyển customer managed key từ `Enabled` sang `Disabled`. Trong trạng thái này, KMS không cho phép dùng key trong các thao tác mật mã. Key vẫn tồn tại, giữ nguyên key material, policy và metadata; người có quyền phù hợp có thể enable lại.

Ví dụ:

~~~bash
aws kms disable-key --key-id <KEY_ID_OR_ARN>

aws kms describe-key \
  --key-id <KEY_ID_OR_ARN> \
  --query "KeyMetadata.{State:KeyState,Enabled:Enabled}"
~~~

Khi đã xác nhận có thể sử dụng lại:

~~~bash
aws kms enable-key --key-id <KEY_ID_OR_ARN>
~~~

Chỉ customer managed keys mới có thể được disable hoặc enable theo cách này. AWS managed keys và AWS owned keys không thể được người dùng trực tiếp disable hoặc enable.

Disable là lựa chọn phù hợp khi cần:

- Tạm dừng một key để điều tra sự cố hoặc kiểm tra phụ thuộc.
- Ngăn workload tiếp tục dùng key trong khi đánh giá cấu hình.
- Thử nghiệm tác động trước khi quyết định xóa key.
- Tạm thời ngăn thao tác mật mã mà vẫn giữ khả năng phục hồi.

Cần hiểu tác động tới dịch vụ sử dụng envelope encryption. Dữ liệu đã được giải mã hoặc data key đang được dịch vụ lưu trong bộ nhớ có thể chưa bị ảnh hưởng ngay. Sự cố thường xuất hiện khi dịch vụ cần gọi KMS để giải mã data key hoặc thực hiện thao tác mật mã tiếp theo. Vì vậy, một workload có thể tiếp tục hoạt động trong một khoảng thời gian rồi mới phát sinh lỗi khi cần KMS.

Khi key bị disable, KMS cũng dừng automatic rotation. Sau khi enable lại, KMS tiếp tục lịch rotation hoặc thực hiện rotation ngay nếu đã quá hạn. Không nên disable một key production để thử nghiệm nếu chưa xác định được workload, bản sao lưu và dịch vụ phụ thuộc.

## 4. Scheduled deletion: lên lịch xóa key

Xóa KMS key là thao tác không thể đảo ngược sau khi thời gian chờ kết thúc. AWS KMS chỉ cho phép lên lịch xóa customer managed key. AWS managed keys và AWS owned keys không thể được người dùng lên lịch xóa.

KMS yêu cầu thời gian chờ từ 7 đến 30 ngày; mặc định là 30 ngày. Khi lệnh được chấp nhận, key chuyển sang `PendingDeletion` và không thể thực hiện thao tác mật mã. Khi hết thời gian chờ, KMS xóa key material, key metadata và các alias liên quan. Thời điểm xóa thực tế có thể muộn hơn thời gian đã đặt tối đa 24 giờ; dùng `DescribeKey` để xem ngày xóa được lên lịch.

Ví dụ lên lịch xóa sau 30 ngày:

~~~bash
aws kms schedule-key-deletion \
  --key-id <KEY_ID_OR_ARN> \
  --pending-window-in-days 30
~~~

KMS ghi nhận thao tác lên lịch xóa và việc xóa thực tế trong AWS CloudTrail. Trong thời gian chờ, hãy theo dõi các lần gọi KMS thất bại để phát hiện workload còn phụ thuộc vào key.

### 4.1. Kiểm tra trước khi lên lịch xóa

Trước khi chạy `ScheduleKeyDeletion`, hãy thực hiện các bước sau:

1. Xác định key đang được dịch vụ AWS, ứng dụng, tài khoản khác hoặc hệ thống ngoài AWS sử dụng.
2. Kiểm tra CloudTrail và cấu hình tài nguyên để tìm hoạt động gần đây; KMS không lưu ciphertext và không cung cấp danh sách đầy đủ mọi dữ liệu đã được mã hóa bằng key.
3. Kiểm tra bản sao lưu, snapshot, log lưu trữ dài hạn, dữ liệu archive và yêu cầu lưu giữ dữ liệu.
4. Xác minh kế hoạch khôi phục thảm họa và khả năng giải mã dữ liệu trong các Region liên quan.
5. Cân nhắc disable key trước, đặt cảnh báo CloudWatch và quan sát lỗi trong khoảng thời gian đủ dài để xác nhận không còn phụ thuộc.
6. Giới hạn quyền `kms:ScheduleKeyDeletion`; có thể dùng condition key `kms:ScheduleKeyDeletionPendingWindowInDays` trong key policy hoặc IAM policy để áp đặt thời gian chờ tối thiểu.

Nếu chưa chắc chắn dữ liệu đã hết phụ thuộc, hãy giữ key ở trạng thái `Disabled` và tiếp tục điều tra. Key disabled vẫn có thể được enable lại; key đã xóa vĩnh viễn thì không thể khôi phục theo quy trình thông thường.

### 4.2. Trường hợp multi-Region key

Khi lên lịch xóa multi-Region primary key còn replica, primary key chuyển sang `PendingReplicaDeletion`. Phải lên lịch xóa tất cả replica keys và chờ chúng được xóa. Thời gian chờ xóa primary chỉ bắt đầu sau khi replica cuối cùng được xóa.

Replica key có thể được tạo lại bằng cách replicate primary key còn tồn tại trong cùng Region. Tuy nhiên, xóa primary key là quyết định có ảnh hưởng đến toàn bộ bộ key liên quan; cần kiểm tra kế hoạch phục hồi và các Region sử dụng trước khi thực hiện.

## 5. Khôi phục khả năng sử dụng key

Cách khôi phục phụ thuộc vào `KeyState` và nguyên nhân bị từ chối. Bước đầu tiên là xác định đúng key bằng key ID hoặc ARN và kiểm tra trạng thái:

~~~bash
aws kms describe-key \
  --key-id <KEY_ID_OR_ARN> \
  --query "KeyMetadata.{KeyId:KeyId,State:KeyState,Enabled:Enabled,Origin:Origin,Manager:KeyManager,MultiRegion:MultiRegion}"
~~~

### 5.1. Key đang Disabled

Nếu trạng thái là `Disabled`, xác minh rằng việc mở lại key phù hợp với xử lý sự cố và workload được phép sử dụng key. Sau đó chạy:

~~~bash
aws kms enable-key --key-id <KEY_ID_OR_ARN>
~~~

Kiểm tra lại bằng `DescribeKey`. Sau khi key trở lại `Enabled`, thử một thao tác mã hóa hoặc giải mã có kiểm soát bằng principal của ứng dụng. Nếu key có encryption context bắt buộc, bài kiểm thử phải dùng đúng context.

### 5.2. Key đang PendingDeletion

Có thể hủy lịch xóa khi key vẫn ở `PendingDeletion` và thời gian chờ chưa kết thúc:

~~~bash
aws kms cancel-key-deletion --key-id <KEY_ID_OR_ARN>
~~~

Sau khi hủy, trạng thái key chuyển thành `Disabled`. Vì vậy, cần enable thêm một bước:

~~~bash
aws kms enable-key --key-id <KEY_ID_OR_ARN>
~~~

Tiếp theo, kiểm tra trạng thái bằng `DescribeKey`, kiểm tra rotation bằng `GetKeyRotationStatus` và thử thao tác với ứng dụng. KMS khôi phục cấu hình rotation trước đó sau khi hủy deletion; nếu đã quá lịch rotation, KMS có thể thực hiện rotation ngay khi key được enable lại.

Nếu thời gian chờ đã kết thúc và KMS đã xóa key, `CancelKeyDeletion` không còn tác dụng. Với symmetric KMS key thông thường, ciphertext được mã hóa bằng key đã xóa không thể giải mã lại.

### 5.3. Key đang PendingImport hoặc Unavailable

Nếu key có `Origin=EXTERNAL` và trạng thái `PendingImport`, hãy kiểm tra thời hạn vật liệu, import token và quy trình nhập key material. Khi vật liệu đã hết hạn hoặc bị xóa, thao tác enable đơn thuần không khôi phục được khả năng mật mã; cần nhập lại vật liệu hợp lệ theo hướng dẫn của KMS.

Nếu key ở `Unavailable`, kiểm tra custom key store. Với AWS CloudHSM key store, xác minh cluster và kết nối. Với external key store, xác minh external key manager, proxy và kết nối. Khi kho khóa nền sẵn sàng, kiểm tra lại trạng thái và thực hiện thao tác thử.

### 5.4. Key Enabled nhưng ứng dụng vẫn bị AccessDenied

`Enabled` chỉ cho biết key có thể thực hiện thao tác mật mã; nó không có nghĩa mọi principal đều được phép sử dụng key. Nếu ứng dụng nhận `AccessDeniedException`, kiểm tra lần lượt:

- Key policy có cho phép principal hoặc tài khoản sử dụng key không.
- IAM policy của role hoặc user có cấp action cần thiết như `kms:Encrypt`, `kms:Decrypt`, `kms:GenerateDataKey` hoặc `kms:ReEncrypt` không.
- KMS grant có bị thu hồi, hết hiệu lực hoặc giới hạn sai không.
- SCP, permission boundary, session policy hoặc VPC endpoint policy có chặn action không.
- Điều kiện trong policy có yêu cầu encryption context, ViaService, Region hoặc principal ARN cụ thể không.
- Ứng dụng có đang tham chiếu đúng key ID, ARN hoặc alias trong đúng Region và tài khoản không.

Chỉ cấp đúng action và resource cần thiết cho workload. Không mở rộng key policy thành quyền rộng cho mọi principal để xử lý nhanh lỗi truy cập.

## 6. Quy trình vận hành và giám sát

Một quy trình vận hành tốt tách việc thay key material, tạm dừng sử dụng và xóa key thành các thay đổi có mục đích rõ ràng.

~~~mermaid
flowchart TD
    A["KMS key đang Enabled"] --> B{"Mục tiêu vận hành?"}
    B -->|"Xoay vòng định kỳ"| C["Automatic rotation"]
    B -->|"Xoay vòng ngay"| D["On-demand rotation"]
    B -->|"Tạm dừng sử dụng"| E["DisableKey"]
    B -->|"Ngừng sử dụng vĩnh viễn"| F["ScheduleKeyDeletion"]
    E --> G{"Cần dùng lại?"}
    G -->|"Có"| H["EnableKey"]
    G -->|"Không, tiếp tục đánh giá"| I["Giữ Disabled và theo dõi"]
    F --> J{"Còn trong thời gian chờ?"}
    J -->|"Có, cần giữ key"| K["CancelKeyDeletion"]
    K --> L["EnableKey"]
    J -->|"Không"| M["Key bị xóa vĩnh viễn"]
~~~

Nên xây dựng các kiểm soát sau:

- **Phân quyền:** tách vai trò quản trị key khỏi vai trò sử dụng key; giới hạn người có quyền `kms:ScheduleKeyDeletion` và `kms:DisableKey`.
- **Thời gian chờ:** dùng `kms:ScheduleKeyDeletionPendingWindowInDays` để áp đặt khoảng chờ tối thiểu theo chính sách tổ chức.
- **Audit:** lưu CloudTrail và rà soát các thao tác `DisableKey`, `EnableKey`, `ScheduleKeyDeletion`, `CancelKeyDeletion` và rotation.
- **Cảnh báo:** tạo CloudWatch alarm hoặc quy tắc EventBridge để phát hiện thay đổi vòng đời key và các lần sử dụng key đang chờ xóa.
- **Kiểm thử phục hồi:** định kỳ diễn tập hủy scheduled deletion, enable key và giải mã một mẫu dữ liệu bằng đúng workload role.
- **Quản lý phụ thuộc:** duy trì danh sách dịch vụ, ứng dụng, snapshot, backup và dữ liệu archive đang phụ thuộc từng key.

Với ứng dụng Java/Spring Boot, cấu hình key ARN hoặc alias nên được quản lý theo môi trường triển khai. Khi chuyển sang key mới, kiểm thử cả luồng mã hóa dữ liệu mới và giải mã dữ liệu cũ. Nếu ứng dụng dùng envelope encryption, lưu trữ encrypted data key cùng ciphertext và bảo đảm key dùng để giải mã encrypted data key vẫn còn khả dụng.

## 7. Chọn thao tác phù hợp

| Nhu cầu | Thao tác nên chọn | Điểm cần xác minh |
|---|---|---|
| Đáp ứng chính sách rotation định kỳ | Automatic rotation | Loại key, origin, chu kỳ và trạng thái rotation. |
| Cần đổi key material ngay | On-demand rotation | Key là symmetric; nếu dùng imported material, đã import vật liệu mới. |
| Key không hỗ trợ rotation tự động | Manual rotation | Cập nhật consumer và giữ key cũ để giải mã dữ liệu cũ. |
| Tạm dừng thao tác mật mã | Disable key | Đã xác định workload và cách enable lại. |
| Đang đánh giá có thể xóa key hay không | Disable và theo dõi | Không còn dịch vụ, backup hoặc ciphertext cần key. |
| Đã xác nhận không còn phụ thuộc và cần xóa | Schedule deletion | Đúng key, thời gian chờ, replicas và quyền phê duyệt. |
| Lên lịch xóa nhầm, vẫn trong thời gian chờ | Cancel deletion rồi enable | Kiểm tra trạng thái và quyền truy cập sau phục hồi. |
| Key Enabled nhưng ứng dụng bị từ chối | Sửa policy, IAM hoặc grant | Principal, action, Region, encryption context và điều kiện policy. |

## 8. Tình huống thực hành

Một ứng dụng Spring Boot lưu tài liệu trên Amazon S3 và dùng customer managed symmetric KMS key để bảo vệ dữ liệu. Nhóm vận hành nhận yêu cầu bật rotation hằng năm, sau đó phát hiện một key cũ có vẻ không còn được sử dụng và muốn xóa.

Cách xử lý:

1. Dùng `DescribeKey` xác nhận key là customer managed, symmetric encryption, `Origin=AWS_KMS` và đang `Enabled`.
2. Bật automatic rotation với chu kỳ 365 ngày, sau đó dùng `GetKeyRotationStatus` kiểm tra cấu hình.
3. Rà soát CloudTrail, cấu hình bucket, bản sao lưu, replication và ứng dụng để xác định các tài nguyên đang phụ thuộc key.
4. Nếu cần kiểm tra mức độ phụ thuộc, disable key trong một cửa sổ bảo trì có giám sát. Theo dõi lỗi truy cập S3 và KMS; nếu phát hiện workload hợp lệ bị ảnh hưởng, enable key ngay.
5. Chỉ khi đã xác nhận dữ liệu và backup không còn cần key, lên lịch xóa với thời gian chờ phù hợp, ví dụ 30 ngày.
6. Trong thời gian chờ, theo dõi CloudTrail và cảnh báo. Nếu phát hiện một backup hoặc workload còn cần key, chạy `CancelKeyDeletion`, sau đó `EnableKey` và kiểm thử giải mã.
7. Khi thời gian chờ kết thúc, key bị xóa vĩnh viễn. Dữ liệu symmetric ciphertext còn phụ thuộc key đó sẽ không thể giải mã.

Tình huống này cho thấy rotation, disable và scheduled deletion phục vụ ba mục tiêu khác nhau. Rotation thay vật liệu mật mã theo chính sách; disable tạm dừng khả năng sử dụng; scheduled deletion kết thúc vòng đời key sau thời gian chờ bắt buộc.

## Tài liệu tham khảo

- [Rotate AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/rotate-keys.html)
- [Enable automatic key rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotating-keys-enable.html)
- [Perform on-demand key rotation](https://docs.aws.amazon.com/kms/latest/developerguide/rotating-keys-on-demand.html)
- [Enable and disable keys](https://docs.aws.amazon.com/kms/latest/developerguide/enabling-keys.html)
- [Key states of AWS KMS keys](https://docs.aws.amazon.com/kms/latest/developerguide/key-state.html)
- [Schedule key deletion](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys-scheduling-key-deletion.html)
- [Cancel key deletion](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys-cancelling-key-deletion.html)
- [Delete an AWS KMS key](https://docs.aws.amazon.com/kms/latest/developerguide/deleting-keys.html)

