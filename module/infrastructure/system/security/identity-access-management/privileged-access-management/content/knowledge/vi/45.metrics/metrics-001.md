# Số privileged account

## 1. Vì sao PAM cần đo số tài khoản đặc quyền?

Một chương trình quản lý truy cập đặc quyền (Privileged Access Management — PAM) phải trả lời được câu hỏi: **Trong phạm vi đang quản lý, có bao nhiêu tài khoản mang quyền đặc biệt, và bao nhiêu tài khoản có thể dùng quyền đó tại thời điểm báo cáo?**

Đây là hai câu hỏi khác nhau. Một tài khoản đã bị vô hiệu hóa có thể vẫn còn trong nhóm quản trị. Một tài khoản được phép kích hoạt quyền theo cơ chế Just-in-Time (JIT) chưa chắc đang có phiên quyền đặc biệt. Một tài khoản quản trị miền xuất hiện trong nhiều nguồn khám phá vẫn chỉ là một tài khoản, dù nó có quyền trên nhiều hệ thống.

Nếu chỉ cộng số dòng xuất từ directory, hệ điều hành, cơ sở dữ liệu và vault, kết quả có thể vừa đếm trùng, vừa bỏ sót tài khoản ngoài PAM. Khi đó số liệu giảm chưa chắc chứng minh rằng rủi ro đã giảm; cũng có thể một nguồn thu thập vừa bị lỗi.

Trong chương Metrics, bài học này xây dựng cách đo số privileged account từ định nghĩa, mô hình dữ liệu, công thức và ví dụ đến cách vận hành báo cáo. Các tên chỉ số và ngưỡng minh họa là quy ước nội bộ để thực hành, không phải một chuẩn bắt buộc cho mọi tổ chức.

Sau bài học, người học cần làm được những việc sau:

- Chọn đơn vị đếm và ranh giới quản lý tài khoản.
- Phân biệt tài khoản, người sử dụng, lần cấp quyền, secret và phiên truy cập.
- Tách tài khoản có quyền thường trực, quyền đủ điều kiện kích hoạt và quyền JIT đang hoạt động.
- Khử trùng dữ liệu từ nhiều nguồn mà vẫn giữ bằng chứng nguồn.
- Giải thích sự thay đổi của số lượng tài khoản bằng dữ liệu kiểm kê và thay đổi thực tế.

## 2. Privileged account là gì trong phép đo?

### 2.1. Phân loại theo khả năng thực hiện hành động

Trong bài học này, một tài khoản được phân loại là đặc quyền khi nó gắn với ít nhất một khả năng quản trị nằm trong danh mục quyền đặc biệt đã phê duyệt của tổ chức.

Ví dụ về khả năng cần xem xét:

| Nhóm khả năng | Ví dụ trong phạm vi PAM |
| --- | --- |
| Quản trị danh tính | Tạo tài khoản quản trị, đặt lại thông tin xác thực của tài khoản khác, cấp vai trò đặc quyền |
| Quản trị hệ thống | Cấu hình hệ điều hành, chạy tác vụ với quyền quản trị, thay đổi cơ chế kiểm soát truy cập |
| Quản trị dữ liệu | Quản lý tài khoản cơ sở dữ liệu, thay đổi phân quyền, truy cập dữ liệu nhạy cảm ngoài chức năng thông thường |
| Quản trị nền tảng | Quản lý tài nguyên cloud, cụm container hoặc cấu hình mạng trong phạm vi được giao |
| Kiểm soát cơ chế bảo vệ | Thay đổi chính sách vault, cấu hình ghi phiên, cấu hình audit hoặc điều khiển công cụ bảo mật |

Không chỉ dựa vào tên tài khoản như `admin`, `root` hay hậu tố `-adm`. Một tài khoản có tên bình thường vẫn có thể được cấp quyền quản trị qua nhóm lồng nhau hoặc vai trò kế thừa. Ngược lại, một tên chứa chữ `admin` không tự chứng minh rằng tài khoản còn có đặc quyền.

Danh mục phải nêu rõ quyền nào được tính, trên tài nguyên nào, trong môi trường nào. Nếu phạm vi bao gồm quyền đọc đặc biệt đối với dữ liệu nhạy cảm thì phải ghi rõ; không ngầm giả định chỉ quyền ghi hoặc quyền quản trị toàn hệ thống mới là đặc quyền.

### 2.2. Phân loại theo loại danh tính

PAM không chỉ quản lý tài khoản của con người. Phép đo cần bao phủ các loại danh tính phù hợp với phạm vi tổ chức:

- Tài khoản quản trị cá nhân, tách biệt với tài khoản làm việc thông thường.
- Tài khoản quản trị dùng chung hoặc tài khoản được truy cập qua cơ chế checkout.
- Tài khoản dịch vụ, tài khoản ứng dụng và tài khoản tự động hóa.
- Danh tính workload hoặc service principal có khả năng thực hiện hành động đặc quyền.
- Tài khoản khẩn cấp, còn gọi là break-glass.
- Tài khoản của nhà cung cấp hoặc bên thứ ba.

Các nhóm trên có thể giao nhau. Một tài khoản khẩn cấp có thể đồng thời là tài khoản dùng chung. Một danh tính tự động hóa có thể thuộc hệ thống của nhà cung cấp. Vì vậy, nên có một chiều phân loại chính, chẳng hạn `HUMAN` hoặc `NON_HUMAN`, cùng các thuộc tính độc lập như `is_shared`, `is_break_glass`, `is_vendor`.

Nếu dùng những thuộc tính giao nhau để chia biểu đồ, không cộng các cột rồi gọi đó là tổng số tài khoản duy nhất.

