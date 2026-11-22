# Object versioning và phục hồi dữ liệu bị ghi đè

Trong chương **Object Storage và Archive Storage** của module **CLOUD_PROVIDERS_ORACLE**, bài học này tập trung vào một câu hỏi vận hành: khi ứng dụng ghi đè một object bằng dữ liệu sai, làm thế nào lấy lại nội dung đúng mà vẫn giữ được dấu vết sự cố?

Bối cảnh là một ứng dụng trên OCI Compute, chạy trong VCN, đọc tệp cấu hình hoặc dữ liệu xuất từ cơ sở dữ liệu Oracle trong một bucket riêng tư. Nhóm vận hành cần phối hợp tenancy, compartment, IAM và Object Storage để khôi phục dữ liệu, theo dõi thao tác và kiểm soát chi phí. Versioning là một lớp bảo vệ trong kiến trúc đó; tính sẵn sàng của ứng dụng còn phụ thuộc vào thời gian phát hiện lỗi và khả năng chuyển sang dữ liệu đã khôi phục.

## Mục tiêu học tập

Sau bài học, người học có thể:

- Giải thích object name, version ID, phiên bản hiện hành và delete marker.
- Phân biệt ba trạng thái versioning của bucket và nhận biết lúc dữ liệu không còn được bảo vệ.
- Phục hồi nội dung bị ghi đè bằng cách đọc một phiên bản cụ thể rồi tạo phiên bản hiện hành mới.
- Phân biệt phục hồi bản ghi đè, khôi phục object bị xóa và restore từ Archive Storage.
- Thiết kế quyền thao tác, cửa sổ lưu lịch sử và bằng chứng xác minh cho một quy trình khôi phục.

## Mô hình dữ liệu: một tên object, nhiều phiên bản

Giả sử ứng dụng luôn đọc object `config/payment.json`. Tên này là khóa tra cứu ổn định; các lần cập nhật có thể mang nội dung khác nhau.

