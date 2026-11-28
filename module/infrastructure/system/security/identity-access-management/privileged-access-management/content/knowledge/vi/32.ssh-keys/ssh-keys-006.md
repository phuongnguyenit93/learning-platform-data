# Known hosts control: kiểm soát danh tính máy chủ SSH trong PAM

## 1. Mục tiêu và phạm vi

Khi mở một phiên SSH đặc quyền, người vận hành thường chú ý tới câu hỏi “ai được phép đăng nhập?”. Tuy nhiên, còn một câu hỏi phải được trả lời trước: **client có đang kết nối tới đúng máy chủ được phê duyệt hay không?**

Known hosts control là cách tổ chức thiết lập, phân phối, kiểm tra và thu hồi niềm tin đối với danh tính máy chủ SSH. Trong Privileged Access Management (PAM), kiểm soát này bảo vệ phiên quản trị khỏi việc đi nhầm đích hoặc chấp nhận máy chủ giả mạo, đồng thời tạo bằng chứng cho quá trình cấp và sử dụng quyền đặc biệt.

Sau bài học, bạn có thể:

- Phân biệt host key của máy chủ với key dùng để xác thực người dùng.
- Giải thích ý nghĩa của `known_hosts`, fingerprint, host certificate và các marker tin cậy.
- Thiết lập quy trình đưa host key vào trust store bằng kênh xác minh độc lập.
- Áp dụng chính sách kiểm tra host key cho máy quản trị, bastion, PAM proxy và tác vụ tự động.
- Xử lý thay đổi key, thay máy và sự cố mà không làm mất kiểm soát danh tính đích.
- Xác định bằng chứng cần lưu cho kiểm toán và ứng phó sự cố.

Bài học dùng tên host minh họa thuộc `pam.example`. Các đoạn cấu hình giả định client OpenSSH; PAM gateway hoặc thư viện SSH có thể có giao diện và khả năng khác. Cần kiểm tra cấu hình thực tế của thành phần khởi tạo từng kết nối.

## 2. Hai chiều xác thực của một kết nối SSH

Một kết nối SSH có hai vấn đề danh tính khác nhau:

| Chiều xác thực | Câu hỏi | Thành phần liên quan |
|---|---|---|
| Client xác thực server | Đây có đúng là máy chủ cần quản trị? | Host key, host certificate, trust store của client |
| Server xác thực client | Người dùng hoặc dịch vụ này có được đăng nhập? | User key, user certificate, mật khẩu, MFA, chính sách tài khoản |

Private host key thuộc về máy chủ SSH. Trong quá trình thiết lập kết nối, server chứng minh khả năng sử dụng key đó theo giao thức. Client đối chiếu danh tính nhận được với nguồn tin cậy của mình.

Private key của người dùng lại thuộc về người hoặc dịch vụ đăng nhập. Public key trong `authorized_keys` hoặc cơ chế user certificate hỗ trợ server xác thực client. Đưa public key người dùng vào `known_hosts` không thay thế được kiểm tra host key; đưa host key vào `authorized_keys` cũng không tạo ra chính sách known hosts đúng.

Một thứ tự tư duy hữu ích là:

```text
Xác định đích dự kiến
        |
        v
Thiết lập kết nối và xác thực danh tính server
        |
        v
Xác thực tài khoản người dùng hoặc dịch vụ
        |
        v
Áp dụng quyền, thực hiện thao tác, ghi nhận phiên
```

Mã hóa đường truyền không tự chứng minh rằng đầu bên kia là máy chủ bạn định truy cập. Nếu client chấp nhận key của một server giả mạo, đường truyền vẫn có thể được mã hóa nhưng tới sai bên.

Tương tự, vault có thể cấp credential đúng hạn, JIT có thể giới hạn thời gian và session recording có thể ghi đầy đủ thao tác. Những cơ chế đó không bù được việc PAM proxy bỏ qua kiểm tra danh tính server.

## 3. Host key, fingerprint và trust store

### 3.1. Host key là tài sản cần quản lý

Một máy chủ có thể sở hữu nhiều host key ứng với các thuật toán khác nhau. Tùy cấu hình và khả năng hai phía, phiên kết nối sẽ chọn một phương án phù hợp.

Không nên đồng nhất:

- **Host key**: public/private key pair dùng cho danh tính server.
- **Fingerprint**: biểu diễn ngắn được tính từ public key để đối chiếu.
- **Tên host**: tên logic mà client dùng để chọn đích và tra trust.
- **Địa chỉ IP**: địa chỉ mạng tại thời điểm kết nối.
- **Tài sản**: thực thể được quản lý với owner, môi trường và vòng đời.

Một fingerprint trùng khớp chỉ có ý nghĩa sau khi tổ chức đã ràng buộc fingerprint đó với đúng tài sản bằng nguồn đáng tin cậy.

### 3.2. Các vị trí known hosts thường gặp

Với OpenSSH, các vị trí thường dùng gồm:

- `~/.ssh/known_hosts`: trust store theo người dùng.
- `/etc/ssh/ssh_known_hosts`: trust store dùng chung ở cấp hệ thống.
- Đường dẫn riêng được cấu hình qua `UserKnownHostsFile` hoặc `GlobalKnownHostsFile`.

Tên file không quyết định độ tin cậy. Cần kiểm soát ai có thể sửa file, file được phân phối từ đâu và ứng dụng nào thực sự đọc file đó.

Trong môi trường PAM, trust store nằm trong container của proxy có thể khác hoàn toàn trust store trên laptop của quản trị viên. File được mount vào image mới cũng có thể khác file đang dùng bởi phiên bản proxy hiện hành.