### 2.3. Phân biệt tài khoản với các đối tượng liên quan

| Đối tượng | Câu hỏi trả lời | Có phải đơn vị của chỉ số số tài khoản? |
| --- | --- | --- |
| Tài khoản hoặc principal | Danh tính nào được hệ thống nhận diện? | Có, theo khóa chuẩn hóa đã chọn |
| Người sử dụng | Ai có thể sử dụng hoặc yêu cầu tài khoản? | Không |
| Quan hệ cấp quyền | Tài khoản có quyền gì trên tài nguyên nào? | Không |
| Vai trò hoặc nhóm | Quyền được tập hợp và trao qua cấu trúc nào? | Không tự động; chỉ đếm nếu mô hình xác thực thực sự coi nó là principal thuộc phạm vi |
| Secret, khóa hoặc chứng thư | Tài khoản xác thực bằng thông tin nào? | Không |
| Phiên hoặc lần kích hoạt | Đã sử dụng quyền trong khoảng thời gian nào? | Không |

Một tài khoản dùng chung cho mười kỹ sư vẫn là một tài khoản, nhưng có vấn đề riêng về truy vết người sử dụng. Một tài khoản dịch vụ có ba phiên bản secret do luân chuyển vẫn là một tài khoản. Hai tài khoản có cùng mật khẩu không vì thế trở thành một tài khoản.

Đối với nền tảng hỗ trợ vai trò có thể được assume hoặc danh tính liên kết, phải công bố cách mô hình hóa principal. Không cộng một người, một vai trò có thể assume và từng phiên tạm thời vào cùng một tổng mà không phân biệt đơn vị.

## 3. Khóa đếm: cùng tên chưa chắc cùng tài khoản

### 3.1. Chọn ranh giới cấp phát danh tính

Một khóa tài khoản chuẩn hóa nên kết hợp:

```text
account_key =
    identity_authority_key
    + principal_identifier
    + lifecycle_discriminator_if_needed
```

Trong đó:

- `identity_authority_key` xác định nơi cấp phát danh tính: directory, tenant, hệ thống cục bộ hoặc miền quản lý tương ứng.
- `principal_identifier` ưu tiên mã định danh ổn định do nguồn cấp.
- `lifecycle_discriminator_if_needed` giúp phân biệt tài khoản bị xóa rồi được tạo lại nếu nguồn tái sử dụng tên hoặc mã.

Đây là mô hình logic. Định dạng kỹ thuật cụ thể phải phù hợp với từng nguồn; không có một khóa ghép duy nhất dùng đúng cho mọi nền tảng.

Ví dụ:

| Tình huống | Quy tắc đếm |
| --- | --- |
| Một principal directory xuất hiện trong directory và vault | Ánh xạ về cùng khóa, đếm một |
| Cùng một principal directory có quyền trên 200 máy | Một tài khoản, nhiều quan hệ quyền và tài nguyên |
| Tài khoản local `root` trên hai máy độc lập | Hai tài khoản thuộc hai ranh giới quản lý cục bộ |
| Hai principal có cùng tên hiển thị ở hai tenant | Hai tài khoản |
| Một tài khoản được đổi tên nhưng giữ định danh nguồn | Vẫn một tài khoản |
| Tài khoản bị xóa, sau đó tạo lại cùng tên | Hai thực thể qua hai vòng đời; báo cáo tại một thời điểm chỉ tính thực thể còn hiện diện |

Với tài khoản local, chỉ dùng tên máy có thể sai khi máy được dựng lại hoặc đổi tên. Chỉ dùng UID hoặc tên đăng nhập cũng có thể sai nếu giá trị được tái sử dụng. Cần kết hợp thông tin định danh tài sản, nguồn quản lý và vòng đời theo khả năng của nguồn.

### 3.2. Tách khóa nguồn với khóa chuẩn hóa

Hệ thống thu thập nên giữ cả hai lớp:

```text
source_record_id -> canonical_account_key
```

Một tài khoản có thể có nhiều `source_record_id` vì được phát hiện qua directory, endpoint và PAM. Các bản ghi nguồn vẫn phải được giữ để truy nguyên; thao tác khử trùng không có nghĩa là xóa mất bằng chứng.

Nếu chưa đủ dữ liệu để ghép an toàn, đưa bản ghi vào hàng chờ đối soát. Không ghép chỉ vì tên gần giống, cùng email hoặc cùng chủ sở hữu. Ghép sai có thể làm tổng số tài khoản đặc quyền thấp giả tạo.

Bản ghi chưa xác định được khóa phải được công bố trong số liệu chất lượng dữ liệu. Không âm thầm loại chúng ra rồi trình bày tổng còn lại như số lượng đầy đủ của toàn tổ chức.

## 4. Định nghĩa một hợp đồng đo lường

Trước khi viết truy vấn, cần thống nhất một hợp đồng đo lường. Hợp đồng này giúp hai nhóm độc lập có thể tính lại cùng một chỉ số từ cùng một bộ dữ liệu.

| Thành phần | Nội dung cần xác định |
| --- | --- |
| Tên chỉ số | Ví dụ: số tài khoản đặc quyền đã xác nhận trong production |
| Đơn vị | Tài khoản/principal duy nhất theo `account_key` |
| Phạm vi | Tenant, hệ thống, môi trường và loại tài sản được đưa vào |
| Mốc thời gian | Snapshot tại thời điểm nào, theo múi giờ nào |
| Tiêu chí đặc quyền | Phiên bản danh mục quyền, cách xử lý kế thừa và nhóm lồng nhau |
| Trạng thái tài khoản | Enabled, disabled và unknown được xử lý thế nào |
| Chế độ quyền | Standing, eligible và JIT đang hoạt động |
| Nguồn chứng cứ | Directory, endpoint, cloud, cơ sở dữ liệu, vault và các nguồn liên quan |
| Độ mới dữ liệu | Thời gian quan sát gần nhất và giới hạn chấp nhận của từng nguồn |
| Giới hạn | Nguồn thiếu, quyền chưa phân giải, tài khoản chưa ghép khóa |
| Chủ sở hữu | Ai duy trì định nghĩa và ai xác nhận báo cáo |

