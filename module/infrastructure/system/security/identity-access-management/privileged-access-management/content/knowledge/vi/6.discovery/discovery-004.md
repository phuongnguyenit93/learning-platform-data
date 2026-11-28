# Phát hiện local admin

Trong chương **Discovery** của quản lý truy cập đặc quyền (PAM), phát hiện local admin là quá trình xác định những danh tính đang có quyền quản trị trên từng máy, chúng nhận quyền qua đường nào và kết quả đó được xác minh ở thời điểm nào. Danh tính có thể là tài khoản cục bộ, tài khoản miền, tài khoản dịch vụ hoặc thành viên của nhóm được cấp quyền trên máy.

Mục tiêu không dừng ở việc tìm tài khoản có tên `Administrator`. Kết quả discovery cần hỗ trợ kiểm kê quyền, xác định chủ sở hữu, giảm đặc quyền thường trực, triển khai JIT/JEA, quản lý credential trong vault, luân chuyển an toàn và lưu bằng chứng phục vụ kiểm toán hoặc ứng phó sự cố.

Bài học lấy máy trạm và máy chủ Windows thành viên làm ví dụ chính. Các hệ thống khác được đối chiếu để tránh áp dụng máy móc một cách thu thập cho mọi nền tảng. Những đoạn lệnh dưới đây chỉ minh họa truy vấn đọc trên máy được phép kiểm kê; bài học không yêu cầu quét hoặc thay đổi hệ thống thật.

## 1. Kết quả cần đạt

Sau bài học, người học có thể:

- Phân biệt tài khoản cục bộ với quyền quản trị cục bộ.
- Thu thập thành viên trực tiếp của nhóm quản trị và truy vết quyền qua nhóm được lồng vào.
- Dùng định danh ổn định để tránh gộp nhầm tài khoản cùng tên trên nhiều máy.
- Phân biệt kết quả đầy đủ, một phần, lỗi và dữ liệu đã cũ.
- Đánh giá các phát hiện để chuyển sang bước quản trị PAM mà không tự động xóa quyền hoặc đổi mật khẩu.
- Chuẩn bị bằng chứng về phạm vi thu thập, đường cấp quyền, khoảng trống và thay đổi theo thời gian.

## 2. Local account và local admin là hai khái niệm khác nhau

**Tài khoản cục bộ** được quản lý trong phạm vi một máy. **Local admin** mô tả quyền quản trị ở máy đó. Vì vậy, một tài khoản miền có thể là local admin, còn một tài khoản cục bộ có thể chỉ là người dùng thông thường.

Trên Windows thành viên, một điểm kiểm kê quan trọng là nhóm tích hợp **Administrators**, có SID `S-1-5-32-544`. Tên hiển thị của nhóm có thể thay đổi theo ngôn ngữ. Truy vấn bằng SID giúp tránh phụ thuộc vào tên `Administrators` trên giao diện.

| Đối tượng quan sát | Có thể kết luận gì? | Chưa thể kết luận gì? |
|---|---|---|
| Tài khoản cục bộ tồn tại | Máy có danh tính đó | Danh tính có quyền quản trị |
| Tài khoản nằm trực tiếp trong Administrators | Có đường cấp quyền quản trị qua nhóm | Tài khoản đang đăng nhập hoặc đã sử dụng quyền |
| Nhóm miền nằm trong Administrators | Nhóm miền là một nguồn cấp quyền trên máy | Chỉ những người được liệt kê trực tiếp trong nhóm mới có quyền |
| Tài khoản bị vô hiệu hóa nhưng vẫn là thành viên nhóm | Cấu hình quyền còn tồn tại | Tài khoản đang đăng nhập được hoặc hoàn toàn không còn rủi ro |
| Credential đã có trong vault | Có một đối tượng credential được quản lý | Mọi quyền của danh tính đã tối thiểu hoặc mọi phiên đều đi qua PAM |

Tư cách thành viên nhóm là bằng chứng về một đường cấp quyền. Khả năng truy cập và sử dụng quyền thực tế còn phụ thuộc vào trạng thái tài khoản, quyền đăng nhập, loại phiên, token, chính sách máy và các điều kiện xác thực. Không cần thử đăng nhập đặc quyền để chứng minh mọi phát hiện trong một tác vụ discovery thông thường.