### 3.3. Dạng bản ghi

Một bản ghi thông thường có cấu trúc:

```text
[marker] host-patterns key-type public-key [comment]
```

Ví dụ minh họa, phần public key trong dấu ngoặc nhọn phải được thay bằng key thực:

```text
db01.pam.example ssh-ed25519 <PUBLIC_KEY_BASE64> asset=db01 environment=prod
[db01.pam.example]:2222 ssh-ed25519 <PUBLIC_KEY_BASE64> asset=db01 endpoint=admin-2222
```

Với cổng không mặc định, tên dùng trong known hosts thường có dạng `[hostname]:port`. Bản ghi cho cổng 22 không tự biểu đạt một endpoint trên cổng 2222.

Một bản ghi có thể chứa danh sách tên phân tách bằng dấu phẩy hoặc pattern theo cú pháp hỗ trợ. Chỉ thêm alias sau khi đã xác minh chúng thực sự trỏ tới cùng danh tính được phép. Tránh ràng buộc key bằng pattern quá rộng chỉ để giảm công việc vận hành.

Comment giúp người đọc nhận diện nhưng không thay cho kho inventory và quy trình phê duyệt. Việc ghi `environment=prod` trong comment không khiến SSH tự thực thi ranh giới môi trường.

### 3.4. Marker đặc biệt

| Marker | Ý nghĩa | Kiểm soát đi kèm |
|---|---|---|
| Không có marker | Pin một public host key cho tên hoặc pattern tương ứng | Phải quản lý thêm, đổi và bỏ key |
| `@cert-authority` | Tin CA dùng để xác minh host certificate trong phạm vi tên phù hợp | Bảo vệ CA, giới hạn phạm vi và kiểm soát cấp chứng thư |
| `@revoked` | Đánh dấu key bị thu hồi để client từ chối khi cơ chế kiểm tra áp dụng | Phân phối cập nhật đầy đủ và kiểm thử tình huống bị thu hồi |

Trust store có thể chứa nhiều nguồn tin cậy. Chỉ thêm một CA không tự loại bỏ những raw host key đã được pin ở nơi khác. Nếu chính sách bắt buộc host certificate, phải rà soát các đường tin cậy thay thế và xác nhận kiểu danh tính thực sự được chấp nhận.

### 3.5. Hash tên host

`HashKnownHosts yes` giúp các mục mới do client lưu không biểu lộ trực tiếp tên host trong file. Nó không mã hóa public key, không biến nguồn key không tin cậy thành nguồn tin cậy và không thay thế kiểm tra host key.

Đặt tùy chọn này cũng không tự chuyển đổi toàn bộ bản ghi có sẵn. Muốn hash file đã tồn tại, cần một bước chuyển đổi có kiểm soát. Công cụ chuyển đổi có thể tạo bản sao chứa tên chưa hash; bản sao đó cũng cần được bảo vệ theo vòng đời dữ liệu.

Để tìm entry kể cả khi tên đã được hash, dùng:

```bash
ssh-keygen -F db01.pam.example -f /etc/pam/ssh_known_hosts
ssh-keygen -F '[db01.pam.example]:2222' -f /etc/pam/ssh_known_hosts
```

Hash tên chủ yếu giảm việc lộ danh sách đích nếu file bị đọc trái phép. Độ tin cậy danh tính vẫn phụ thuộc vào quy trình đưa key vào và quyền sửa trust store.

## 4. Mô hình đe dọa của một phiên quản trị

Các tình huống cần xét gồm:

1. DNS hoặc tuyến mạng dẫn client tới máy khác.
2. Bastion hoặc PAM proxy kết nối nhầm môi trường do alias dùng chung.
3. Server bị rebuild nhưng quy trình cấp phát không tạo yêu cầu cập nhật trust.
4. Nhiều máy được clone từ image chứa cùng private host key.
5. Private host key bị lấy cắp và được dùng để giả mạo server.
6. Pipeline tự động bỏ qua mọi cảnh báo để tránh tác vụ bị treo.
7. Người vận hành xóa entry cũ ngay khi thấy “host identification has changed”.

Known hosts control giúp phát hiện key không được tin cậy hoặc không khớp với niềm tin hiện có. Nó không tự xác định nguyên nhân của sự khác biệt. Một key thay đổi có thể là hoạt động được phê duyệt, sai cấu hình hoặc tấn công; cần điều tra bằng dữ liệu độc lập.

Cũng cần hiểu giới hạn: nếu kẻ tấn công có private host key vẫn đang được tin, pin public key cũ không đủ để phân biệt server giả. Khi đó phải thu hồi niềm tin, thay key và xử lý phạm vi lộ lọt. Nếu server thật đã bị chiếm quyền, danh tính SSH hợp lệ cũng không chứng minh hệ điều hành còn an toàn.

## 5. Ràng buộc danh tính trước khi đưa key vào sử dụng

Một bản ghi quản trị nên mô tả ít nhất:

| Thuộc tính | Ví dụ | Mục đích |
|---|---|---|
| Asset ID | `asset-prod-db-01` | Tránh phụ thuộc hoàn toàn vào DNS |
| Owner | Nhóm nền tảng dữ liệu | Có bên chịu trách nhiệm xác minh |
| Môi trường | Production | Xác định ranh giới trust |
| Endpoint | `db01.pam.example:22` | Ràng buộc tên và cổng |
| Phương thức trust | Pin host key | Biết quy trình cập nhật phù hợp |
| Loại key và fingerprint | `ssh-ed25519`, `SHA256:…` | Đối chiếu đúng từng key |
| Nguồn xác minh | Console quản trị đã kiểm soát | Giải thích vì sao key được tin |
| Bản thay đổi | `CHG-2048` | Liên kết với phê duyệt |
| Phiên bản trust store | `pam-trust-prod-017` | Biết phiên nào dùng tập trust nào |
| Vòng đời | Đang dùng, chờ bỏ, đã thu hồi | Hỗ trợ rotation và điều tra |