Ví dụ một mô tả đủ rõ:

> Tại mốc báo cáo 00:00 UTC của ngày được chọn, đếm các principal đã xác nhận còn tồn tại, có ít nhất một quan hệ quyền thường trực, quyền đủ điều kiện kích hoạt hoặc quyền JIT đang hoạt động thuộc production. Khử trùng theo authority và định danh principal. Công bố riêng trạng thái enabled, disabled và unknown. Các quan hệ chưa phân giải không được trộn vào tổng đã xác nhận.

Nếu một nguồn đã quá hạn thu thập, báo cáo phải hiển thị trạng thái thiếu độ mới. Giá trị từ snapshot cũ có thể còn hữu ích như thông tin gần nhất đã biết, nhưng không được mô tả là trạng thái hiện tại đã xác minh.

## 5. Một chỉ số tổng và các tập con cần đi cùng

### 5.1. Tập tài khoản đặc quyền trong kiểm kê

Gọi:

- `t` là mốc snapshot báo cáo.
- `S` là phạm vi đã chọn.
- `A(t, S)` là tập tài khoản đã xác nhận còn hiện diện trong phạm vi.
- `P(a, t, S)` là tập quan hệ đặc quyền hợp lệ của tài khoản `a`, đã phân giải theo quy tắc báo cáo.

Định nghĩa số tài khoản đặc quyền đã xác nhận trong kiểm kê:

```text
I(t, S) = { a thuộc A(t, S) | P(a, t, S) khác rỗng }

N_inventory(t, S) = số phần tử của I(t, S)
```

Trong quy ước của bài học, `P` bao gồm quyền thường trực, quyền eligible và quyền JIT đang hoạt động. Tài khoản disabled vẫn có thể thuộc `I` nếu còn quan hệ quyền hợp lệ trong kiểm kê. Lý do là việc vô hiệu hóa đăng nhập không đồng nghĩa với việc đã dọn sạch mọi quan hệ đặc quyền.

Đây là số tài khoản được xác nhận, không phải khẳng định mọi tài khoản đặc quyền trong thực tế đều đã được phát hiện.

### 5.2. Tập tài khoản có khả năng sử dụng quyền tại snapshot

Tách các tập sau trong số tài khoản đã xác nhận enabled:

```text
S_standing = tài khoản enabled có ít nhất một quyền thường trực
J_active   = tài khoản enabled có ít nhất một quyền JIT đang hoạt động
E_eligible = tài khoản enabled có ít nhất một quyền đủ điều kiện kích hoạt

C_current  = S_standing hợp J_active
```

Khi đó:

```text
N_current =
    N_standing + N_jit_active - N_standing_and_jit_active
```

Không cộng `N_eligible` vào `N_current`: quyền eligible chưa kích hoạt không phải quyền đang hoạt động. Một tài khoản có thể đồng thời thuộc cả ba tập; ví dụ quyền đọc quản trị thường trực, quyền triển khai JIT đang hoạt động và quyền quản trị khác còn ở trạng thái eligible.

Tên `N_current` ở đây là kết quả theo mô hình dữ liệu đã phân giải. Nó không chứng minh rằng mỗi tài khoản chắc chắn đăng nhập thành công, cũng không chứng minh tài khoản ngoài tập không thể dùng token hoặc phiên còn hiệu lực chưa được nguồn dữ liệu phản ánh.

Nếu trạng thái enabled chưa xác định, không tự quy thành disabled. Công bố nhóm unknown để người đọc thấy phần chưa chắc chắn.

### 5.3. Không nhầm trạng thái quyền với thời gian sử dụng

Cần phân biệt:

- Tài khoản có quyền: được xác định từ quan hệ cấp quyền.
- Tài khoản đã sử dụng: được xác định từ sự kiện xác thực hoặc thao tác trong một khoảng thời gian.
- Tài khoản chưa sử dụng gần đây: vẫn có thể còn quyền đặc biệt.
- Tài khoản hết hạn kích hoạt JIT: có thể vẫn đủ điều kiện yêu cầu quyền lại.

Một tài khoản break-glass không được sử dụng trong nhiều tháng không thể tự động bị xem là không đặc quyền. Việc giữ hoặc thu hồi nó là quyết định về kiểm soát và khả năng khôi phục, không phải hệ quả của phép đếm đăng nhập.

### 5.4. Các chỉ số bổ trợ

| Chỉ số | Mục đích |
| --- | --- |
| `N_inventory` | Biết quy mô tập tài khoản đặc quyền đã xác nhận |
| `N_current` | Theo dõi tập tài khoản enabled có quyền hoạt động theo mô hình |
| `N_standing` | Theo dõi quyền tồn tại thường xuyên |
| `N_eligible` | Biết tập tài khoản có thể yêu cầu hoặc kích hoạt quyền |
| `N_jit_active` | Biết tập tài khoản đang có quyền JIT hoạt động |
| `N_disabled_privileged` | Theo dõi tài khoản disabled nhưng vẫn còn quan hệ quyền |
| `N_unknown_state` | Công bố phần chưa xác định trạng thái tài khoản |
| `N_without_owner` | Nhận diện tài khoản chưa có chủ sở hữu hợp lệ |
| `N_candidate_unresolved` | Theo dõi ứng viên đặc quyền chưa đủ bằng chứng phân loại |