UAC có thể ảnh hưởng đến token và thao tác cần nâng quyền. Không nên vì một phiên hiện tại chưa được nâng quyền mà kết luận danh tính không có tư cách quản trị.

### Giới hạn của việc chỉ xem nhóm Administrators

Nhóm này là một nguồn bằng chứng quan trọng nhưng không mô tả mọi khả năng đặc quyền trên máy. Danh tính hệ thống, quyền được ủy nhiệm riêng, dịch vụ chạy đặc quyền hoặc quyền sửa thành phần mà tiến trình đặc quyền sẽ thực thi có thể tạo rủi ro khác.

Do đó, cần ghi rõ báo cáo đang phản ánh **thành viên và đường quyền qua nhóm Administrators**, hay đã bao gồm đánh giá rộng hơn về đặc quyền hiệu lực. Không đặt tên báo cáo là “mọi đường quản trị đã được phát hiện” khi mới thu một danh sách nhóm.

## 3. Bắt đầu từ phạm vi máy cần kiểm kê

Danh sách máy là mẫu số của discovery. Nếu chỉ báo cáo những máy kết nối thành công, báo cáo có thể bỏ qua đúng những máy ít được quản lý nhất.

Với mỗi máy trong phạm vi, nên có:

- Định danh tài sản từ nguồn quản lý đáng tin cậy, tên hiển thị và miền quản lý.
- Vai trò máy: máy trạm, máy chủ thành viên hoặc loại hệ thống đặc biệt.
- Môi trường, mức nhạy cảm, chủ sở hữu kỹ thuật và nghiệp vụ nếu có.
- Phương thức thu thập được phép, thời gian quan sát và yêu cầu độ mới.
- Trạng thái thu thập, khả năng truy vấn nguồn danh tính liên quan và lỗi cần xử lý.

Tên máy và địa chỉ IP có thể đổi hoặc được tái sử dụng. Cần liên kết kết quả với đúng vòng đời tài sản, không chỉ nối bản ghi bằng chuỗi hostname.

**Domain controller cần luồng riêng.** Không xử lý domain controller như một máy chủ thành viên có kho tài khoản cục bộ thông thường. Các nhóm quản trị trên đó liên quan đến phạm vi miền và có mức tác động khác. Công cụ thu thập phải nhận diện vai trò máy trước khi áp dụng cách diễn giải kết quả.

Máy không tham gia miền, máy ngoài văn phòng, máy tắt hoặc máy nằm trong mạng cô lập vẫn thuộc phạm vi nếu chúng có trong danh mục được giao. Chúng cần trạng thái chưa xác minh hoặc dữ liệu cũ, không bị âm thầm loại khỏi báo cáo.

## 4. Chọn nguồn thu thập và quyền của collector

Có thể thu thập qua agent quản lý endpoint, truy vấn tại máy, kênh quản trị từ xa được tổ chức cho phép hoặc dữ liệu kiểm kê đã được xác minh. Mỗi nguồn có độ trễ và phạm vi khác nhau.

| Nguồn | Giá trị sử dụng | Điểm cần xác minh |
|---|---|---|
| Quan sát trực tiếp trên endpoint | Phản ánh thành viên nhóm tại lúc truy vấn | Đúng máy, đúng thời điểm, truy vấn có hoàn tất không |
| Nguồn danh tính miền | Giải thích nhóm miền và thành viên liên quan | Có đủ quyền đọc, có nhóm lồng hoặc quan hệ tin cậy không |
| Chính sách quản lý tập trung | Thể hiện trạng thái tổ chức muốn áp dụng | Chính sách đã đến máy và có bị cấu hình khác tác động không |
| Nguồn PAM/vault | Cho biết đối tượng đã được quản lý như thế nào | Ánh xạ tới đúng tài khoản và tài sản, dữ liệu còn mới không |
| Log hoạt động và thay đổi nhóm | Bổ sung lịch sử sử dụng hoặc thay đổi | Phạm vi log, thời gian lưu, đồng bộ thời gian và phần thiếu |