Không lưu private host key trong inventory này. Fingerprint không phải secret đăng nhập, nhưng mapping tài sản và tuyến quản trị vẫn có thể là thông tin nội bộ cần giới hạn quyền đọc.

Nếu cùng một key xuất hiện trên nhiều server không liên quan, phải xác định đó là thiết kế được chấp thuận hay lỗi clone. Chia sẻ private host key làm tăng phạm vi ảnh hưởng khi một bản sao bị lộ và làm giảm khả năng phân biệt từng máy.

## 6. Bootstrap: xác minh key lần đầu

### 6.1. Trust on first use có giới hạn

Ở lần kết nối đầu, client có thể hỏi người dùng có tin key vừa nhận được không. Nếu người dùng đối chiếu fingerprint qua nguồn độc lập đáng tin rồi chấp thuận, thao tác này có thể là một phần của quy trình bootstrap.

Nếu chỉ nhập `yes` vì “đây là lần đầu”, tổ chức đang đặt niềm tin vào đường mạng tại thời điểm đó. Cách này không đáp ứng yêu cầu xác minh mạnh cho một đích quản trị nhạy cảm.

Với PAM production, nên bootstrap trust trước khi cho phép phiên đặc quyền đầu tiên. Lỗi thiếu trust phải trở thành yêu cầu onboarding, không phải lý do để tắt kiểm tra.

### 6.2. Nguồn xác minh độc lập

Một số nguồn có thể dùng nếu đã nằm trong quy trình tin cậy:

- Console của hệ thống quản lý máy ảo hoặc máy chủ vật lý có kiểm soát truy cập.
- Quy trình provisioning xuất public host key kèm danh tính tài sản.
- Hệ thống quản lý cấu hình có kênh xác thực và quyền thay đổi được kiểm soát.
- Owner xác nhận fingerprint lấy từ máy đích qua kênh quản trị độc lập đã được xác thực.

“Độc lập” không có nghĩa chỉ mở một cửa sổ terminal khác trên cùng tuyến chưa tin cậy. Lấy key từ cùng đường mạng rồi lấy fingerprint từ chính kết quả đó không tạo ra hai nguồn xác minh.

### 6.3. Ví dụ thu thập và đối chiếu

Thu thập một candidate key:

```bash
ssh-keyscan -T 5 -p 22 -t ed25519 db01.pam.example > /tmp/db01-hostkey.candidate
ssh-keygen -lf /tmp/db01-hostkey.candidate -E sha256
```

`ssh-keyscan` lấy public key mà endpoint cung cấp. Nó không xác thực rằng endpoint đó thuộc đúng tài sản cần quản trị. Vì vậy, file candidate phải được xem là dữ liệu chưa tin cậy.

Từ console tin cậy của đúng máy đích, lấy fingerprint của public host key đang được cấu hình sử dụng, ví dụ:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub -E sha256
```

Đối chiếu loại key, fingerprint, tài sản, tên và cổng. Nếu server dùng đường dẫn host key khác, phải lấy đúng public key tương ứng thay vì giả định file mặc định luôn là key đang hoạt động.

Nếu candidate rỗng, thiếu thuật toán dự kiến hoặc có nhiều kết quả không giải thích được, dừng onboarding để xác minh. Không dùng việc đổi thuật toán hoặc bỏ kiểm tra như một cách làm cho phép thử thành công.

Sau khi đối chiếu và phê duyệt, đưa public key đã xác minh vào bản trust store được quản lý. Tránh chạy chuỗi “scan rồi append thẳng vào production”, vì chuỗi đó bỏ qua bước quyết định có nên tin key hay không.

### 6.4. Quy trình onboarding đầy đủ

```text
Yêu cầu thêm endpoint và owner
            |
            v
Thu thập candidate key + xác minh độc lập
            |
            v
Review mapping tài sản, tên, cổng, môi trường
            |
            v
Tạo phiên bản trust store được phê duyệt
            |
            v
Phân phối tới client/PAM proxy thực sự kết nối
            |
            v
Kiểm thử thành công và kiểm thử key sai bị chặn
            |
            v
Cho phép sử dụng phiên đặc quyền
```

Bằng chứng onboarding phải trả lời được: ai xác minh, xác minh từ đâu, key nào được chấp thuận và những client nào đã nhận phiên bản đó.

## 7. Chính sách client cho phiên đặc quyền

### 7.1. Ý nghĩa của StrictHostKeyChecking

| Giá trị | Hành vi tổng quát với host mới | Khi host key đã biết bị thay đổi | Cách dùng trong PAM |
|---|---|---|---|
| `yes` | Từ chối nếu chưa có trust phù hợp | Từ chối thay đổi không được tin | Phù hợp khi trust được quản lý trước |
| `ask` | Hỏi người dùng khi cần chấp thuận | Không tự chấp nhận key đã thay đổi | Chỉ dùng trong bootstrap có hướng dẫn xác minh |
| `accept-new` | Tự chấp nhận key của host chưa biết | Từ chối key đã biết bị thay đổi | Vẫn có rủi ro lần đầu; không tương đương pre-approval |
| `no` hoặc `off` | Cho phép nhiều trường hợp không có trust trước | Có thể cho kết nối tiếp với các hạn chế tùy trường hợp | Không phù hợp làm chính sách xác minh đích đặc quyền |

`accept-new` có ích trong một số mô hình vận hành nhưng không giải quyết việc xác minh lần đầu. Không nên trình bày nó như chính sách production đã xác minh mạnh chỉ vì nó chặn thay đổi về sau.

`BatchMode yes` hỗ trợ tránh các prompt xác thực tương tác trong tự động hóa; nó không phải một chính sách host trust. Cần cấu hình rõ `StrictHostKeyChecking` thay vì suy ra hành vi xác minh server từ `BatchMode`.

### 7.2. Ví dụ pinning cho client được quản lý

```sshconfig
Host pam-db01-prod
    HostName db01.pam.example
    Port 22
    User pam-operator
    StrictHostKeyChecking yes
    UserKnownHostsFile /etc/pam/ssh_known_hosts
    GlobalKnownHostsFile /etc/ssh/ssh_known_hosts
    UpdateHostKeys no
    BatchMode yes