Không cộng các dòng của bảng thành một tổng. Chúng là các góc nhìn khác nhau, một số chồng lấn. Với ứng viên chưa phân giải, cần nêu rõ đang đếm bản ghi nguồn hay principal đã có khóa; không đặt cùng nhãn đơn vị khi bản chất khác nhau.

## 6. Ví dụ đếm trên một snapshot nhỏ

Giả sử tổ chức đã chuẩn hóa được chín tài khoản sau trong phạm vi báo cáo:

| Khóa rút gọn | Loại tài khoản | Trạng thái | Quan hệ đặc quyền |
| --- | --- | --- | --- |
| `dir:lan-adm` | Cá nhân | Enabled | Standing trên ba nhóm tài nguyên |
| `host-a:root` | Local | Enabled | Standing |
| `host-b:root` | Local | Enabled | Standing |
| `dir:svc-deploy` | Dịch vụ | Enabled | Standing |
| `tenant:vendor-ops` | Nhà cung cấp | Enabled | Eligible và JIT đang hoạt động |
| `tenant:emergency` | Break-glass | Enabled | Standing |
| `dir:old-admin` | Cá nhân | Disabled | Còn quan hệ standing |
| `tenant:cloud-operator` | Cá nhân | Enabled | Chỉ eligible |
| `db:legacy-operator` | Dịch vụ | Unknown | Quan hệ standing đã xác nhận |

Bản ghi `dir:lan-adm` được directory và vault cùng phát hiện. Vì hai nguồn được đối chiếu về cùng principal, không đếm hai lần.

Kết quả:

```text
N_inventory            = 9
N_enabled_inventory    = 7
N_disabled_privileged  = 1
N_unknown_state        = 1

N_standing             = 5
N_jit_active           = 1
N_standing_and_jit_active = 0
N_current              = 5 + 1 - 0 = 6
N_eligible             = 2
```

Bảy tài khoản enabled gồm sáu tài khoản có quyền đang hoạt động và một tài khoản chỉ eligible. Hai tài khoản eligible là `vendor-ops` và `cloud-operator`; `vendor-ops` đã nằm trong `N_current`.

Một số kết luận sai cần tránh:

- “Có tám tài khoản hiện có quyền vì sáu current cộng hai eligible.” Sai vì eligible chưa kích hoạt khác current và còn chồng lấn.
- “Hai tài khoản root giống tên nên chỉ tính một.” Sai vì chúng thuộc hai hệ thống local độc lập.
- “Tài khoản Lan quản trị ba nhóm tài nguyên nên tính ba.” Sai vì đang đo tài khoản, không đo quan hệ quyền.
- “Tài khoản cũ đã disabled nên xóa khỏi mọi báo cáo.” Sai với định nghĩa inventory đang dùng; nó cần được nhìn thấy trong nhóm disabled còn quan hệ quyền.
- “Unknown tương đương không thể truy cập.” Chưa đủ bằng chứng.

Phép đếm đúng phải bảo toàn đơn vị từ dữ liệu nguồn đến biểu đồ cuối cùng.

## 7. Thu thập và chuẩn hóa dữ liệu

### 7.1. Bắt đầu từ nguồn quyền, không chỉ từ vault

Vault cho biết những tài khoản hoặc secret đã được đưa vào một cơ chế quản lý cụ thể. Nó không tự chứng minh toàn bộ tài khoản đặc quyền trong tổ chức đã được phát hiện.

Một quy trình kiểm kê cần kết hợp nguồn phù hợp với phạm vi:

1. Nguồn định danh cung cấp principal và trạng thái vòng đời.
2. Nguồn phân quyền cung cấp vai trò, nhóm, quyền trực tiếp, quyền kế thừa và điều kiện kích hoạt.
3. Nguồn tài sản cung cấp ranh giới hệ thống và môi trường.
4. PAM hoặc vault cung cấp quan hệ quản lý, luân chuyển và truy cập.
5. Nguồn audit hoặc phiên truy cập hỗ trợ đối soát hoạt động.

Báo cáo chỉ lấy tài khoản trong vault nên mang tên “tài khoản đặc quyền đang được vault quản lý”, không nên đặt tên “toàn bộ tài khoản đặc quyền”.

### 7.2. Chuẩn hóa quan hệ quyền trước khi đếm

Đường đi từ principal đến quyền có thể gồm nhiều bước:

```text
principal
    -> nhóm trực tiếp
    -> nhóm lồng nhau hoặc vai trò kế thừa
    -> quyền quản trị
    -> phạm vi tài nguyên
```

Chỉ quét một lớp membership có thể bỏ sót quyền gián tiếp. Ngược lại, cùng một tài khoản có nhiều đường đến cùng quyền không được nhân số tài khoản.

Với quyền có điều kiện, deny, ràng buộc ngữ cảnh hoặc cơ chế đặc thù nền tảng, cần một bước phân giải theo semantics của nguồn. Nếu chưa xác định được khả năng thực tế, đánh dấu chưa phân giải thay vì suy luận đơn giản rằng có một dòng role assignment nghĩa là có toàn quyền.

Bài học dùng bảng quan hệ đã chuẩn hóa để minh họa phép đếm. Truy vấn tổng hợp không thay thế bộ phân giải quyền của từng hệ thống.

### 7.3. Xử lý tài khoản biến mất và dữ liệu cũ

Một lần quét không thấy tài khoản có thể do:

- Tài khoản đã bị xóa.
- Nguồn thu thập thiếu quyền đọc.
- Một trang phân trang chưa được tải.
- Kết nối đến một vùng hoặc tenant bị lỗi.
- Tài khoản được chuyển sang phạm vi khác.
- Bộ lọc nguồn thay đổi.