Khi bucket bật versioning, một lần ghi mới làm phiên bản vừa ghi trở thành **latest version**; nội dung trước đó vẫn có thể tồn tại dưới dạng **previous version**. **Version ID** định danh một phiên bản cụ thể. Truy cập bằng tên thông thường lấy nội dung hiện hành; muốn đọc lịch sử phải chỉ rõ phiên bản. Xem [khái niệm Object Storage versioning của Oracle](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

Ví dụ dưới đây dùng các nhãn V1, V2, V3 để minh họa, không phải version ID thực:

| Thời điểm | Hành động với cùng tên object | Nội dung hiện hành | Nội dung lịch sử |
| --- | --- | --- | --- |
| 09:00 | Upload cấu hình đúng | V1 | Chưa có |
| 09:10 | Pipeline upload cấu hình sai | V2 | V1 |
| 09:20 | Đọc V1 và upload lại | V3, có nội dung như V1 | V1 và V2 |

V3 có định danh mới. Khôi phục bằng upload lại không làm thời gian quay ngược, cũng không xóa V2. Cách này giữ được bản lỗi để điều tra và biểu diễn rõ hành động sửa chữa.

~~~mermaid
sequenceDiagram
    participant P as Pipeline
    participant B as Bucket bật versioning
    participant O as Người vận hành
    P->>B: Ghi cấu hình đúng
    Note over B: V1 hiện hành
    P->>B: Ghi đè bằng cấu hình lỗi
    Note over B: V2 hiện hành, V1 còn trong lịch sử
    O->>B: Đọc đúng version ID của V1
    B-->>O: Nội dung V1
    O->>O: Kiểm tra checksum và nội dung nghiệp vụ
    O->>B: Upload nội dung đã kiểm tra
    Note over B: V3 hiện hành, giữ V1 và V2
~~~

Đừng dùng version ID như số thứ tự để so sánh trước sau. Trong quy trình vận hành, hãy đối chiếu thời gian, nội dung, nguồn cập nhật và định danh đã ghi trong nhật ký triển khai. Một bản cũ hơn chưa chắc là bản đúng.

## Trạng thái versioning của bucket

Versioning được cấu hình ở cấp bucket. Các trạng thái cần phân biệt:

| Trạng thái | Ý nghĩa vận hành |
| --- | --- |
| `Disabled` | Bucket chưa từng bật versioning; ghi đè không giữ lịch sử để phục hồi bằng tính năng này |
| `Enabled` | Tạo và giữ các phiên bản khi cập nhật; có thể đọc lại phiên bản còn tồn tại |
| `Suspended` | Ngừng tạo lịch sử mới cho các lần ghi đè hoặc xóa sau đó; các phiên bản đã giữ trước đây vẫn còn nếu chưa bị xóa |

Sau khi đã bật, không chuyển bucket về `Disabled`; có thể chuyển sang `Suspended` rồi bật lại. CLI cập nhật bucket chấp nhận `Enabled` và `Suspended`. Xem [tham số versioning của UpdateBucket](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/bucket/update.html).

Bật versioning sau sự cố không tái tạo được nội dung đã mất trước đó. Tương tự, việc thấy bucket đang Enabled hôm nay chưa chứng minh nó đã bảo vệ lần ghi đè xảy ra hôm qua. Khi điều tra, cần biết trạng thái tại thời điểm thay đổi và xác nhận phiên bản cần phục hồi thực sự còn tồn tại.

Trong thiết kế hạ tầng tự động hóa, nên khai báo rõ trạng thái versioning mong muốn, phát hiện thay đổi sang Suspended và giới hạn người được sửa bucket. Bật versioning trên Console nhưng để một lần triển khai hạ tầng sau đó chuyển sang Suspended sẽ làm đứt cửa sổ bảo vệ dự kiến.

## Ba thao tác dễ nhầm lẫn khi xóa và phục hồi

### Xóa object bằng tên

Trong bucket Enabled, xóa object mà không chỉ version ID tạo một **delete marker**. Marker đánh dấu trạng thái đã xóa; dữ liệu của các phiên bản trước có thể vẫn còn. Truy cập thông thường bằng tên sẽ không trả về bản dữ liệu cũ chỉ vì bản đó tồn tại trong lịch sử.

Nếu gỡ marker đang che phiên bản dữ liệu phù hợp, phiên bản bên dưới có thể hiện lại. Trên Console, cần hiển thị object đã xóa và xem danh sách phiên bản. Xem [khôi phục object bị xóa](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning_topic-To_recover_a_deleted_object.htm).

### Xóa một phiên bản cụ thể

Xóa với version ID là thao tác xóa vĩnh viễn đối với phiên bản được chọn, kể cả khi nó đang là phiên bản mới nhất. Không có cơ chế versioning tự tạo thêm bản sao để cứu chính phiên bản vừa bị xóa vĩnh viễn. Xem [xóa phiên bản Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning_topic-To_delete_an_object.htm).

Do đó, khi V2 bị lỗi và V1 còn tốt, ưu tiên đọc V1 rồi ghi lại thành phiên bản mới. Xóa V2 để làm lộ bản bên dưới làm mất một phần bằng chứng và đặt thao tác phục hồi vào quyền xóa không thể hoàn tác.

### Restore dữ liệu trong Archive Storage

Restore từ Archive làm một object đã lưu trữ lạnh có thể được đọc trong khoảng thời gian phục hồi. Nó giải quyết khả năng truy cập dữ liệu lạnh, không tự chọn lại bản nghiệp vụ đúng sau khi ghi đè. Cần chờ quá trình restore hoàn tất trước khi tải dữ liệu. Xem [restore object từ Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/managingobjects_topic-To_restore_objects_from_Archive_Storage.htm).

Nếu phiên bản tốt đã chuyển sang Archive, quy trình có thêm bước restore **đúng phiên bản đó**, rồi mới tải, xác minh và đưa nội dung thành bản hiện hành. CLI restore có tham số version ID; không được bỏ qua định danh khi cần một bản lịch sử cụ thể. Xem [OCI CLI object restore](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/restore.html).

## Quyền IAM và phạm vi khôi phục

Một bucket nằm trong compartment nhưng quyền khôi phục không tự xuất hiện từ việc người dùng biết tên bucket. Thiết kế quyền nên tách các nhiệm vụ:

| Vai trò | Nhu cầu | Giới hạn nên đặt |
| --- | --- | --- |
| Ứng dụng ghi dữ liệu | Tạo hoặc ghi đè object theo nghiệp vụ | Chỉ bucket hoặc prefix cần dùng; không mặc định cấp quyền xóa lịch sử |
| Người kiểm tra sự cố | Liệt kê và đọc phiên bản | Đọc dữ liệu, không sửa cấu hình bucket |
| Người phục hồi | Đọc bản tốt và ghi bản thay thế | Phạm vi bucket được giao, có ghi nhận thao tác |
| Người dọn lịch sử | Xóa phiên bản theo chính sách | Tách khỏi tài khoản ứng dụng thông thường |
| Người quản lý bucket | Cấu hình versioning và lifecycle | Kiểm soát thay đổi cấu hình bảo vệ dữ liệu |

Trong bộ quyền OCI, thay đổi bucket liên quan `BUCKET_UPDATE`; xóa object và xóa phiên bản là các quyền khác nhau, gồm `OBJECT_DELETE` và `OBJECT_VERSION_DELETE`. `manage objects` bao gồm quyền xóa phiên bản, nên cấp rộng quyền này cho ứng dụng có thể làm suy yếu lớp bảo vệ lịch sử. Xem [tham chiếu IAM cho Object Storage và Archive Storage](https://docs.oracle.com/en-us/iaas/Content/Identity/Reference/objectstoragepolicyreference.htm).

Khi viết policy thực tế, quản trị viên cần đối chiếu API được dùng, phạm vi compartment và điều kiện bucket/object. Không nên suy ra rằng một danh sách vai trò trong thiết kế đã đủ thay thế policy đã triển khai. Bài thực hành bên dưới giả định tài khoản đã có quyền đọc namespace, đọc/cập nhật bucket, liệt kê/đọc và tạo/ghi đè object trong bucket lab.

Nếu ứng dụng chạy trong private subnet của VCN, cũng phải xác nhận đường mạng đến endpoint Object Storage phù hợp với kiến trúc, chẳng hạn đường qua Service Gateway. Lỗi truy cập do mạng, sai region hoặc thiếu quyền không phải bằng chứng rằng phiên bản đã mất.

## Quy trình xử lý ghi đè trong vận hành

Một quy trình khôi phục có thể dùng sáu bước sau:

1. **Khoanh vùng thay đổi.** Tạm dừng pipeline hoặc luồng ghi gây lỗi; ghi lại region, namespace, bucket, tên object và thời điểm phát hiện.
2. **Lưu trạng thái ban đầu.** Ghi nhận version ID và ETag hiện hành, danh sách phiên bản liên quan, thời gian và nguồn thay đổi. Nếu dữ liệu cho phép, lưu bản lỗi vào nơi điều tra có kiểm soát.
3. **Chọn ứng viên.** Đọc phiên bản dự kiến tốt bằng version ID. Đối chiếu mã phát hành, checksum đã biết hoặc kiểm tra nghiệp vụ.
4. **Khôi phục có kiểm soát.** Tạo một bản hiện hành mới từ nội dung đã kiểm tra. Sử dụng điều kiện ETag hoặc cửa sổ ngừng ghi để tránh đè lên thay đổi khác.
5. **Đọc lại theo cách ứng dụng đọc.** Tải object không chỉ định version ID, xác minh nội dung và chạy kiểm tra nghiệp vụ liên quan.
6. **Khôi phục luồng ghi và theo dõi.** Xác nhận ứng dụng đã nạp bản mới, cập nhật hồ sơ sự cố và xử lý nguyên nhân gốc.

Version ID và ETag phục vụ hai mục tiêu khác nhau. Version ID chọn dữ liệu nguồn cụ thể; ETag dùng trong điều kiện để phát hiện tài nguyên đã thay đổi so với lúc kiểm tra. Không coi ETag là checksum nghiệp vụ hay mặc định là MD5 của nội dung.

Nếu điều kiện ETag không còn khớp, dừng và đánh giá thay đổi vừa xảy ra. Việc lấy ETag mới rồi tự động thử ghi lại ngay có thể đè lên bản sửa hợp lệ của người khác.

## Thực hành: khôi phục tệp cấu hình bị ghi đè

Các lệnh sau dành cho **Bash**, chẳng hạn OCI Cloud Shell. Đây là bài thực hành trên bucket lab riêng tư đã tạo sẵn, ban đầu trống và không có người ghi đồng thời. Không dùng bucket dữ liệu thật.

Chuẩn bị OCI CLI đã xác thực và một bucket Standard tên `versioning-lab` trong region của bạn. Bucket không có retention rule đang hoạt động hoặc cấu hình khác ngăn bật versioning. Thay region và bucket dưới đây cho đúng môi trường. Tên object và nội dung trong ví dụ không chứa bí mật.

### Chuẩn bị và bật versioning

~~~bash
set -euo pipefail

REGION="ap-singapore-1"
BUCKET="versioning-lab"
KEY="lab/config.json"
LAB_DIR="$(mktemp -d)"

NS="$(oci os ns get --region "$REGION" --query data --raw-output)"
test -n "$NS"

oci os bucket get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET"

oci os bucket update \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --versioning Enabled

oci os bucket get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" \
  --query 'data.versioning' --raw-output
~~~

Kết quả cuối phải là `Enabled`. Nếu bật thất bại, xử lý nguyên nhân trước khi upload dữ liệu cần bảo vệ. Không tiếp tục chỉ vì đã gửi lệnh cập nhật.

### Tạo phiên bản tốt và ghi nhận định danh

~~~bash
printf '%s\n' '{"release":1,"paymentEnabled":true}' > "$LAB_DIR/good.json"
printf '%s\n' '{"release":2,"paymentEnabled":false}' > "$LAB_DIR/bad.json"

oci os object put \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/good.json" \
  --content-type application/json --no-multipart

oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all

V1="$(oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all \
  --query 'data.items[0]."version-id"' --raw-output)"

test -n "$V1"
test "$V1" != "null"
printf 'Version da ghi nhan: %s\n' "$V1"
~~~

Ở thời điểm này bucket lab chỉ có một object và một phiên bản, nên lấy phần tử đầu tiên là đủ cho ví dụ. Trong bucket thật, `--prefix` là lọc theo tiền tố, có thể trả về nhiều tên; phải khớp chính xác tên, loại trừ delete marker và chọn bản dựa trên bằng chứng, không sao chép cách chọn vị trí này.

Lệnh liệt kê trả về các mục trong `data.items`, gồm tên, version ID và chỉ báo delete marker. Tham khảo [liệt kê phiên bản trên OCI](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning_topic-To_list_object_versions.htm). Tùy chọn `--all` lấy đủ các trang kết quả; thiếu phân trang có thể khiến bạn kết luận sai rằng không có bản cần tìm. Xem [OCI CLI list-object-versions](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/list-object-versions.html).

### Mô phỏng lần ghi đè sai

~~~bash
oci os object put \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/bad.json" \
  --content-type application/json --no-multipart --force

oci os object get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/current-bad.json"

cat "$LAB_DIR/current-bad.json"

oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all
~~~

Lần đọc không chỉ version ID phải cho thấy release 2 với `paymentEnabled:false`. Danh sách phiên bản phải còn cả bản đầu. Đây là kết quả dự kiến để người học kiểm tra, không phải kết quả của một lần chạy đã thực hiện sẵn.

### Đọc đúng bản lịch sử và kiểm tra

~~~bash
oci os object get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --version-id "$V1" \
  --file "$LAB_DIR/recovered.json"

cmp "$LAB_DIR/good.json" "$LAB_DIR/recovered.json"
cat "$LAB_DIR/recovered.json"
~~~

`cmp` phải trả về mã thành công và không in khác biệt. Trong bài lab, tệp nguồn tốt đóng vai trò mốc đối chiếu. Trong sự cố thật, dùng checksum từ bản phát hành tin cậy hoặc kiểm tra nghiệp vụ phù hợp; chỉ tải thành công chưa chứng minh dữ liệu đúng.

Tham số `--version-id` của [OCI CLI object get](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/get.html) giúp đọc đúng phiên bản ngay cả khi tên object hiện đang trỏ đến nội dung khác.

### Ghi lại nội dung tốt với điều kiện ETag

Sau khi xác minh bản tốt, lấy ETag của object hiện hành:

~~~bash
CURRENT_ETAG="$(oci os object head \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --query etag --raw-output)"

test -n "$CURRENT_ETAG"
test "$CURRENT_ETAG" != "null"

oci os object put \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/recovered.json" \
  --content-type application/json \
  --if-match "$CURRENT_ETAG" --no-multipart --force
~~~

`head` lấy metadata và ETag mà không tải toàn bộ nội dung. Xem [OCI CLI object head](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/head.html). Điều kiện `--if-match` chỉ cho phép ghi khi ETag còn khớp; `--force` bỏ bước hỏi ghi đè của CLI, không thay thế điều kiện đồng thời. Ví dụ dùng object nhỏ và upload một phần. Xem [OCI CLI object put](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/put.html).

Trên hệ thống thật, cần ghi nhận ETag trong cùng giai đoạn kiểm tra trạng thái hiện hành và tiếp tục đối chiếu trước lúc ghi. Trong lab không có writer khác; khi vận hành có nhiều writer, ưu tiên tạm dừng hoặc điều phối chúng trong cửa sổ khôi phục.

Upload lại từ file không tự mang theo toàn bộ metadata của phiên bản nguồn. Lab đặt rõ Content-Type; dữ liệu thật có thể cần giữ thêm metadata nghiệp vụ, Content-Encoding hoặc Cache-Control. Hãy ghi nhận và truyền lại các thuộc tính cần thiết thay vì chỉ kiểm tra byte nội dung.

### Đọc lại bản hiện hành và xác nhận lịch sử

~~~bash
oci os object get \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY" \
  --file "$LAB_DIR/current-restored.json"

cmp "$LAB_DIR/good.json" "$LAB_DIR/current-restored.json"

oci os object head \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --name "$KEY"

oci os object list-object-versions \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --prefix "$KEY" --all
~~~

Bài lab đạt yêu cầu khi bản đọc thông thường có nội dung release 1, có một phiên bản hiện hành mới, và các phiên bản trước vẫn được giữ. Với đúng ba lần upload thành công, không có retry tạo thêm lần ghi và không có thao tác khác, dự kiến có ba phiên bản dữ liệu.

Ứng dụng có thể giữ cấu hình trong bộ nhớ hoặc cache ở một lớp khác. Sau khi Object Storage đã đúng, phải xác minh ứng dụng đã tải lại dữ liệu; chỉ nhìn Console chưa đủ để kết luận luồng thanh toán đã phục hồi.

Các file local nằm trong thư mục tạm được in bằng `printf '%s\n' "$LAB_DIR"`. Sau bài lab, thực hiện dọn dẹp theo quy định môi trường. Xóa object bằng tên trong bucket Enabled không đồng nghĩa đã xóa mọi phiên bản và giải phóng toàn bộ dung lượng.

## Phương án sao chép phía dịch vụ

Với object lớn, có thể chọn CopyObject thay vì tải xuống máy rồi upload lại. Chỉ rõ `--source-version-id` để tránh vô tình sao chép bản lỗi đang hiện hành. Có thể sao chép sang một tên kiểm tra hoặc bucket phục hồi đã tồn tại trước khi thay thế tên đang được ứng dụng sử dụng.

Ví dụ sau là phương án thay thế sau khi đã có `V1` trong bài lab; nó tạo một tên mới để kiểm tra:

~~~bash
RECOVERY_KEY="recovery/config-v1.json"

oci os object copy \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" \
  --source-object-name "$KEY" --source-version-id "$V1" \
  --destination-namespace "$NS" \
  --destination-region "$REGION" \
  --destination-bucket "$BUCKET" \
  --destination-object-name "$RECOVERY_KEY" \
  --destination-object-if-none-match-e-tag '*' \
  --wait-for-state COMPLETED
~~~

Lệnh copy là bất đồng bộ; phải kiểm tra work request hoàn tất và đọc lại kết quả. Nếu tên kiểm tra đã tồn tại, điều kiện trong ví dụ chặn ghi đè. Khi thay thế một object đang tồn tại, có thể dùng điều kiện ETag của đích. Các tham số này được mô tả trong [OCI CLI object copy](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/copy.html).

Copy cần cả quyền của bên gọi và quyền để dịch vụ Object Storage thực hiện thao tác thay mặt người dùng. Cấp quyền dịch vụ theo region và phạm vi cần thiết; không giải quyết lỗi copy bằng cách mặc định cấp toàn tenancy. Copy từ Archive còn yêu cầu restore trước. Xem [điều kiện và quyền cho CopyObject](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/copyingobjects.htm).

Đây là sao chép một phiên bản được chọn, không phải chuyển nguyên bộ lịch sử sang đích. Nếu mục tiêu là một bản sao độc lập phục vụ phục hồi, phải thiết kế rõ các phiên bản nào được chuyển và cách kiểm tra chúng.

## Nếu object bị xóa: xử lý delete marker

Tình huống này khác với lần ghi đè sai trong lab chính. Trước tiên, liệt kê phiên bản của đúng tên object, tìm mục có `is-delete-marker: true` và xác nhận đó là marker cần gỡ. Với một marker mới nhất và một phiên bản dữ liệu tốt ngay bên dưới, gỡ marker có thể làm dữ liệu hiện lại.

Ví dụ dưới đây chỉ minh họa cú pháp; phải thay ID sau khi đã kiểm tra, không dùng ID của phiên bản dữ liệu:

~~~bash
DELETE_MARKER_ID="REPLACE_WITH_CONFIRMED_DELETE_MARKER_ID"

oci os object delete \
  --region "$REGION" --namespace-name "$NS" \
  --bucket-name "$BUCKET" --object-name "$KEY" \
  --version-id "$DELETE_MARKER_ID"
~~~

CLI giữ bước hỏi xác nhận. Chỉ xác nhận sau khi đối chiếu đúng tên và marker. Cùng lệnh này với ID của một phiên bản dữ liệu sẽ xóa vĩnh viễn phiên bản đó. Xem [cú pháp OCI CLI object delete](https://docs.oracle.com/en-us/iaas/tools/oci-cli/latest/oci_cli_docs/cmdref/os/object/delete.html).

Nếu có nhiều marker hoặc nhiều lần ghi xen kẽ, không xóa hàng loạt marker theo một bộ lọc thiếu ngữ cảnh. Chọn phiên bản dữ liệu tốt rồi tạo một bản hiện hành mới thường giúp kiểm soát kết quả rõ hơn. Sau mọi cách khôi phục, vẫn phải đọc lại bằng tên thông thường để xác minh điều ứng dụng sẽ thấy.

## Cửa sổ phục hồi, lifecycle và chi phí

Versioning giữ nhiều bản dữ liệu nên dung lượng tính phí có thể lớn hơn nhiều so với kích thước bản hiện hành. Ước lượng kỹ thuật ban đầu cần tính tổng kích thước các phiên bản còn lưu, thay vì chỉ đếm tên object. Đây là mô hình ước lượng dung lượng, không phải báo giá OCI.

Ví dụ tự đặt: một object 100 MiB được thay toàn bộ nội dung 12 lần mỗi ngày. Giữ các bản cũ trong khoảng 30 ngày có thể tạo khoảng 360 bản cũ, tương đương khoảng 35,2 GiB, cộng bản hiện hành. Con số chỉ minh họa một object có kích thước không đổi, chưa có lifecycle và không có lần ghi khác; chi phí thực tế còn phụ thuộc tier, thời gian lưu, request, truy xuất và truyền dữ liệu.

Có thể đặt chính sách vận hành cho từng nhóm dữ liệu:

| Nhóm dữ liệu | Câu hỏi cần trả lời trước khi đặt lifecycle |
| --- | --- |
| Cấu hình triển khai | Sau bao lâu nhóm vận hành thường phát hiện một bản cấu hình sai? |
| Tệp xuất báo cáo | Có cần so sánh nhiều kỳ và xác minh lại kết quả đã công bố không? |
| Dữ liệu tạm | Có thật sự cần lịch sử lâu hơn vòng đời công việc không? |
| Dữ liệu phục hồi từ cơ sở dữ liệu | Những tệp nào phải thuộc cùng một bộ phục hồi nhất quán? |

Lifecycle hỗ trợ xử lý previous versions. Mốc tuổi của một bản cũ có thể tính từ lúc bản đó chuyển từ latest sang previous; cần đọc đúng tiêu chí của rule. Xóa previous version là xóa vĩnh viễn, nên cửa sổ giữ phải bao phủ thời gian phát hiện lỗi và thời gian xử lý. Lifecycle chạy theo cơ chế nền, không nên coi là thao tác xóa đúng một giây đã định. Xem [Object Lifecycle Management](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usinglifecyclepolicies.htm).

Nếu chuyển bản cũ sang Archive để giảm dung lượng ở tier nóng, phải đánh đổi với thời gian và chi phí lấy lại. Một cấu hình khôi phục cần vài phút không nên phụ thuộc duy nhất vào phiên bản tốt đang ở trạng thái phải chờ restore.

## Giới hạn cần đưa vào thiết kế

Versioning giúp quay lại nội dung của từng object còn giữ lịch sử. Nó không tự xác minh tính đúng của dữ liệu và không tạo giao dịch khôi phục nhiều object.

Ví dụ, một bộ xuất dữ liệu Oracle gồm `manifest.json`, `customers.csv` và `orders.csv`. Nếu đưa riêng `orders.csv` về bản cũ trong khi hai tệp còn lại thuộc một lần xuất khác, bộ dữ liệu có thể không nhất quán. Thiết kế đề xuất là tạo một mã lần xuất, ghi manifest gồm tên và version ID hoặc checksum của từng tệp, rồi kiểm tra cả bộ trước khi đưa vào sử dụng.

Cũng không dùng versioning như phương án duy nhất chống tài khoản quản trị bị chiếm. Người có quyền xóa phiên bản hoặc cấu hình lifecycle rộng vẫn có thể phá hủy lịch sử. Cần phối hợp tách quyền, quản lý khóa mã hóa khi áp dụng và bản sao phục hồi theo yêu cầu hệ thống.

Nếu dùng retention rule hoặc replication, phải kiểm tra tương thích trước khi kết hợp: OCI có ràng buộc giữa retention rule đang hoạt động với versioning; replication không chuyển toàn bộ các previous versions và bucket đích replication có giới hạn riêng. Xem [tương tác giữa versioning và các tính năng Object Storage](https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingversioning.htm).

## Theo dõi và bằng chứng hoàn tất

Nhật ký triển khai và hồ sơ sự cố nên liên kết được object với nguồn thay đổi. Một bản ghi phục hồi tối thiểu có thể gồm:

~~~text
Incident: INC-EXAMPLE-017
Region / namespace / bucket: giá trị đã xác nhận
Object name: config/payment.json
Thời điểm phát hiện: ghi kèm múi giờ
Version trước phục hồi: định danh của bản lỗi
Version nguồn: định danh của bản đã kiểm tra
ETag trước thao tác: giá trị dùng làm điều kiện
Version sau phục hồi: định danh mới
Xác minh: checksum hoặc kiểm tra nội dung + kiểm tra ứng dụng
Người thực hiện / nguồn tự động hóa: định danh truy vết
~~~

Đây là mẫu ghi nhận đề xuất, không phải dữ liệu sự cố thật. Khi dùng Audit hoặc log liên quan, đối chiếu thời gian, danh tính và request ID của thao tác có bằng chứng; không suy ra nội dung đầy đủ của object chỉ từ tên API trong log.

Theo dõi định kỳ trạng thái versioning của bucket quan trọng, tăng trưởng số phiên bản, dung lượng lưu lịch sử, lỗi truy cập và kết quả diễn tập phục hồi. Với workload trên Compute, kết thúc sự cố chỉ khi cả bản đọc Object Storage và hành vi ứng dụng đều đã được xác nhận.

## Xử lý các tình huống thường gặp

| Hiện tượng | Điều cần kiểm tra | Hướng xử lý |
| --- | --- | --- |
| Không thấy bản tốt | Đúng region, namespace, bucket, tên, phân trang; trạng thái tại thời điểm ghi | Liệt kê phiên bản đầy đủ và kiểm tra bằng chứng triển khai |
| Đọc bằng tên báo không tìm thấy | Có delete marker hiện hành hay không | Đọc phiên bản dữ liệu cụ thể hoặc xử lý marker đã xác nhận |
| Đọc bản cụ thể bị từ chối | IAM, đường mạng, khóa mã hóa nếu có | Sửa quyền hoặc điều kiện truy cập trong phạm vi được giao |
| Ghi phục hồi lỗi điều kiện ETag | Có writer thay đổi object trong lúc xử lý hay không | Dừng, ghi nhận thay đổi mới và điều phối lại |
| Tải bản cũ chưa được | Bản đó có đang ở Archive hoặc đang restore hay không | Restore đúng phiên bản, chờ hoàn tất rồi đọc lại |
| Copy chưa có kết quả | Work request và quyền dịch vụ Object Storage | Kiểm tra trạng thái, lỗi và đọc lại object đích |
| Bản hiện hành đúng nhưng ứng dụng vẫn lỗi | Cache, cấu hình đã nạp, tệp liên quan | Kiểm tra đường đọc thực tế và tính nhất quán của cả bộ |
| Dung lượng không giảm sau xóa | Các previous versions và marker còn lưu | Kiểm tra lịch sử và chính sách dọn đúng phiên bản |

Nếu phiên bản đã bị xóa vĩnh viễn hoặc nội dung đã bị ghi đè khi không được bảo vệ, không hứa khôi phục bằng versioning. Khi đó phải tìm bản sao độc lập hoặc tái tạo dữ liệu từ nguồn đáng tin cậy.

Một quy trình tốt kết hợp ba bằng chứng: phiên bản nguồn đã được chọn đúng, bản hiện hành đã được đọc lại đúng và ứng dụng đã hoạt động với dữ liệu khôi phục.