```

Trong ví dụ:

- Trust store riêng của PAM được cung cấp tại `/etc/pam/ssh_known_hosts`.
- Trust store toàn cục vẫn được khai báo, nên các entry ở đó cũng phải được quản lý theo cùng phạm vi chính sách.
- `UpdateHostKeys no` thể hiện quyết định chỉ cập nhật trust qua quy trình phân phối tập trung.
- Alias `pam-db01-prod` là tên gọi trong cấu hình; cần xác nhận tên thực sự dùng để tra host key, nhất là khi có `HostKeyAlias`, canonicalization hoặc cấu hình khác.

Nếu tổ chức chỉ cho phép một tập trust duy nhất, cần cấu hình và kiểm thử để loại bỏ các nguồn bổ sung ngoài chính sách. Đặt tên một file “managed” không khiến những file khác tự ngừng có hiệu lực.

Có thể xem cấu hình đã được client tổng hợp:

```bash
ssh -G pam-db01-prod
```

Kiểm tra ít nhất `hostname`, `port`, `stricthostkeychecking`, `userknownhostsfile`, `globalknownhostsfile`, `hostkeyalias`, `proxyjump` và `updatehostkeys` nếu có. Kết quả này cho biết cấu hình hiệu lực, không thay thế thử nghiệm kết nối và kiểm tra key thực sự được nhận.

Cấu hình ở file hệ thống có thể không phải ranh giới bắt buộc nếu người dùng còn được chạy client riêng hoặc truyền tùy chọn khác. Với yêu cầu cưỡng chế, PAM proxy hoặc runner được quản lý phải kiểm soát cả chương trình, cấu hình, trust store và đường egress cho phiên được cấp quyền.

### 7.3. Quyền trên trust store

Trust store được quản lý tập trung cần có owner và quyền sửa phù hợp. Tài khoản mở phiên đặc quyền không nên đồng thời có quyền tùy ý thay tập key mà proxy sử dụng.

Trong container hoặc runner, có thể mount trust store ở chế độ chỉ đọc đối với tiến trình SSH. Tuy nhiên, cần quản lý cả quyền thay image, manifest triển khai, cấu hình mount và nguồn phân phối file. Chỉ đọc ở một lớp không ngăn được bên có quyền thay toàn bộ workload.

Không cần coi public host key là bí mật giống credential. Mục tiêu quan trọng của quyền file là bảo vệ tính toàn vẹn và giới hạn việc lộ mapping nội bộ khi cần.

## 8. Bastion, ProxyJump và PAM session proxy

Một luồng quản trị có thể gồm nhiều kết nối SSH:

```text
Máy quản trị -- SSH A --> Bastion
      |
      +----- SSH B qua kênh chuyển tiếp -----> Máy đích
```

Với OpenSSH `ProxyJump`, client thường xác thực riêng host của bastion và host của máy đích; kết nối đích đi qua chuyển tiếp không có nghĩa danh tính đích đã được bastion xác minh thay.

Ví dụ cấu hình minh họa:

```sshconfig
Host pam-bastion-prod
    HostName bastion01.pam.example
    User pam-entry
    StrictHostKeyChecking yes
    UserKnownHostsFile /etc/pam/ssh_known_hosts
    GlobalKnownHostsFile /etc/ssh/ssh_known_hosts
    UpdateHostKeys no
    BatchMode yes

Host pam-db01-via-bastion
    HostName db01.pam.example
    User pam-operator
    ProxyJump pam-bastion-prod
    StrictHostKeyChecking yes
    UserKnownHostsFile /etc/pam/ssh_known_hosts
    GlobalKnownHostsFile /etc/ssh/ssh_known_hosts
    UpdateHostKeys no
    BatchMode yes
```

Cần có trust đúng cho cả `bastion01.pam.example` và `db01.pam.example`, đồng thời kiểm thử cấu hình riêng của từng host.

Với PAM session proxy có cơ chế kết thúc và tạo lại phiên, luồng khác đi:

```text
Người dùng -- phiên vào --> PAM gateway -- SSH ra --> Máy đích
                                 |
                                 +--> Trust store dùng cho kết nối SSH ra