Chỉ xác nhận đã xóa khi có bằng chứng phù hợp, chẳng hạn sự kiện vòng đời hoặc kết quả kiểm kê đầy đủ theo chính sách. Không biến lỗi thu thập thành sự kiện giảm tài khoản.

Mỗi nguồn cần có thời điểm quan sát, trạng thái hoàn tất và thông tin độ mới. Có thể báo “số gần nhất đã biết” khi nguồn thiếu, nhưng phải tách biệt với “snapshot đã xác minh đầy đủ”.

### 7.4. Đếm tài khoản tồn tại ngắn

Danh tính tạm thời có thể được tạo và hủy giữa hai lần quét. Khi đó snapshot cuối ngày có thể bằng không dù trong ngày từng có nhiều tài khoản đặc quyền.

Nên phân biệt:

```text
Snapshot count:
    Số tài khoản hiện diện tại một mốc.

Period distinct count:
    Số account_key khác nhau từng hiện diện trong khoảng thời gian.

Peak concurrent count:
    Số tài khoản cùng hiện diện lớn nhất trong khoảng thời gian.
```

Không dùng ba chỉ số này thay thế nhau. Với principal tạm thời, còn phải phân biệt tài khoản tạm được cấp phát thực sự với các session của cùng một principal; chỉ đếm session như tài khoản nếu hợp đồng đo lường quy định một loại đối tượng khác và đặt tên rõ.

## 8. Mô hình dữ liệu và truy vấn minh họa

### 8.1. Ba tập dữ liệu đầu vào

Giả sử kho dữ liệu có ba bảng snapshot:

```text
account_snapshot
    report_id
    account_key
    account_type
    enabled_state        -- ENABLED, DISABLED, UNKNOWN
    existence_state      -- PRESENT, DELETED, UNKNOWN
    owner_id

privilege_path_snapshot
    report_id
    path_id
    account_key
    scope_key
    grant_mode           -- STANDING, ELIGIBLE, JIT_ACTIVE
    valid_in_snapshot
    resolution_state     -- RESOLVED, UNRESOLVED

report_scope_snapshot
    report_id
    scope_key
    in_scope
```

Các điều kiện đầu vào:

- `account_snapshot` có đúng một dòng cho mỗi cặp `report_id, account_key`.
- `report_scope_snapshot` có đúng một dòng cho mỗi cặp `report_id, scope_key`.
- Mỗi snapshot dùng cùng một phiên bản phạm vi và quy tắc phân loại quyền.
- `privilege_path_snapshot` có thể có nhiều dòng cho cùng tài khoản vì nhiều đường quyền.
- Một dòng `JIT_ACTIVE` chỉ hợp lệ nếu việc kích hoạt còn hiệu lực tại mốc snapshot.
- Một dòng `ELIGIBLE` mô tả điều kiện kích hoạt hợp lệ, không tự động là quyền đang hoạt động.
- Dữ liệu đầu vào đã được kiểm tra độ mới và trạng thái thu thập; lỗi nguồn không được giải quyết bằng cách mặc định không có tài khoản.

Cần giữ dữ liệu quan sát gốc và thời điểm nguồn riêng để truy vết. Các cột trên chỉ là phần tối thiểu dùng trong ví dụ.

### 8.2. Đếm theo tài khoản thay vì theo dòng join

Truy vấn sau là SQL minh họa; `:report_id` là tham số do công cụ truy vấn truyền vào.

```sql
WITH per_account AS (
    SELECT
        a.report_id,
        a.account_key,
        a.account_type,
        a.enabled_state,
        a.owner_id,
        MAX(CASE
            WHEN p.grant_mode = 'STANDING' THEN 1 ELSE 0
        END) AS has_standing,
        MAX(CASE
            WHEN p.grant_mode = 'ELIGIBLE' THEN 1 ELSE 0
        END) AS has_eligible,
        MAX(CASE
            WHEN p.grant_mode = 'JIT_ACTIVE' THEN 1 ELSE 0
        END) AS has_jit_active
    FROM account_snapshot a
    JOIN privilege_path_snapshot p
      ON p.report_id = a.report_id
     AND p.account_key = a.account_key
    JOIN report_scope_snapshot s
      ON s.report_id = p.report_id
     AND s.scope_key = p.scope_key
    WHERE a.report_id = :report_id
      AND a.existence_state = 'PRESENT'
      AND p.valid_in_snapshot = TRUE
      AND p.resolution_state = 'RESOLVED'
      AND p.grant_mode IN ('STANDING', 'ELIGIBLE', 'JIT_ACTIVE')
      AND s.in_scope = TRUE
    GROUP BY
        a.report_id,
        a.account_key,
        a.account_type,
        a.enabled_state,
        a.owner_id
)
SELECT
    COUNT(*) AS inventory_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'ENABLED' THEN 1 ELSE 0
    END), 0) AS enabled_inventory_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'ENABLED'
         AND has_standing = 1 THEN 1 ELSE 0
    END), 0) AS standing_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'ENABLED'
         AND has_eligible = 1 THEN 1 ELSE 0
    END), 0) AS eligible_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'ENABLED'
         AND has_jit_active = 1 THEN 1 ELSE 0
    END), 0) AS jit_active_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'ENABLED'
         AND has_standing = 1
         AND has_jit_active = 1 THEN 1 ELSE 0
    END), 0) AS standing_and_jit_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'ENABLED'
         AND (has_standing = 1 OR has_jit_active = 1)
        THEN 1 ELSE 0
    END), 0) AS current_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'DISABLED' THEN 1 ELSE 0
    END), 0) AS disabled_privileged_accounts,
    COALESCE(SUM(CASE
        WHEN enabled_state = 'UNKNOWN' THEN 1 ELSE 0
    END), 0) AS unknown_state_accounts,
    COALESCE(SUM(CASE
        WHEN owner_id IS NULL THEN 1 ELSE 0
    END), 0) AS accounts_without_owner
FROM per_account;
```