Chính sách mong muốn và trạng thái quan sát là hai dữ liệu khác nhau. Một chính sách nói nhóm X phải là admin chưa chứng minh máy đã áp dụng thành công. Ngược lại, máy có thành viên ngoài chính sách là một phát hiện cần điều tra, không phải lý do bỏ qua kết quả thực tế.

Collector nên dùng quyền đọc tối thiểu đủ cho phương thức thu thập. Nếu cơ chế cụ thể cần quyền cao hơn, phải giới hạn phạm vi, thời hạn và bảo vệ danh tính đó. Không dùng một credential quản trị dùng chung trên toàn bộ hạ tầng chỉ để tiện triển khai discovery.

Truy vấn đọc vẫn có thể tạo log, tải xử lý hoặc lỗi xác thực. Khi mở rộng thu thập, cần giới hạn tốc độ, thời gian chờ và số lần thử lại; không tự nâng quyền hoặc đổi phương thức truy cập ngoài phạm vi đã cho phép khi gặp lỗi.

## 5. Thu thập thành viên trực tiếp trên Windows

### 5.1. Dùng SID của nhóm thay vì tên hiển thị

Ví dụ PowerShell sau dành cho Windows có module `Microsoft.PowerShell.LocalAccounts` phù hợp với môi trường chạy. Đoạn lệnh đọc tại máy hiện tại và in một bản ghi kết quả; không ghi file, đổi nhóm hoặc lấy mật khẩu.

```powershell
try {
    $adminGroup = Get-LocalGroup -SID 'S-1-5-32-544' -ErrorAction Stop
    $members = @(
        Get-LocalGroupMember -SID $adminGroup.SID -ErrorAction Stop
    )

    $observations = @(
        foreach ($member in $members) {
            [pscustomobject]@{
                principal_sid    = $member.SID.Value
                display_name     = $member.Name
                object_class     = [string]$member.ObjectClass
                principal_source = [string]$member.PrincipalSource
            }
        }
    )

    [pscustomobject]@{
        computer_name     = $env:COMPUTERNAME
        collected_at_utc  = [DateTimeOffset]::UtcNow.ToString('o')
        collection_status = 'SUCCESS'
        group_sid         = $adminGroup.SID.Value
        direct_members    = $observations
    } | ConvertTo-Json -Depth 6
}
catch {
    [pscustomobject]@{
        computer_name     = $env:COMPUTERNAME
        collected_at_utc  = [DateTimeOffset]::UtcNow.ToString('o')
        collection_status = 'FAILED'
        error_type        = $_.Exception.GetType().FullName
        error_message     = $_.Exception.Message
    } | ConvertTo-Json -Depth 4
}
```

Tên máy trong kết quả chưa thay thế định danh tài sản. Bộ điều phối vẫn cần gắn bản ghi với máy đã được xác minh trong danh mục và ghi nhận phiên bản collector, phương thức thu thập cùng thời gian hoàn tất.

Khả năng có module, quyền đọc và cách phân giải danh tính phụ thuộc môi trường. Nếu lệnh không tồn tại, không truy vấn được nhóm hoặc gặp lỗi phân giải thành viên, cần ghi nhận lỗi. Không chuyển một lỗi thành mảng rỗng rồi kết luận “không có admin”.

Ví dụ này chỉ thu thành viên trực tiếp. Nếu một phần tử là nhóm miền, cần bước truy vết từ nguồn danh tính tương ứng. `principal_source` là thuộc tính hỗ trợ phân loại, không thay thế việc xác minh định danh; giá trị thiếu hoặc không phân giải được phải được giữ là chưa rõ.

### 5.2. Xác định tài khoản quản trị tích hợp kể cả khi đổi tên

Trong phạm vi tài khoản cục bộ trên Windows thành viên, tài khoản quản trị tích hợp có RID `500`, tức SID kết thúc bằng `-500`. Có thể dùng dữ liệu tài khoản để nhận diện thay vì chỉ tìm tên `Administrator`:

```powershell
Get-LocalUser -ErrorAction Stop |
    Where-Object { $_.SID.Value -match '-500$' } |
    Select-Object Name, SID, Enabled
```

Cần diễn giải kết quả trong ngữ cảnh máy và nguồn tài khoản cục bộ. Không dùng điều kiện “SID kết thúc bằng 500” trên một kho danh tính trộn nhiều miền rồi coi mọi kết quả là cùng một tài khoản.

Tài khoản bị đổi tên vẫn phải xuất hiện trong kiểm kê. Trạng thái `Enabled = false` là một điều kiện giảm khả năng sử dụng hiện tại, không xóa đi cấu hình quyền hay nhu cầu bảo vệ tài khoản khi được bật lại.

Không cần đọc password hash, trích xuất kho credential hoặc thử mật khẩu để nhận diện tài khoản này. Discovery về quyền nên thu định danh và thuộc tính cần thiết, không thu nội dung secret.

## 6. Mở rộng từ thành viên trực tiếp đến đường cấp quyền

Giả sử nhóm Administrators trên máy `asset-023` chứa nhóm miền `ACME\Ops-Servers`. Nhóm này có thể chứa người dùng hoặc nhóm khác. Nếu chỉ ghi tên nhóm cuối cùng, báo cáo không cho biết những danh tính nào nhận quyền qua nhóm đó.

Có thể biểu diễn quan hệ:

```text
ACME\lan
    └─ là thành viên của ACME\Ops-Servers
          └─ là thành viên Administrators trên asset-023
                └─ có đường cấp quyền quản trị tại asset-023
```

Mỗi cạnh cần có nguồn và thời gian quan sát. Nếu quan hệ nhóm lấy lúc 09:00 còn endpoint được thu lúc 16:00, đó là hai ảnh chụp khác thời điểm. Báo cáo phải thể hiện sai lệch thời gian thay vì tạo cảm giác toàn bộ chuỗi được xác minh đồng thời.

### 6.1. Nguyên tắc mở rộng nhóm

- Dùng định danh nhóm để tra thành viên, không nối bằng tên hiển thị.
- Phân giải trong đúng miền hoặc nguồn danh tính; quan hệ qua miền cần nguồn dữ liệu được phép và đủ tin cậy.
- Theo dõi nhóm đã thăm để tránh lặp hoặc vòng tham chiếu; đặt giới hạn độ sâu và lượng dữ liệu.
- Giữ lại đường đi từ danh tính đến nhóm quản trị trên từng máy.
- Ghi rõ điểm dừng do thiếu quyền, hết thời gian, không hỗ trợ hoặc không phân giải được.
- Kiểm tra ngữ nghĩa nhóm và cơ chế tạo token của nền tảng trước khi gọi mọi đường quan hệ là quyền hiệu lực chắc chắn.

Đường quan hệ trong một đồ thị danh tính là bằng chứng phục vụ đánh giá. Quyền hiệu lực thực tế còn phụ thuộc loại nhóm, phạm vi nhóm, quan hệ tin cậy và cơ chế ủy quyền. Công cụ không nên tự suy rộng mọi cạnh `member_of` thành khả năng quản trị thành công trên mọi phiên.

Mã giả sau chỉ mô tả việc thu bằng chứng đường nhóm, không phải bộ máy tính quyền hoàn chỉnh:

```text
function trace_members(group_id, authority, visited, path):
    key = (authority, group_id)
    if key in visited:
        record_cycle_or_repeated_group(path, key)
        return

    visited = visited plus key
    result = directory_read_members(authority, group_id)
    if result is incomplete:
        record_visibility_gap(path, result.reason)

    for member in result.available_members:
        next_path = path plus member.stable_id
        record_membership_evidence(member, group_id, next_path)
        if member is a resolvable_group:
            trace_members(
                member.id,
                member.authority,
                visited,
                next_path
            )
```

Nếu triển khai dùng một bộ nhớ đệm hoặc tập đã thăm chung để giảm truy vấn, vẫn cần giữ đủ đường tham chiếu. Một danh tính có thể nhận quyền qua nhiều nhóm; xóa đường trùng quá sớm có thể làm mất bằng chứng cho một đường cấp quyền độc lập.