```

Ở đây, trust store trên laptop không tự bảo vệ kết nối từ gateway tới đích. Phải xác định ai khởi tạo SSH ra, thành phần đó xác minh gì và log lỗi nằm ở đâu.

Một ma trận trách nhiệm nên ghi rõ:

| Chặng | Bên xác minh danh tính server | Trust cần quản lý |
|---|---|---|
| Người dùng tới bastion SSH | Client người dùng | Host key hoặc CA của bastion |
| OpenSSH client tới đích qua ProxyJump | Client khởi tạo kết nối đích | Host key hoặc CA của đích |
| PAM gateway tạo phiên SSH ra | SSH stack của gateway | Trust của gateway đối với đích |
| Runner tự động tới bastion hoặc đích | Client trong runner | Trust store đúng phiên bản của runner |

Không nên kết luận toàn bộ luồng đã an toàn chỉ từ một phép thử SSH thành công trên laptop.

## 9. Host certificate và CA

Khi có nhiều server hoặc tài sản thay đổi nhanh, pin từng raw host key có thể tạo chi phí cập nhật lớn. SSH host certificate cho phép client tin một CA có thẩm quyền cấp danh tính server trong phạm vi được xác định.

Ví dụ bản ghi trust, với public key CA thực thay cho placeholder:

```text
@cert-authority *.pam.example ssh-ed25519 <HOST_CA_PUBLIC_KEY_BASE64> host-ca=prod
```

Client vẫn phải xác minh chứng thư hợp lệ cho tên đích, chữ ký CA, thời hạn và các điều kiện liên quan. Pattern của bản ghi CA là phạm vi tin cậy ở client; nó không thay cho việc cấp đúng principal trong certificate.

Ví dụ: nếu server xuất trình certificate cho `db02.pam.example`, việc CA được tin cho `*.pam.example` không tự làm certificate đó hợp lệ cho tên `db01.pam.example`.

Có thể xem thông tin một certificate được cung cấp để review:

```bash
ssh-keygen -L -f ssh_host_ed25519_key-cert.pub
```

Lệnh hiển thị thông tin chứng thư; người review vẫn cần đối chiếu issuer, principal, thời hạn và chính sách cấp với nguồn quản lý CA. Đọc được certificate không đồng nghĩa đã chứng minh endpoint mạng đang giữ private key tương ứng.

Các kiểm soát quan trọng:

- Tách phạm vi CA cho production và môi trường thử nghiệm khi chính sách yêu cầu.
- Cấp principal theo danh tính tài sản đã được xác minh.
- Bảo vệ private key CA ở mức tương xứng với số lượng host mà CA có thể xác nhận.
- Giới hạn quyền yêu cầu và phê duyệt cấp certificate.
- Quản lý thời hạn, đồng bộ thời gian và quy trình cấp lại.
- Có cơ chế thu hồi được client thực sự hỗ trợ và nhận cập nhật.

Host CA xác thực **server**. User CA xác thực **người đăng nhập**. Hai vai trò cần được phân biệt cả về key, chính sách và bằng chứng.

Certificate ngắn hạn giảm khoảng thời gian một certificate có thể được sử dụng, nhưng không thay thế xử lý ngay khi private key hoặc CA bị lộ.

## 10. DNS, IP, alias và endpoint động

### 10.1. DNS đổi không nhất thiết host key đổi

IP có thể đổi trong khi cùng một máy chủ tiếp tục giữ key. Ngược lại, cùng một IP có thể được gán cho máy mới với key mới.

Vì vậy, không coi IP là bằng chứng duy nhất về danh tính. Khi phân tích mismatch, phải liên kết DNS, tuyến mạng, asset ID và vòng đời cấp phát.

Một số cấu hình còn kiểm tra hoặc lưu thông tin IP bên cạnh hostname. Hành vi này chịu ảnh hưởng bởi tùy chọn như `CheckHostIP` và mô hình kết nối. Cần xem cấu hình thực tế, không giả định mọi client đều kiểm tra cùng một tập tên/IP.

### 10.2. Alias phải có ý nghĩa ổn định

Nếu một alias dùng cho production hôm nay nhưng staging ngày mai, trust có thể tiếp tục trỏ tới một ngữ cảnh đã sai.

`HostKeyAlias` có thể hữu ích khi cần một tên tra trust ổn định hoặc phân biệt endpoint sau port forwarding. Nhưng alias cũng thay đổi danh tính tên mà client dùng để tra cứu và kiểm tra host certificate. Chỉ dùng khi đã thiết kế mapping rõ và kiểm thử principal tương ứng.

Không gán chung một alias host key cho nhiều đích độc lập để “hết lỗi known hosts”.

### 10.3. Load balancer và máy dùng ngắn hạn

Nếu cùng tên DNS dẫn tới nhiều server có key khác nhau, việc mỗi phiên nhận một key mới có thể là kết quả thiết kế chứ không phải lỗi client. Cần chọn mô hình danh tính phù hợp:

- Quản lý và phê duyệt tập key riêng của các backend.
- Dùng host certificate với principal đúng cho tên dịch vụ theo chính sách.
- Tạo endpoint quản trị riêng ổn định cho từng tài sản.

Không giải quyết bằng cách tắt kiểm tra hoặc phát tán một private host key dùng chung ngoài kiểm soát. Với hạ tầng dùng ngắn hạn, quy trình provisioning phải gắn danh tính SSH với tài sản mới trước khi mở quyền quản trị.

## 11. Rotation có kế hoạch

### 11.1. Pinning theo quy trình tập trung

Một quy trình đổi host key thông thường có thể gồm:

1. Xác nhận yêu cầu thay đổi, owner và danh sách client bị ảnh hưởng.
2. Tạo hoặc cấp key mới trên server theo quy trình được phê duyệt.
3. Xác minh public key mới qua kênh độc lập.
4. Phân phối trust có cả key cũ và key mới trong giai đoạn chuyển tiếp có giới hạn.
5. Triển khai cấu hình server sử dụng key mới và kiểm tra thuật toán thực sự được thương lượng.
6. Xác nhận các proxy, runner và máy quản trị liên quan đã kết nối bằng danh tính mới.
7. Bỏ trust cũ theo thời hạn; nếu có dấu hiệu lộ key, áp dụng thu hồi phù hợp.
8. Lưu kết quả triển khai, phạm vi còn lỗi và bằng chứng kết thúc thay đổi.

Chỉ thêm key mới ở server không đảm bảo client đã chọn key đó; server có nhiều key và client có chính sách thuật toán riêng. Phép kiểm tra cần xác nhận key hoặc certificate thực sự được dùng, không chỉ exit code của phiên.

Trong rotation thường lệ, rollback có thể được thiết kế trước. Khi key cũ đã bị xác nhận lộ, rollback sang key cũ không còn là phương án phục hồi an toàn.

### 11.2. Vai trò của UpdateHostKeys

OpenSSH có cơ chế `UpdateHostKeys` hỗ trợ học các host key bổ sung từ server sau khi server đã được xác thực, khi hai phía và điều kiện cấu hình hỗ trợ.

Cơ chế này có thể hỗ trợ rotation, nhưng:

- Không phải cách xác minh độc lập host chưa từng được tin.
- Không chứng minh hệ thống vẫn an toàn khi private key đang được tin đã bị lộ.
- Phụ thuộc vào hỗ trợ phía server, cách xác thực host và khả năng cập nhật trust store phía client.
- Có thể xung đột với mô hình trust store chỉ đọc và cập nhật qua release tập trung.

Vì vậy, lựa chọn bật hay tắt phải là quyết định thiết kế. Nếu dùng, hãy kiểm thử trên đúng phiên bản client/server và mô hình trust hiện hành, đồng thời làm rõ key học thêm có được ghi nhận, review và phân phối tới các client khác hay không.

## 12. Thu hồi và xử lý cảnh báo thay đổi key

### 12.1. Cảnh báo là điểm dừng để xác minh

Khi thấy cảnh báo dạng “REMOTE HOST IDENTIFICATION HAS CHANGED”, không nên suy ra ngay rằng server bị tấn công, cũng không nên suy ra đó chỉ là rebuild bình thường.

Một runbook phù hợp:

1. Dừng phiên kết nối lỗi và ghi nhận thời gian, đích, client, proxy cùng mã tương quan.
2. Xác định trust store thực sự được dùng và entry nào đang khớp tên/cổng.
3. Kiểm tra có thay đổi đã được phê duyệt, rebuild, đổi tuyến hoặc đổi DNS không.
4. Đối chiếu key vừa nhận với key trên đúng tài sản qua kênh độc lập.
5. Đánh giá khả năng lộ host key, sai endpoint hoặc sai cấu hình proxy.
6. Chỉ cập nhật trust sau khi kết luận và phê duyệt theo quy trình.
7. Kiểm tra lại kết nối, phạm vi client và bằng chứng đóng sự kiện.

Lệnh tra cứu phục vụ điều tra:

```bash
ssh-keygen -F db01.pam.example -f /etc/pam/ssh_known_hosts
ssh-keygen -F '[db01.pam.example]:2222' -f /etc/pam/ssh_known_hosts
```

Không xóa mù quáng “dòng lỗi” trong mọi file known hosts. Cùng một đích có thể xuất hiện ở trust store người dùng, trust store hệ thống hoặc nguồn động được client cấu hình thêm.

### 12.2. Vì sao ssh-keygen -R không phải biện pháp xác minh

`ssh-keygen -R` xóa entry khớp một tên khỏi file được chỉ định. Nó không kiểm tra key mới có thuộc máy chủ đúng hay không.

Trong một bản sao staging của trust store, sau khi thay đổi đã được xác minh và cần bỏ entry cũ, có thể dùng:

```bash
ssh-keygen -R db01.pam.example -f ./ssh_known_hosts.staging
```

Sau đó cần bổ sung đúng key đã được phê duyệt, review diff, kiểm thử và phân phối bản mới. Lệnh xóa có thể loại bỏ các entry khớp khác của tên đó, nên phải xem toàn bộ kết quả thay đổi.

Đặc biệt, xóa entry rồi kết nối lại bằng chế độ tự chấp nhận host mới sẽ xóa mất rào cản mà không tạo bằng chứng tin cậy mới.

### 12.3. Bỏ trust và thu hồi là hai việc khác nhau

Xóa key khỏi một file có thể khiến lần kết nối sau bị coi là host chưa biết. Nếu một nguồn khác vẫn tin key đó hoặc client cho phép tự thêm host mới, việc xóa chưa bảo đảm key sẽ bị từ chối.

Thu hồi có mục tiêu rõ hơn: key hoặc certificate không còn được chấp nhận ngay cả khi nó từng có mặt trong tập trust. Có thể dùng các cơ chế phù hợp như marker `@revoked` hoặc danh sách thu hồi được cấu hình qua `RevokedHostKeys` ở client hỗ trợ.

Với certificate, cần thiết kế thu hồi đúng đối tượng: key host, certificate cụ thể hoặc CA theo phạm vi sự cố. Không giả định mọi sản phẩm PAM hỗ trợ đầy đủ cùng định dạng hoặc cách phân phối danh sách thu hồi.

Sau cập nhật, phải kiểm thử cả hai chiều:

- Danh tính hợp lệ hiện hành vẫn kết nối được.
- Danh tính đã thu hồi thực sự bị chặn trên các client thuộc phạm vi.

Nếu CA bị lộ, đổi key cho một server không giải quyết toàn bộ sự cố. Cần xử lý niềm tin vào CA, phạm vi chứng thư có thể bị cấp trái phép và phân phối trust mới.

## 13. Tự động hóa và CI/CD

Tác vụ tự động không có người quan sát prompt, nên trust cần được chuẩn bị trước khi job chạy.

Một mô hình phù hợp:

```text
Nguồn inventory + key đã xác minh
               |
               v