Bước `per_account` đưa dữ liệu về đúng một dòng trên mỗi tài khoản. Vì thế tài khoản có mười đường quyền vẫn đóng góp một đơn vị vào tổng inventory.

`COALESCE` giúp tổng bằng không khi cohort hợp lệ nhưng không có dòng dữ liệu. Điều này chỉ có ý nghĩa sau khi xác nhận snapshot đã thu thập thành công; không dùng số không để che việc nguồn không chạy.

Trong ví dụ, `owner_id IS NULL` chỉ nhận diện dữ liệu thiếu chủ sở hữu. Để đánh giá chủ sở hữu còn hợp lệ hay đã nghỉ việc, cần đối chiếu nguồn vòng đời riêng và định nghĩa một chỉ số rõ hơn.

Các tài khoản chỉ có đường quyền chưa phân giải không đi vào `per_account`. Phải có một báo cáo riêng cho chúng, kèm số trường hợp chưa xác định trạng thái tồn tại, để tổng đã xác nhận không che phần thiếu chứng cứ.

### 8.3. Các lỗi truy vấn thường gặp

```sql
-- Không phải số tài khoản duy nhất:
SELECT COUNT(*)
FROM account_snapshot a
JOIN privilege_path_snapshot p
  ON p.account_key = a.account_key;
```

Truy vấn trên có hai vấn đề: một tài khoản bị nhân theo số đường quyền và các snapshot khác nhau có thể bị ghép chéo do thiếu `report_id`.

Một lỗi khác là dùng `COUNT(DISTINCT username)`. Cách này dễ gộp nhầm tài khoản local trên nhiều máy hoặc principal cùng tên ở nhiều tenant. Phải dùng khóa tài khoản đã chuẩn hóa.

Ngay cả `COUNT(DISTINCT account_key)` cũng chưa đủ nếu không lọc phạm vi, thời gian và trạng thái quan hệ quyền đúng với hợp đồng đo lường.

## 9. Chia nhỏ số liệu để điều hành PAM

### 9.1. Các chiều phân tích hữu ích

Tổng module hoặc toàn tổ chức nên cho phép xem theo:

- Môi trường: production, staging, development.
- Loại danh tính: human, non-human, unknown.
- Chế độ quyền: standing, eligible, JIT active.
- Mức độ nhạy cảm hoặc tầng quản trị của tài nguyên.
- Đơn vị chịu trách nhiệm.
- Tình trạng quản lý PAM đã định nghĩa.
- Tình trạng có chủ sở hữu và chu kỳ rà soát.

Không cần đưa mọi chiều vào một biểu đồ. Chọn chiều giúp người vận hành nhận ra tập tài khoản cần xử lý, chẳng hạn tài khoản dịch vụ standing ở production chưa có chủ sở hữu.

### 9.2. Tổng các nhóm có thể lớn hơn tổng duy nhất

Một tài khoản có thể có quyền ở cả production và staging. Khi xem từng môi trường, tài khoản đó có thể xuất hiện ở cả hai nhóm; tổng hai nhóm khi đó lớn hơn số tài khoản duy nhất toàn tổ chức.

Có hai cách trình bày hợp lệ:

1. Đếm theo phạm vi quyền, chấp nhận giao nhau và ghi rõ các nhóm không cộng được.
2. Gán mỗi tài khoản vào đúng một nhóm chính theo quy tắc công bố trước, dùng khi cần một biểu đồ cộng được.

Cách thứ hai chỉ là phân loại phục vụ báo cáo, không xóa các quan hệ quyền ở nhóm phụ. Nếu gán theo mức nhạy cảm cao nhất, phải giữ được bằng chứng tại sao tài khoản được đưa vào tầng đó.

### 9.3. Có trong vault chưa có nghĩa là được kiểm soát đầy đủ

Nếu theo dõi tỷ lệ tài khoản được PAM quản lý, cần định nghĩa thế nào là “được quản lý”:

- Chỉ đã đăng ký tài khoản?
- Credential có được kiểm soát theo chính sách?
- Luân chuyển có hoạt động theo yêu cầu?
- Truy cập có đi qua cơ chế phù hợp?
- Ngoại lệ có được phê duyệt và còn hạn?

Không suy từ một bản ghi vault sang kết luận đã đáp ứng mọi kiểm soát PAM. Với danh tính dùng credential ngắn hạn hoặc cơ chế xác thực khác, điều kiện quản lý có thể khác tài khoản dùng mật khẩu.

Chỉ số số tài khoản đặc quyền cung cấp tập đối tượng nền. Những chỉ số về độ bao phủ vault, luân chuyển, JIT hoặc ghi phiên cần định nghĩa riêng trên tập đó.

## 10. Đọc xu hướng mà không hiểu sai

### 10.1. Giải thích chênh lệch bằng các nhóm thay đổi

Một phép đối soát thực hành:

```text
Số cuối kỳ =
    Số đầu kỳ
    + tài khoản đặc quyền mới được tạo
    + tài khoản cũ mới được phát hiện
    + tài khoản được cấp đặc quyền lần đầu
    + tài khoản chuyển vào phạm vi
    - tài khoản bị xóa
    - tài khoản bị thu hồi quan hệ đặc quyền cuối cùng
    - tài khoản chuyển ra khỏi phạm vi
    + điều chỉnh định danh hoặc định nghĩa
```