### 6.2. Không phân giải được SID chưa có nghĩa là tài khoản mồ côi

Một SID chưa hiện tên có thể do thiếu kết nối tới nguồn danh tính, thiếu quyền đọc, lỗi đồng bộ, quan hệ tin cậy không sẵn sàng hoặc đối tượng đã bị xóa. Chỉ quan sát SID không phân giải được chưa đủ phân biệt các trường hợp này.

Giữ nguyên SID, máy liên quan, nguồn và lỗi phân giải. Gắn trạng thái `UNRESOLVED`, sau đó xác minh với nguồn có thẩm quyền. Chỉ phân loại tài khoản mồ côi hoặc thành viên không còn hợp lệ khi có bằng chứng thích hợp. Không tự xóa thành viên trong lúc discovery.

## 7. Chuẩn hóa dữ liệu để không gộp nhầm danh tính

Hai máy có thể đều có tài khoản `local-maint`, nhưng đó là hai tài khoản cục bộ khác nhau. Cùng tên cũng không chứng minh dùng chung mật khẩu.

Khóa danh tính nên bao gồm nguồn thẩm quyền và định danh ổn định. Với tài khoản cục bộ, cần gắn thêm tài sản/vòng đời máy để diễn giải đúng, đặc biệt khi có tái tạo máy hoặc dữ liệu nguồn không bảo đảm duy nhất.

| Trường | Mục đích |
|---|---|
| `asset_id`, `management_domain` | Xác định máy và miền quản lý |
| `principal_id`, `identity_authority` | Xác định danh tính từ đúng nguồn |
| `display_name` | Hỗ trợ người đọc, không làm khóa duy nhất |
| `relationship_type` | Phân biệt thành viên trực tiếp, quan hệ nhóm và loại bằng chứng khác |
| `privilege_path` | Lưu đường cấp quyền đến máy |
| `account_state` | Đang bật, bị vô hiệu hóa, đã xóa hoặc chưa xác minh |
| `observed_at`, `source` | Thời gian và xuất xứ dữ liệu |
| `collection_status`, `resolution_status` | Phân biệt đủ dữ liệu với khoảng trống |
| `owner_status`, `pam_management_status` | Hỗ trợ bước quản trị tiếp theo |

Ví dụ **JSON minh họa mô hình dữ liệu**, không phải schema của một sản phẩm:

```json
{
  "asset_id": "asset-023",
  "management_domain": "acme",
  "host_role": "member_server",
  "observation_id": "obs-0042",
  "collection_status": "SUCCESS",
  "observed_at": "2026-11-26T09:00:00+07:00",
  "principal": {
    "identity_authority": "asset-023-local",
    "principal_id": "S-1-5-21-111111111-222222222-333333333-1007",
    "display_name": "ORDERS-02\\local-maint",
    "account_state": "enabled"
  },
  "privilege_path": [
    {
      "relationship": "direct_member_of",
      "group_id": "S-1-5-32-544",
      "scope_asset_id": "asset-023"
    }
  ],
  "pam_management_status": "UNVERIFIED",
  "owner_status": "UNASSIGNED"
}
```

Trong ví dụ, thành viên trực tiếp đã được quan sát nhưng trạng thái quản lý PAM và chủ sở hữu chưa được xác minh. Không tự đổi `UNVERIFIED` thành `UNMANAGED` chỉ vì chưa tra được nguồn PAM. Các thuộc tính cần có xuất xứ riêng nếu được bổ sung từ những nguồn khác nhau.

## 8. Đọc kết quả qua một tình huống cụ thể

Phạm vi được giao gồm ba máy. Kết quả đầu tiên như sau:

| Máy | Quan sát | Kết luận ban đầu |
|---|---|---|
| `asset-023` | Administrators có tài khoản cục bộ `local-maint`, tài khoản tích hợp RID 500 bị vô hiệu hóa và nhóm miền `Ops-Servers` | Có thành viên trực tiếp; cần truy vết nhóm miền và xác minh quản lý credential |
| `asset-024` | Có tài khoản cục bộ cùng tên `local-maint` nhưng định danh khác | Là một đối tượng tài khoản khác; chưa kết luận dùng chung mật khẩu |
| `asset-025` | Không kết nối được qua phương thức thu thập được phép | Chưa biết trạng thái local admin hiện tại |