Review và tạo release trust store
               |
               v
Artifact có phiên bản và bảo vệ tính toàn vẹn
               |
               v
Runner/PAM proxy nạp đúng phiên bản
               |
               v
SSH với chính sách kiểm tra nghiêm ngặt
               |
               v
Log kết quả + phiên bản trust + đích thực tế
```

Các yêu cầu vận hành quan trọng:

- Job không lấy candidate từ mạng rồi tự chuyển candidate thành trust trong cùng bước.
- Người sửa logic deployment không mặc nhiên có quyền bỏ qua phê duyệt trust của production.
- File được cung cấp trước khi SSH chạy, với quyền hạn phù hợp.
- Runner mới được tạo không phụ thuộc vào known hosts vô tình còn sót ở máy cũ.
- Phiên bản image và phiên bản trust store được ghi nhận đủ để tái hiện.
- Khi thiếu trust hoặc key sai, job dừng với lỗi có thể phân loại.

Không dùng `StrictHostKeyChecking=no`, `UserKnownHostsFile=/dev/null` hoặc cơ chế “tin tất cả host” trong thư viện để sửa lỗi pipeline. Nếu policy yêu cầu pre-approval, `accept-new` cũng chưa đáp ứng yêu cầu đó.

Với thư viện SSH, cần tìm API xác minh host key tương đương, xác định trust source và kiểm thử mismatch. Có file known hosts trong image không chứng minh thư viện đã sử dụng file ấy.

## 14. Bằng chứng và khả năng kiểm toán

Một sự kiện kiểm soát host trust nên liên kết được với phiên PAM và thay đổi cấu hình. Ví dụ schema ghi nhận nội bộ:

```json
{
  "event_type": "ssh_host_identity_check",
  "session_id": "pam-session-4821",
  "asset_id": "asset-prod-db-01",
  "requested_host": "db01.pam.example",
  "requested_port": 22,
  "connection_origin": "pam-proxy-prod-02",
  "trust_mode": "pinned_host_key",
  "key_type": "ssh-ed25519",
  "observed_fingerprint": "SHA256:<fingerprint>",
  "trust_store_version": "pam-trust-prod-017",
  "result": "matched",
  "change_reference": "CHG-2048"
}
```

Đây là schema minh họa cho hệ thống thu thập của tổ chức, không phải khẳng định OpenSSH tự xuất sẵn bản ghi JSON như vậy. Có thể cần kết hợp log client, inventory, log proxy và metadata triển khai.

Các bằng chứng cần có theo vòng đời:

| Sự kiện | Bằng chứng chính |
|---|---|
| Onboarding | Nguồn xác minh độc lập, fingerprint, owner, phê duyệt |
| Phân phối trust | Phiên bản, phạm vi client, kết quả triển khai |
| Kết nối | Đích yêu cầu, origin, kết quả kiểm tra, phiên PAM |
| Rotation | Key cũ/mới, kế hoạch chuyển tiếp, kết quả kiểm thử |
| Thu hồi | Lý do, phạm vi, thời điểm phân phối và phép thử từ chối |
| Ngoại lệ | Người chịu trách nhiệm, thời hạn, biện pháp kiểm soát được phê duyệt |

Nếu bật log SSH chi tiết để chẩn đoán, giới hạn thời gian thu thập, quyền đọc và dữ liệu chia sẻ. Không đưa private key, mật khẩu hoặc dữ liệu nhạy cảm của phiên vào báo cáo trust.

Chỉ số vận hành nên phân biệt host chưa onboarding, mismatch, trust store cũ và certificate hết hạn. Một tỷ lệ kết nối thành công cao không có ý nghĩa nếu client đang bỏ qua kiểm tra.

## 15. Tình huống thực tế: database production được rebuild

Nhóm hạ tầng rebuild `db01.pam.example` sau bảo trì. DNS vẫn giữ nguyên, nhưng máy mới sinh host key khác. PAM proxy từ chối phiên quản trị; một kỹ sư đề nghị xóa known hosts trên mọi proxy.

Phân tích:

- Mismatch cho thấy kiểm soát đang phát hiện thay đổi danh tính.
- DNS không đổi không chứng minh key mới đã được phê duyệt.
- Cần đối chiếu asset mới, yêu cầu rebuild và fingerprint từ console tin cậy.
- Xóa entry hàng loạt sẽ phá liên kết với key cũ mà chưa thiết lập liên kết đáng tin với key mới.

Cách xử lý:

1. Gắn sự kiện mismatch với yêu cầu rebuild và xác nhận đúng tài sản.
2. Lấy fingerprint key mới qua console quản trị đã kiểm soát.
3. Review mapping tên/cổng, cập nhật trust trong release có phiên bản.
4. Phân phối tới toàn bộ proxy có khả năng nhận phiên cho tài sản này.
5. Kiểm thử kết nối hợp lệ và thử key không được phê duyệt trong môi trường kiểm thử.
6. Bỏ trust cũ hoặc thu hồi theo chính sách vòng đời và mức rủi ro.
7. Lưu bằng chứng, rồi bổ sung bước trust onboarding vào quy trình rebuild.

Nếu không tìm thấy yêu cầu rebuild hợp lệ hoặc fingerprint không khớp nguồn độc lập, xử lý như sự kiện cần điều tra. Không cấp một ngoại lệ rộng để khôi phục khả năng đăng nhập trước khi biết mình đang đăng nhập vào đâu.

## 16. Bài thực hành có kiểm soát

Thực hiện trong lab với client và server riêng. Dùng tài khoản thử nghiệm, không dùng credential quản trị production và không thay host key của máy đang phục vụ người dùng.

### Phần A — Host chưa được tin

- Chuẩn bị client với trust store lab tách biệt và `StrictHostKeyChecking yes`.
- Kết nối tới server chưa có entry.
- Kết quả mong đợi: client không hoàn tất kết nối tới host chưa được tin.
- Ghi nhận lỗi để phân biệt với lỗi quyền tài khoản.

### Phần B — Bootstrap đúng

- Thu thập candidate key.
- Lấy fingerprint từ console lab độc lập.
- Đối chiếu và thêm key đã xác minh vào trust store lab.
- Kết nối lại với tài khoản hợp lệ.

Kết quả mong đợi: kiểm tra danh tính server vượt qua; đăng nhập chỉ thành công nếu xác thực người dùng cũng hợp lệ.

### Phần C — Host key thay đổi

- Giữ client và trust store như cũ.
- Dùng một endpoint lab được chuẩn bị với host key khác cho cùng tên/cổng thử nghiệm.
- Kết nối lại và quan sát mismatch.
- Xác nhận quy trình không tự xóa entry hoặc tự chấp nhận key mới.

### Phần D — Kiểm tra từng chặng

- Tạo luồng qua bastion.
- Làm sai trust của bastion trong bản cấu hình lab và xác nhận bị chặn.
- Khôi phục trust bastion, làm sai trust đích và xác nhận kết nối đích bị chặn.
- Chứng minh hai phép thử tạo lỗi ở hai vị trí khác nhau.

### Phần E — Rotation hoặc certificate

Tùy mô hình lab, thực hiện một trong hai nhánh:

- Pinning: phân phối key mới đã xác minh, chuyển server sang key mới, xác nhận key cũ không còn được chấp nhận theo chính sách.
- Certificate: kiểm thử certificate đúng principal và còn hạn được chấp nhận; certificate sai principal hoặc không còn hiệu lực bị từ chối.

Nếu dùng thu hồi, bổ sung phép thử key/certificate đã thu hồi bị từ chối. Lưu phiên bản trust store, cấu hình hiệu lực và kết quả cho từng trường hợp.

Tiêu chí hoàn thành không chỉ là “SSH chạy được”. Bài thực hành đạt yêu cầu khi bạn chứng minh được cả kết nối đúng được cho phép và danh tính sai bị chặn.

## 17. Lỗi thường gặp và câu hỏi tự kiểm tra

| Lỗi | Hệ quả | Hướng xử lý |
|---|---|---|
| Scan rồi tự động thêm vào trust | Chấp nhận danh tính chưa xác minh | Đối chiếu qua nguồn độc lập trước khi phê duyệt |
| Tin lần đầu chỉ bằng thao tác nhập yes | Không biết key thuộc tài sản nào | Bootstrap có owner và bằng chứng |
| Chỉ cấu hình laptop | Kết nối SSH từ proxy vẫn có thể bỏ kiểm tra | Kiểm soát đúng thành phần khởi tạo từng chặng |
| Bỏ qua cổng hoặc alias | Tra sai entry, cập nhật sai đích | Review cấu hình hiệu lực và tên tra trust |
| Dùng chung private host key do clone image | Mở rộng phạm vi giả mạo khi lộ key | Sinh danh tính riêng hoặc thiết kế certificate phù hợp |
| Xóa entry khi có cảnh báo | Mất pinning mà chưa có trust mới | Điều tra và cập nhật bằng change đã xác minh |
| Thêm CA nhưng giữ các trust ngoài chính sách | Vẫn có đường chấp nhận danh tính không mong muốn | Rà soát toàn bộ nguồn trust và kiểm thử |
| Chỉ kiểm thử đường thành công | Không chứng minh key sai bị từ chối | Bổ sung unknown, mismatch, hết hạn, sai principal và thu hồi |
| Có file trust nhưng ứng dụng không đọc | Cảm giác kiểm soát sai | Xác nhận API, cấu hình và hành vi thực tế |

Tự kiểm tra:

1. Vì sao public key được lấy bằng `ssh-keyscan` chưa đủ để cho phép một phiên PAM production?
2. Vì sao key người dùng trong vault không thay thế được host key verification?
3. Khi dùng ProxyJump, client cần tin những danh tính server nào?
4. Khi PAM gateway tạo kết nối SSH ra, trust store nào quyết định danh tính đích?
5. Vì sao `accept-new` không tương đương danh sách host đã được phê duyệt?
6. Nếu máy được rebuild và giữ nguyên DNS, những bằng chứng nào cần có trước khi cập nhật trust?
7. Khi host CA bị lộ, vì sao chỉ đổi host key của một server chưa đủ?
8. Vì sao xóa key khỏi một file chưa chắc khiến key đó bị từ chối ở mọi client?
9. Bạn sẽ kiểm thử thế nào để chứng minh một trust store mới vẫn cho phép host hợp lệ và chặn host giả?

Trong một hệ thống PAM được quản lý tốt, danh tính máy chủ là đầu vào được phê duyệt trước khi quyền đặc biệt được sử dụng. Known hosts control nối danh tính đó với cấu hình client thực tế, vòng đời tài sản và bằng chứng của từng phiên quản trị.