Các nhóm phải được thiết kế để mỗi thay đổi chỉ được tính một lần. Ví dụ, tài khoản mới tạo rồi được phát hiện trong cùng kỳ phải được xếp vào một nhóm đối soát đã chọn, không cộng vừa “mới tạo” vừa “mới phát hiện”.

Việc disable một tài khoản không làm giảm `N_inventory` theo định nghĩa của bài nếu tài khoản vẫn tồn tại và còn quan hệ đặc quyền. Nó có thể làm giảm `N_current` khi dữ liệu trạng thái và quyền được cập nhật phù hợp.

### 10.2. Ví dụ số tăng nhưng khả năng quan sát tốt hơn

Giả sử đầu tháng có 180 tài khoản đặc quyền đã xác nhận. Trong tháng:

- Bổ sung nguồn khám phá giúp tìm thấy 60 tài khoản đã tồn tại từ trước.
- Có 8 tài khoản đặc quyền mới được tạo.
- Có 24 tài khoản bị xóa hoặc được thu hồi quan hệ đặc quyền cuối cùng.
- Không có thay đổi phạm vi và các nhóm biến động không chồng lấn.

Khi đó:

```text
N_inventory cuối tháng = 180 + 60 + 8 - 24 = 224
```

Không nên kết luận đội PAM làm tăng rủi ro chỉ vì tổng tăng từ 180 lên 224. Báo cáo cần cho thấy phần tăng do phát hiện thêm và phần giảm do xử lý thực tế.

Ngược lại, nếu tổng giảm mạnh vì connector directory không thu thập được, đó là suy giảm độ tin cậy dữ liệu chứ không phải kết quả least privilege.

### 10.3. Số lượng tài khoản không đo toàn bộ mức rủi ro

Giảm số tài khoản không tự động làm hệ thống an toàn hơn. Hợp nhất nhiều tài khoản cá nhân vào một tài khoản dùng chung có thể giảm số đếm nhưng làm suy yếu trách nhiệm cá nhân và tăng phạm vi ảnh hưởng.

Một tài khoản có quyền quản trị rất rộng có thể nguy hiểm hơn nhiều tài khoản có quyền giới hạn. Đánh giá cần kết hợp số lượng với phạm vi quyền, mức nhạy cảm, thời gian quyền tồn tại, chủ sở hữu và bằng chứng sử dụng.

Mục tiêu điều hành nên gắn với hành động cụ thể: thu hồi tài khoản không còn nhu cầu, giảm quyền standing không cần thiết, xử lý tài khoản không chủ và mở rộng kiểm kê. Không đặt mục tiêu “tổng tài khoản phải giảm mọi tháng” mà bỏ qua thay đổi quy mô hệ thống.

## 11. Dashboard và cảnh báo

### 11.1. Những thông tin nên xuất hiện cùng nhau

Một dashboard cơ bản có thể hiển thị:

```text
Snapshot: mốc thời gian báo cáo và phiên bản định nghĩa
Phạm vi: danh sách hoặc mã phạm vi đã chọn

Tài khoản đặc quyền đã xác nhận trong kiểm kê: 9
Trong đó enabled: 7 | disabled: 1 | unknown: 1

Enabled có quyền đang hoạt động theo mô hình: 6
Standing: 5 | JIT active: 1 | giao hai tập: 0
Eligible: 2, có thể chồng lấn với các tập trên

Nguồn thu thập: trạng thái hoàn tất và độ mới từng nguồn
Ngoại lệ dữ liệu: principal chưa ghép khóa, quyền chưa phân giải
```

Ví dụ này không bổ sung số ứng viên chưa phân giải giả định. Dashboard thực tế phải điền từ dữ liệu nguồn, kể cả bằng không sau khi đã xác minh nguồn đầy đủ.

Người xem cần biết giá trị nào là số tài khoản, giá trị nào là số bản ghi lỗi, và tổng nào có thể cộng được.

### 11.2. Số tài khoản tại snapshot là gauge

Số tài khoản có thể tăng hoặc giảm, nên là đại lượng biểu diễn trạng thái tại thời điểm đo. Nếu xuất sang hệ thống metrics, có thể dùng kiểu gauge.

Ví dụ tên và nhãn minh họa:

```text
# TYPE pam_privileged_accounts gauge
pam_privileged_accounts{scope="production",view="inventory"} 9
pam_privileged_accounts{scope="production",view="current"} 6
pam_privileged_accounts{scope="production",view="standing_enabled"} 5
pam_privileged_accounts{scope="production",view="eligible_enabled"} 2
pam_privileged_accounts{scope="production",view="jit_active_enabled"} 1
pam_privileged_accounts{scope="production",view="state_unknown"} 1
```

Các `view` giao nhau, vì vậy không cộng toàn bộ series để lấy tổng. Nếu hệ thống giám sát hoặc đội vận hành dễ tổng hợp nhầm, nên tách thành các tên metric rõ nghĩa hoặc công bố quy tắc truy vấn đi kèm.

Không đặt username, email, secret, token hoặc từng `account_key` vào nhãn. Chi tiết từng tài khoản nên nằm ở kho kiểm kê hoặc báo cáo có phân quyền; metrics tổng hợp chỉ cần các nhãn hữu hạn phục vụ điều hành.

Thời điểm thu thập và độ mới nguồn cần metric riêng. Một giá trị tổng hợp còn được exporter xuất ra không chứng minh dữ liệu nền vừa được cập nhật.

### 11.3. Cảnh báo cần xem cả dữ liệu và nghiệp vụ

Có thể xây cảnh báo cho:

- Tổng tăng bất thường trong một phạm vi nhạy cảm.
- Tài khoản standing mới xuất hiện ở tầng quản trị quan trọng.
- Tài khoản đặc quyền không có chủ sở hữu.
- Số tài khoản giảm đột ngột đồng thời nguồn thu thập bị lỗi.
- Nhóm unknown hoặc quyền chưa phân giải tăng.
- Dữ liệu nguồn quá hạn so với yêu cầu vận hành.

Ngưỡng phải dựa trên quy mô và nhịp thay đổi của tổ chức. Ví dụ mức tăng 10% chỉ là tín hiệu để điều tra nếu được tổ chức chọn; nó không tự xác định có sự cố.

Một cảnh báo số lượng nên dẫn tới danh sách chênh lệch tài khoản có quyền xem phù hợp và bằng chứng nguồn. Chỉ gửi con số tổng mà không chỉ ra đối tượng thay đổi sẽ làm người vận hành khó xử lý.

## 12. Bằng chứng và trách nhiệm vận hành

Để số liệu có thể phục vụ kiểm toán hoặc ứng phó sự cố, cần giữ được chuỗi truy nguyên:

```text
Giá trị trên báo cáo
    -> report_id và phiên bản định nghĩa
    -> tập account_key đóng góp vào giá trị
    -> quan hệ quyền và phạm vi
    -> bản ghi nguồn, thời điểm quan sát, trạng thái thu thập
```

Một gói bằng chứng có thể bao gồm:

- Mốc thời gian báo cáo và phiên bản danh mục đặc quyền.
- Phiên bản bộ phân giải, truy vấn hoặc cấu hình dùng để tính.
- Danh sách nguồn đã thu thập thành công và nguồn đang thiếu.
- Ánh xạ khử trùng cùng các trường hợp chưa giải quyết.
- Danh sách tài khoản đóng góp vào từng chỉ số, theo quyền truy cập báo cáo.
- Danh sách thay đổi so với kỳ trước và lý do đối soát.
- Người chịu trách nhiệm nguồn và người tiếp nhận hành động xử lý.

Không cần đưa credential hoặc secret vào bằng chứng để chứng minh một tài khoản đã được đếm. Dùng mã định danh và thông tin quan hệ đủ để kiểm tra, áp dụng quyền truy cập phù hợp cho dữ liệu danh tính.

Nên phân công rõ trách nhiệm: đội sở hữu nền tảng giải thích quyền thực tế; đội quản lý danh tính xác nhận vòng đời; đội PAM theo dõi biện pháp kiểm soát; đội dữ liệu duy trì phép tính và độ mới. Một con số thiếu chủ sở hữu vận hành thường không tạo ra hành động khắc phục bền vững.

## 13. Bài thực hành

### 13.1. Đề bài

Trong một phạm vi production, thu được các dữ kiện sau:

1. Tài khoản directory `mai-adm` xuất hiện ở hai nguồn, cùng định danh principal. Nó có standing trên bốn hệ thống.
2. Hai máy độc lập đều có tài khoản local `root`, enabled và standing.
3. Một tài khoản dịch vụ enabled có hai secret trong thời gian luân chuyển, quyền standing.
4. Một tài khoản nhà cung cấp enabled có eligible, chưa kích hoạt.
5. Một tài khoản break-glass enabled có standing, không có sự kiện đăng nhập trong kỳ.
6. Một tài khoản quản trị disabled vẫn còn membership cấp đặc quyền.
7. Một tài khoản enabled vừa có standing vừa có JIT đang hoạt động.

Hãy tính `N_inventory`, `N_current`, `N_standing`, `N_eligible`, `N_jit_active` và số tài khoản disabled còn quan hệ đặc quyền. Giả sử mọi principal đã có khóa chuẩn hóa, nguồn đầy đủ, không có trạng thái unknown và không có tài khoản nào khác.

### 13.2. Đáp án và giải thích

Tổng inventory:

```text
mai-adm                  1
root trên hai máy        2
tài khoản dịch vụ        1
nhà cung cấp eligible    1
break-glass              1
quản trị disabled        1
standing và JIT          1
--------------------------
N_inventory              8
```

Các tập còn lại:

```text
N_standing               = 6
N_eligible               = 1
N_jit_active             = 1
N_standing_and_jit_active = 1
N_current                = 6 + 1 - 1 = 6
N_disabled_privileged    = 1
```

Sáu tài khoản standing enabled gồm `mai-adm`, hai `root`, tài khoản dịch vụ, break-glass và tài khoản vừa standing vừa JIT. Tài khoản JIT đã nằm trong tập standing nên không làm tăng số tài khoản current.

Hai secret không tạo thành hai tài khoản. Không có đăng nhập của break-glass không làm mất đặc quyền. Tài khoản nhà cung cấp chỉ eligible được tính trong inventory nhưng chưa đi vào current.

### 13.3. Câu hỏi mở rộng

- Nếu một nguồn mất kết nối, vì sao không thể lập tức kết luận tài khoản của nguồn đó đã bị xóa?
- Nếu một tài khoản có quyền ở hai môi trường, làm thế nào giải thích việc tổng các cột môi trường lớn hơn tổng duy nhất?
- Khi chuyển từ standing sang JIT, chỉ số nào có thể giảm trong khi inventory không đổi?
- Nếu giảm số tài khoản bằng cách chuyển sang tài khoản dùng chung, cần đánh giá thêm những yếu tố nào?

Câu trả lời cần gắn với đơn vị đếm, mốc thời gian, phạm vi quyền và độ tin cậy dữ liệu. Một báo cáo PAM hữu ích không chỉ trả lời “có bao nhiêu”, mà còn cho phép truy ra tài khoản nào được đếm, vì sao được đếm và thay đổi nào cần người chịu trách nhiệm xử lý.