Nguồn danh tính cho thấy `Ops-Servers` chứa hai người, trong đó một người đã chuyển đội. Đây là dấu hiệu cần rà soát quyền theo trách nhiệm hiện tại. Người chuyển đội không tự động bị kết luận là truy cập trái phép; cần đối chiếu với chính sách và quyết định cấp quyền còn hiệu lực.

Nếu không thể phân giải một nhóm con của `Ops-Servers`, phần thành viên trực tiếp của `asset-023` vẫn có thể thu thành công, nhưng phần truy vết danh tính cuối cùng là chưa đầy đủ. Nên biểu diễn riêng hai trạng thái này thay vì đánh dấu toàn bộ máy đã kiểm kê hoàn chỉnh.

Với `asset-025`, một lần quét thất bại không chứng minh không có local admin. Cũng không được tiếp tục hiển thị kết quả tháng trước như một quan sát mới. Giữ bản ghi cũ với thời điểm gốc, đánh dấu đã cũ và tạo việc bổ sung độ bao phủ.

### Phát hiện đáng ưu tiên

- Danh tính không có chủ sở hữu rõ ràng trên máy nhạy cảm.
- Nhóm rộng được gán vào Administrators của nhiều máy ngoài nhu cầu công việc.
- Tài khoản có quyền thường trực trong khi công việc chỉ cần thao tác theo phiên.
- Tài khoản dịch vụ có quyền quản trị nhưng chưa xác định được phụ thuộc vận hành.
- Cấu hình thực tế lệch khỏi chính sách được phê duyệt.
- Tài khoản hoặc SID chưa phân giải trên máy quan trọng.
- Máy quan trọng không thu thập được hoặc dữ liệu đã quá hạn yêu cầu.

Mức ưu tiên phải kết hợp tác động tài sản, độ rộng quyền, khả năng sử dụng và độ tin cậy dữ liệu. Không dùng một tên tài khoản lạ hoặc một thời điểm đăng nhập cũ làm bằng chứng duy nhất để xóa quyền.

## 9. Phân biệt discovery với thay đổi quản trị PAM

Discovery tạo đầu vào để ra quyết định. Việc đưa credential vào vault, đổi mật khẩu, gỡ thành viên nhóm hoặc triển khai JIT/JEA là các thay đổi cần thiết kế và thực hiện theo luồng riêng.

| Phát hiện | Bước quản trị có thể tiếp theo | Điều cần xác minh trước thay đổi |
|---|---|---|
| Tài khoản local admin chưa có chủ sở hữu | Xác nhận chủ sở hữu và mục đích sử dụng | Ai chịu trách nhiệm, tài khoản còn cần không |
| Credential quản trị cần được quản lý | Onboard vào cơ chế quản lý phù hợp | Đúng tài khoản/đích, phương thức truy cập và khả năng luân chuyển |
| Tài khoản dịch vụ là local admin | Thu hẹp quyền hoặc tách danh tính | Dịch vụ, tác vụ, phụ thuộc và quyền tối thiểu thực sự cần |
| Quyền quản trị thường trực của người dùng | Chuyển phần công việc phù hợp sang JIT/JEA | Khả năng cấp/thu hồi, kênh thực thi và phương án vận hành |
| Thành viên không còn nhu cầu | Rà soát và gỡ quyền được phê duyệt | Đường quyền khác, tác động và phương án khôi phục |
| SID không phân giải được | Điều tra nguồn danh tính | Đối tượng đã xóa hay chỉ đang thiếu khả năng quan sát |

Đổi mật khẩu tài khoản dịch vụ mà chưa biết nơi sử dụng có thể làm dừng dịch vụ hoặc tác vụ. Gỡ một tài khoản khỏi Administrators chưa chắc loại bỏ quyền qua nhóm khác. Ngược lại, đưa mật khẩu vào vault không tự làm giảm quyền hoặc chặn việc dùng credential ngoài phiên PAM.

Không so sánh mật khẩu bằng cách thu và lưu password hash trong kho discovery thông thường. Nếu tổ chức cần đánh giá việc tái sử dụng credential, đó phải là tác vụ riêng có cơ chế và phạm vi được cho phép. Với bài kiểm kê này, cùng tên tài khoản chỉ là một tín hiệu cần xác minh, không phải bằng chứng dùng chung secret.

## 10. Đối chiếu trên Unix/Linux

Trên Unix/Linux, khái niệm quyền quản trị không thể thay bằng việc tìm một nhóm tên `Administrators`. Cần xem cơ chế của hệ thống cụ thể.

| Dấu hiệu | Cách hiểu phù hợp |
|---|---|
| Tài khoản có UID 0 | Cần được xem xét như danh tính có quyền root theo cơ chế hệ thống |
| Thành viên nhóm tên `sudo` hoặc `wheel` | Là đầu mối cần tra chính sách; tên nhóm tự nó không cấp mọi quyền |
| Quy tắc sudo | Cần đọc theo chủ thể, máy, danh tính chạy thay, lệnh, đối số và điều kiện áp dụng |
| Nhóm từ nguồn danh tính tập trung | Cần xác định cách hệ thống phân giải và áp chính sách ở thời điểm sử dụng |
| Quyền đặc biệt trên executable hoặc cấu hình dịch vụ | Có thể tạo đường đặc quyền khác, cần luồng đánh giá phù hợp |

Chỉ liệt kê nhóm `sudo` hoặc `wheel` sẽ bỏ sót người được ủy quyền qua quy tắc khác. Chỉ thấy tên trong một file cũng chưa chứng minh đã đọc mọi nguồn cấu hình có hiệu lực hoặc các phần được include.

Cùng nguyên tắc với Windows, cần tách thành viên được quan sát, quy tắc cấp quyền và khả năng thực thi thực tế. Không suy rằng quyền chạy một lệnh cụ thể qua sudo đồng nghĩa với quyền root không giới hạn, nhưng cũng cần đánh giá liệu lệnh đó có khả năng thực thi thêm hành động rộng hơn hay không.

## 11. Phát hiện thay đổi và đo độ bao phủ

Một lần chụp trạng thái không duy trì được kiểm kê lâu dài. Thành viên nhóm, quan hệ nhóm miền, trạng thái tài khoản và tài sản đều có thể thay đổi.

Có thể kết hợp thu định kỳ với sự kiện thay đổi thành viên nhóm, tài khoản và chính sách từ các nguồn được phép. Sự kiện giúp phát hiện sớm; lần thu đối soát giúp phát hiện phần bị bỏ lỡ. Không coi thiếu sự kiện là bằng chứng cấu hình không đổi nếu nguồn log không đầy đủ.

Khi so sánh hai lần thu, cần phân biệt:

- Thêm hoặc xóa một thành viên trực tiếp.
- Thay đổi thành viên trong nhóm miền làm thay đổi đường quyền trên nhiều máy.
- Chỉ đổi tên hiển thị nhưng định danh giữ nguyên.
- Tài nguyên được tái tạo với định danh mới.
- Mất khả năng quan sát, khiến đối tượng không còn xuất hiện trong dữ liệu thu về.

Một tài khoản biến mất vì collector lỗi không phải bằng chứng quyền đã bị gỡ. Một nhóm vẫn ở nguyên trên endpoint cũng không chứng minh tập người nhận quyền không đổi.

### Chỉ số có mẫu số rõ ràng

```text
Độ bao phủ thu trực tiếp =
    số máy có kết quả thu trực tiếp thành công, còn đủ mới
    / tổng số máy trong phạm vi

Độ đầy đủ truy vết =
    số máy đủ mới, có thu trực tiếp thành công
    và đã hoàn tất phần truy vết danh tính cần thiết
    / tổng số máy trong phạm vi
```

Trong ví dụ ba máy, nếu `asset-023` và `asset-024` thu trực tiếp thành công nhưng `asset-025` thất bại, độ bao phủ thu trực tiếp là `2/3`. Nếu `asset-023` còn một nhóm chưa truy vết xong còn `asset-024` đã đầy đủ, độ đầy đủ truy vết là `1/3` theo cách định nghĩa trên.

Số thành viên trực tiếp, số nhóm và số tài khoản sau mở rộng là các chỉ số khác nhau. Cần khử trùng theo định danh khi đếm tài khoản, đồng thời vẫn giữ nhiều đường cấp quyền để phục vụ thu hồi và điều tra.

Có thể bổ sung tỷ lệ có chủ sở hữu, tỷ lệ được xác minh quản lý PAM, số SID chưa phân giải và tuổi dữ liệu. Những chỉ số này phải nêu rõ mẫu số và trạng thái chưa xác minh, tránh làm tỷ lệ đẹp hơn bằng cách loại các bản ghi khó thu thập.

## 12. Bằng chứng và kiểm thử chấp nhận

Bằng chứng nên nối được danh mục phạm vi, lần chạy collector, máy đích, dữ liệu thô cần thiết, bản ghi chuẩn hóa và kết luận. Lưu thời gian quan sát, nguồn, phiên bản công cụ, trạng thái truy vết và lý do thiếu dữ liệu.

Danh sách quản trị và quan hệ nhóm là dữ liệu nhạy cảm về hạ tầng và danh tính. Chỉ thu những trường cần thiết, kiểm soát người xem/sửa và thời hạn lưu. Không để đầu ra discovery trở thành nơi lưu credential hoặc dữ liệu cá nhân không liên quan.

### Bài tập thực hành

Thiết kế kiểm kê cho ba máy trong tình huống ở trên. Tạo bản ghi minh họa cho tài khoản cục bộ, nhóm miền và máy không truy vấn được; không dùng credential thật. Sau đó giải thích cách nối đường quyền của một thành viên nhóm miền tới đúng máy và cách chứng minh dữ liệu còn mới.

### Ma trận nghiệm thu trên môi trường thực hành được phép

| Ca kiểm tra | Kết quả cần đạt |
|---|---|
| Nhóm Administrators hiển thị bằng ngôn ngữ khác | Vẫn xác định được nhóm theo SID phù hợp |
| Tài khoản RID 500 đã đổi tên | Được nhận diện từ nguồn tài khoản cục bộ, không phụ thuộc tên |
| Tài khoản miền nằm trực tiếp trong nhóm quản trị | Được ghi nhận cùng miền thẩm quyền và định danh |
| Nhóm miền có thành viên lồng nhau | Lưu được đường quan hệ hoặc chỉ rõ điểm chưa phân giải |
| Hai máy có tài khoản cùng tên | Không gộp thành một danh tính cục bộ |
| SID không phân giải được | Giữ SID và lỗi; không tự kết luận mồ côi hoặc xóa thành viên |
| Collector bị từ chối truy cập hoặc timeout | Báo lỗi/chưa xác minh, không trả kết luận sạch |
| Thu endpoint thành công nhưng truy vết nhóm thất bại | Tách trạng thái thu trực tiếp và độ đầy đủ truy vết |
| Dữ liệu quá hạn độ mới | Đánh dấu cũ, không cập nhật giả thời điểm quan sát |
| Chỉ đổi tên tài khoản | Không báo nhầm thành một lần xóa và thêm danh tính |
| Thay đổi thành viên nhóm miền, endpoint không đổi | Phát hiện tác động đến đường quyền trên các máy liên quan |
| Tài khoản đã có đối tượng trong vault | Vẫn kiểm tra đúng ánh xạ và không tự kết luận quyền tối thiểu |
| Máy là domain controller | Đi vào luồng thu thập và diễn giải riêng |
| So sánh nhóm trước và sau discovery | Không có thay đổi thành viên do tác vụ thu thập tạo ra |

Kết quả discovery hữu ích khi có thể chỉ ra danh tính nào nhận quyền quản trị trên máy nào, qua đường nào, với mức độ xác minh và thời điểm cụ thể. Những phần chưa biết phải được giữ lại như công việc cần xử lý để bước quản trị PAM tiếp theo dựa trên bằng chứng đầy đủ hơn.