# Xác thực HTTPS bằng token và trình quản lý thông tin đăng nhập

Khi làm việc với repository từ xa qua HTTPS, Git cần xác thực người dùng trước khi thực hiện các thao tác như `clone`, `fetch` hoặc `push` vào repository riêng tư. Nhiều dịch vụ Git không còn chấp nhận mật khẩu tài khoản cho thao tác Git qua HTTPS; thay vào đó, người dùng cần dùng personal access token (PAT), OAuth hoặc một cơ chế xác thực do nhà cung cấp hỗ trợ.

Token có thể được nhập khi Git hỏi thông tin đăng nhập, nhưng không nên phải nhập lại ở mỗi lần thao tác. Trình quản lý thông tin đăng nhập (credential manager) giúp lưu và cung cấp thông tin xác thực thông qua kho bảo mật của hệ điều hành. Khi phối hợp đúng, nhóm có thể dùng HTTPS thuận tiện mà vẫn kiểm soát thời hạn, quyền hạn và vòng đời của token.

Trong dịch vụ quản lý mã nguồn Git, bảo vệ thông tin xác thực là một phần của bảo mật repository. Token có quyền ghi có thể cho phép người khác thay đổi mã nguồn, tạo release hoặc truy cập dữ liệu riêng tư. Vì vậy, cần cấp quyền tối thiểu, lưu token đúng nơi, tránh đưa token vào URL hoặc file cấu hình và thu hồi ngay khi nghi ngờ bị lộ.

## 1. Xác thực HTTPS trong Git hoạt động như thế nào?

Khi remote dùng URL HTTPS, Git giao tiếp với dịch vụ Git qua HTTPS. Nếu repository yêu cầu xác thực, máy chủ yêu cầu credential. Tùy dịch vụ, credential có thể gồm tên người dùng và PAT, OAuth token hoặc một cơ chế xác thực tương thích khác.

Ví dụ remote HTTPS:

```bash
git remote -v
git remote add origin https://github.com/example-team/payment-service.git
```

Khi chạy `git fetch origin` hoặc `git push origin main`, Git có thể yêu cầu thông tin đăng nhập. Với dịch vụ dùng PAT cho HTTPS:

- Username thường là tên tài khoản trên dịch vụ Git.
- Password được nhập là PAT, không phải mật khẩu đăng nhập tài khoản.

Một số nhà cung cấp dùng OAuth thông qua trình duyệt và credential manager; khi đó người dùng đăng nhập qua trang xác thực của nhà cung cấp và không cần tự tạo PAT. Hãy theo cơ chế được dịch vụ Git của tổ chức hỗ trợ.

### Vì sao không dùng mật khẩu tài khoản?

Token cho phép cấp quyền và thời hạn riêng cho hoạt động Git. Nếu token bị lộ, ta có thể thu hồi token đó mà không cần đổi mật khẩu tài khoản. Một PAT có thể chỉ được phép đọc một số repository, trong khi token khác có quyền ghi cho một nhóm dự án. Cách cấp quyền này giúp giới hạn tác động khi thông tin xác thực bị lộ.

Không phải dịch vụ nào cũng có cùng chính sách token. Có nơi dùng fine-grained PAT, có nơi dùng token theo nhóm hoặc deploy token, có nơi ưu tiên OAuth. Cần đọc chính sách của nhà cung cấp và tổ chức trước khi tạo token.

## 2. Personal access token là gì?

Personal access token (PAT) là chuỗi bí mật đại diện cho một danh tính người dùng hoặc ứng dụng khi truy cập dịch vụ Git. PAT thường được cấu hình với các thuộc tính:

- **Phạm vi (scope/permissions):** quyền đọc repository, ghi repository, quản lý workflow, package hoặc các tài nguyên khác.
- **Repository access:** toàn bộ repository hoặc chỉ những repository được chọn, tùy nhà cung cấp.
- **Thời hạn:** ngày hết hạn hoặc thời gian sống do chính sách tổ chức quy định.
- **Chủ sở hữu:** tài khoản người dùng, nhóm hoặc service identity phát hành token.
- **Trạng thái:** đang hoạt động, hết hạn, bị thu hồi hoặc bị giới hạn bởi chính sách bảo mật.

PAT là bí mật tương đương một thông tin xác thực. Ai có token và quyền phù hợp có thể thực hiện các thao tác trong phạm vi token được cấp. Không gửi token qua chat, email, issue, pull request, ảnh chụp màn hình hoặc tài liệu hướng dẫn.

### Chọn quyền tối thiểu

Trước khi tạo PAT, xác định thao tác cần thực hiện:

| Nhu cầu | Quyền nên cân nhắc |
| --- | --- |
| Clone hoặc fetch repository riêng tư | Quyền đọc repository cần thiết |
| Push commit lên repository | Quyền đọc và ghi nội dung repository |
| Tải package riêng tư | Quyền đọc package tương ứng |
| Publish package | Quyền ghi package tương ứng |
| Chạy hoặc quản lý workflow | Chỉ cấp quyền workflow nếu thực sự cần |

Tên quyền cụ thể khác nhau giữa GitHub, GitLab, Azure DevOps và máy chủ Git nội bộ. Không chọn toàn bộ quyền chỉ để tránh lỗi xác thực. Nếu push thất bại do thiếu quyền, xác định đúng quyền cần bổ sung thay vì cấp quyền quản trị rộng.

### Thời hạn và luân chuyển token

Ưu tiên token có thời hạn phù hợp với nhu cầu và chính sách tổ chức. Token dùng cho một tác vụ ngắn nên có thời gian sống ngắn; token dài hạn cần có chủ sở hữu, lịch luân chuyển và quy trình thu hồi rõ ràng.

Khi tạo token mới để thay token cũ:

1. Tạo token mới với quyền tối thiểu và thời hạn phù hợp.
2. Cập nhật credential manager hoặc secret store của môi trường liên quan.
3. Kiểm tra `fetch`/`push` hoặc tác vụ CI bằng token mới.
4. Thu hồi token cũ sau khi xác nhận các nơi dùng đã chuyển đổi.

Không để token hết hạn bất ngờ làm gián đoạn pipeline hoặc công việc nhóm. Theo dõi ngày hết hạn và thông báo luân chuyển theo quy trình nội bộ.

## 3. Trình quản lý thông tin đăng nhập là gì?

Git hỗ trợ credential helper để trao đổi thông tin xác thực với một chương trình bên ngoài. Khi dịch vụ yêu cầu đăng nhập, Git hỏi helper xem đã có credential phù hợp chưa. Nếu chưa, Git có thể hỏi người dùng; sau khi xác thực thành công, helper có thể lưu thông tin để lần sau dùng lại.

Credential helper có thể được cấu hình ở nhiều dạng:

| Helper | Cách lưu | Nhận xét |
| --- | --- | --- |
| Git Credential Manager (`manager`) | Tích hợp kho bảo mật của hệ điều hành và luồng OAuth của nhà cung cấp được hỗ trợ | Lựa chọn thuận tiện cho nhiều môi trường desktop và dịch vụ Git phổ biến |
| `osxkeychain` | macOS Keychain | Dùng kho thông tin xác thực của macOS |
| `libsecret` | Secret Service trên Linux | Cần môi trường/kho secret tương thích |
| `cache` | Bộ nhớ tạm trong một khoảng thời gian | Không lưu lâu dài; hết thời gian sẽ hỏi lại |
| `store` | File văn bản trên đĩa | Có thể lưu credential dạng rõ; không phù hợp để giữ PAT nhạy cảm |

Không nên nhầm credential helper với việc lưu token trong remote URL hoặc file cấu hình. Helper được thiết kế để cung cấp credential khi cần, còn token nhúng trong URL có thể xuất hiện trong `.git/config`, log, lịch sử shell hoặc đầu ra chẩn đoán.

## 4. Git Credential Manager (GCM)

Git Credential Manager là credential helper đa nền tảng dành cho Git. GCM có thể tích hợp với nhà cung cấp Git để thực hiện đăng nhập qua trình duyệt/OAuth hoặc xử lý thông tin xác thực theo cơ chế được hỗ trợ, sau đó lưu thông tin trong kho bảo mật của hệ điều hành.

Các kho lưu trữ thường gặp:

- Windows: Windows Credential Manager.
- macOS: Keychain.
- Linux: Secret Service/libsecret hoặc backend bảo mật phù hợp với môi trường.

Backend cụ thể phụ thuộc phiên bản GCM, hệ điều hành và cấu hình. Nếu môi trường Linux không có secret service khả dụng, hãy thiết lập backend được hỗ trợ hoặc dùng cơ chế xác thực do tổ chức phê duyệt; tránh chuyển sang lưu PAT dạng rõ để xử lý nhanh.

### Kiểm tra GCM

```bash
git credential-manager --version
```

Nếu lệnh không tồn tại, GCM có thể chưa được cài hoặc chưa nằm trong PATH. Một số bản cũ dùng tên lệnh `git-credential-manager-core`; tên lệnh phụ thuộc phiên bản đang cài.

### Cấu hình GCM làm credential helper

Trên các bản GCM hiện đại:

```bash
git credential-manager configure
```

Lệnh này cấu hình Git tích hợp với GCM. Trong một số môi trường đã cài sẵn GCM, có thể đặt helper trực tiếp:

```bash
git config --global credential.helper manager
```

Kiểm tra cấu hình:

```bash
git config --show-origin --get-all credential.helper
```

Không nên cấu hình nhiều helper một cách tùy tiện. Git có thể gọi lần lượt các helper được khai báo; một helper cũ có thể tiếp tục trả về credential sai hoặc lưu credential ở nơi không mong muốn. Hãy kiểm tra toàn bộ giá trị và nguồn cấu hình trước khi thay đổi.

### Đăng nhập lần đầu

Sau khi cấu hình GCM, dùng remote HTTPS bình thường:

```bash
git remote set-url origin https://github.com/example-team/payment-service.git
git fetch origin
```

Nếu nhà cung cấp hỗ trợ OAuth qua GCM, trình duyệt có thể mở để người dùng đăng nhập và cấp quyền. Nếu nhà cung cấp yêu cầu PAT, nhập username theo hướng dẫn và dán PAT vào trường password khi được hỏi. Không ghi PAT vào lệnh hoặc URL.

Sau khi xác thực thành công, GCM lưu credential trong kho bảo mật tương ứng. Lần `fetch` hoặc `push` tiếp theo thường không cần nhập lại cho đến khi credential hết hạn, bị thu hồi hoặc chính sách yêu cầu xác thực lại.

## 5. Dùng PAT với remote HTTPS

Ví dụ quy trình tổng quát khi nhà cung cấp yêu cầu PAT:

### Bước 1: Tạo PAT trên dịch vụ Git

Mở trang quản lý token của nhà cung cấp và tạo token theo hướng dẫn của tổ chức. Chọn:

- Repository hoặc nhóm repository cần truy cập.
- Quyền đọc/ghi tối thiểu cho công việc.
- Thời hạn hợp lý.
- SSO hoặc phê duyệt tổ chức nếu nhà cung cấp yêu cầu.

Nhiều dịch vụ chỉ hiển thị token đầy đủ một lần khi tạo. Sao chép token trực tiếp vào nơi nhập an toàn hoặc để credential manager mở luồng xác thực; không lưu tạm trong file văn bản hay clipboard dùng chung.

### Bước 2: Xác nhận remote không chứa token

```bash
git remote -v
```

URL nên có dạng:

```text
https://github.com/example-team/payment-service.git
```

Không dùng dạng nhúng bí mật như:

```text
https://USERNAME:TOKEN@github.com/example-team/payment-service.git
```

URL có token có thể được ghi vào cấu hình repository, log CI, shell history hoặc thông tin chẩn đoán. Nếu token đã từng được nhúng vào URL, hãy xóa khỏi cấu hình và thu hồi token đó vì nó có thể đã bị lưu ở nơi khác.

### Bước 3: Thực hiện thao tác yêu cầu xác thực

```bash
git fetch origin
```

Nếu Git hỏi username và password, nhập username tài khoản và dùng PAT ở trường password. Nếu GCM mở trình duyệt, hoàn tất luồng đăng nhập theo nhà cung cấp. Không gửi PAT vào tham số dòng lệnh.

### Bước 4: Kiểm tra thao tác

```bash
git status -sb
git fetch origin
```

Nếu cần quyền ghi, kiểm tra bằng một thao tác push được phép theo quy trình nhóm, chẳng hạn push nhánh tính năng đã commit. Không tạo commit hoặc push thử lên nhánh được bảo vệ chỉ để kiểm tra credential.

## 6. Các credential helper khác

GCM thường là lựa chọn tốt cho máy developer có hỗ trợ backend bảo mật. Một số môi trường có thể dùng helper khác.

### macOS Keychain

```bash
git config --global credential.helper osxkeychain
```

Git dùng Keychain để lưu và lấy credential. Người dùng có thể quản lý hoặc xóa mục liên quan trong ứng dụng Keychain Access theo chính sách của máy.

### Linux Secret Service/libsecret

Nếu Git được cài kèm helper `libsecret`, có thể cấu hình:

```bash
git config --global credential.helper /usr/lib/git-core/git-credential-libsecret
```

Đường dẫn thực tế thay đổi theo bản phân phối và cách cài Git. Kiểm tra helper đã có trên máy và dùng đúng đường dẫn được cung cấp bởi gói cài đặt. Backend thường cần một Secret Service khả dụng, chẳng hạn keyring của môi trường desktop.

### Credential cache

```bash
git config --global credential.helper 'cache --timeout=3600'
```

Cache giữ credential trong bộ nhớ trong 3.600 giây. Sau thời gian đó Git có thể hỏi lại. Đây là lựa chọn tạm thời, không phải kho lưu trữ lâu dài. Không đặt timeout quá dài nếu chính sách bảo mật yêu cầu thời gian ngắn.

### Credential store

```bash
git config --global credential.helper store
```

Helper `store` có thể ghi credential vào file như `~/.git-credentials` ở dạng văn bản rõ. Bất kỳ tiến trình hoặc người dùng nào có quyền đọc file đều có thể lấy token. Không sử dụng `store` để lưu PAT nhạy cảm trên máy dùng chung hoặc môi trường không được bảo vệ. Nếu đã lưu token theo cách này, chuyển sang helper an toàn và thu hồi/luân chuyển token theo chính sách tổ chức.

## 7. Phân biệt credential helper với cấu hình username

Git có thể lưu username mặc định riêng với credential helper:

```bash
git config --global credential.username developer
```

Thiết lập này chỉ gợi ý username; nó không lưu PAT và không cấp quyền truy cập. Có thể giới hạn username cho một host bằng cấu hình URL-specific nếu làm việc với nhiều tài khoản. Cần kiểm tra cú pháp URL và cấu hình theo tài liệu Git trước khi áp dụng.

Khi có nhiều tài khoản trên cùng host, Git có thể dùng credential đã lưu cho host đó. Có thể yêu cầu Git phân biệt credential theo đường dẫn repository:

```bash
git config --global credential.useHttpPath true
```

Khi bật `useHttpPath`, Git đưa path vào ngữ cảnh credential thay vì chỉ dùng protocol và host. Điều này có thể hữu ích khi cùng host phục vụ nhiều repository hoặc nhiều danh tính, nhưng hành vi lưu trữ còn phụ thuộc credential helper và chính sách nhà cung cấp. Không bật tùy chọn này chỉ để che giấu việc đang dùng sai tài khoản; trước hết hãy kiểm tra credential đang lưu và đăng nhập lại đúng danh tính.

## 8. Quản lý và thu hồi credential

Khi credential hết hạn, bị thu hồi hoặc dùng sai tài khoản, Git có thể liên tục hỏi lại hoặc nhận lỗi xác thực. Cần xóa credential cũ khỏi helper rồi xác thực lại.

Git có giao thức để yêu cầu helper quên credential theo ngữ cảnh. Ví dụ trên shell POSIX, có thể gửi host cần xóa mà không đưa token vào câu lệnh:

```bash
printf "protocol=https\nhost=github.com\n\n" | git credential reject
```

Thao tác này yêu cầu helper xóa credential phù hợp với host đó; kết quả phụ thuộc helper và ngữ cảnh credential. Nếu dùng GCM, cũng có thể xóa tài khoản/credential của host trong giao diện quản lý tài khoản hoặc kho bảo mật của hệ điều hành. Với Windows, kiểm tra Windows Credential Manager; với macOS, kiểm tra Keychain Access; với Linux, kiểm tra Secret Service/keyring hoặc backend đang cấu hình.

Sau khi xóa credential cũ, chạy lại:

```bash
git fetch origin
```

Git sẽ yêu cầu xác thực lại hoặc mở luồng đăng nhập. Đảm bảo token mới có đúng repository access, scope và thời hạn.

### Khi nào phải thu hồi token ngay?

Thu hồi token ngay nếu:

- Token xuất hiện trong commit, issue, pull request, log hoặc URL remote.
- Token được gửi nhầm qua chat/email hoặc chia sẻ cho người không được phép.
- Thiết bị chứa token bị mất hoặc tài khoản có dấu hiệu bị xâm nhập.
- Không còn xác định được token đang được dùng ở đâu hoặc ai quản lý nó.

Sau khi thu hồi:

1. Kiểm tra log hoạt động của dịch vụ Git để tìm truy cập bất thường.
2. Tạo token thay thế với quyền tối thiểu nếu công việc vẫn cần.
3. Cập nhật credential manager và secret store của CI.
4. Xóa token khỏi nơi lưu trữ đang kiểm soát và xử lý lịch sử Git nếu token từng được commit.
5. Kiểm tra fork, clone, cache, log và artifact có thể đã chứa token.

Xóa token khỏi commit mới không làm token cũ mất hiệu lực. Việc đầu tiên luôn là thu hồi token ở nhà cung cấp; viết lại lịch sử chỉ là bước xử lý phần dấu vết còn lại.

## 9. Không nhúng token vào URL, script hoặc cấu hình

Không sử dụng các cách sau:

```bash
# Không làm: token xuất hiện trong URL và có thể bị ghi vào config/log
git remote set-url origin https://user:token@example.com/team/repo.git

# Không làm: token nằm trực tiếp trong lệnh hoặc script
git clone https://TOKEN@example.com/team/repo.git
```

Không đặt token trong:

- `.git/config`, `.gitmodules`, `.git-credentials` hoặc file cấu hình được commit.
- Shell history, script build, Dockerfile hoặc file manifest.
- Log CI, output debug, thông báo lỗi hoặc URL được in ra.
- Biến môi trường không được bảo vệ hoặc artifact có thể tải công khai.

Với pipeline, dùng secret store của CI/CD và cơ chế cấp credential ngắn hạn nếu nhà cung cấp hỗ trợ. Tránh in biến secret ra log. Chỉ cấp quyền cho repository và thao tác cần thiết; tách token read-only dùng để checkout khỏi token có quyền publish nếu pipeline có cả hai giai đoạn.

## 10. Dùng HTTPS token trong CI/CD

Máy CI thường chạy không có người dùng tương tác để nhập token. Vì vậy, credential phải được cung cấp qua secret store hoặc identity federation được nhà cung cấp hỗ trợ.

Quy trình tổng quát:

1. Tạo secret hoặc kết nối service identity trong hệ thống CI.
2. Giới hạn quyền theo repository và thao tác.
3. Cấp secret vào bước cần truy cập Git qua cơ chế bảo mật của CI.
4. Dùng remote HTTPS không chứa token.
5. Chạy fetch/clone/push theo quyền đã cấp.
6. Không echo secret, không bật debug chứa header xác thực và không lưu credential vào workspace lâu dài.
7. Thu hồi hoặc xoay vòng credential theo lịch và khi pipeline không còn cần.

Ví dụ minh họa cấu hình remote:

```bash
git remote set-url origin https://github.com/example-team/payment-service.git
git fetch origin
```

Token được cấp bởi secret store cho helper hoặc cơ chế xác thực của runner, không được ghép trực tiếp vào URL. Cách ánh xạ secret vào Git phụ thuộc nền tảng CI; hãy dùng action/plugin chính thức hoặc tài liệu của nhà cung cấp để tránh ghi token ra log.

Nếu CI chỉ cần clone/fetch, dùng credential read-only. Nếu bước phát hành cần push tag hoặc cập nhật repository, tách credential có quyền ghi và chỉ cấp cho job đáng tin cậy. Không dùng PAT cá nhân dài hạn của developer làm credential mặc định cho pipeline.

## 11. So sánh HTTPS token và SSH key

Git có thể truy cập remote qua HTTPS hoặc SSH. Hai phương thức có mô hình xác thực khác nhau:

| Tiêu chí | HTTPS + token/OAuth | SSH key |
| --- | --- | --- |
| Thông tin xác thực | PAT, OAuth hoặc credential được nhà cung cấp hỗ trợ | Cặp khóa riêng và khóa công khai |
| Quản lý | Credential manager hoặc secret store | SSH agent, keychain hoặc secret store |
| Thu hồi | Thu hồi token theo tài khoản/ứng dụng | Xóa/revoke public key đã đăng ký hoặc thay key |
| Phạm vi quyền | Có thể giới hạn theo scope/repository tùy nhà cung cấp | Thường gắn với danh tính/key; quyền repository do dịch vụ Git quyết định |
| Tự động hóa | Dễ tích hợp với secret store và OAuth flow | Phù hợp với deploy key hoặc SSH identity được quản lý |

HTTPS token thuận tiện khi tổ chức đã chuẩn hóa OAuth/GCM hoặc cần token có scope và thời hạn. SSH phù hợp khi nhóm có quy trình quản lý key rõ ràng. Không có phương thức nào an toàn nếu bí mật bị lưu trong repository hoặc cấp quyền quá rộng.

## 12. Lỗi xác thực thường gặp

| Lỗi | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `Authentication failed` | PAT sai, hết hạn, bị thu hồi hoặc username không đúng | Kiểm tra trạng thái token, xóa credential cũ rồi xác thực lại |
| `Repository not found` dù URL đúng | Tài khoản/token không có quyền đọc repository riêng tư | Kiểm tra repository access, tổ chức và SSO authorization |
| Fetch được nhưng push bị từ chối | Token chỉ có quyền đọc hoặc nhánh bị bảo vệ | Kiểm tra quyền ghi và quy trình pull request của nhóm |
| Git hỏi credential ở mỗi lần thao tác | Chưa cấu hình helper, helper không lưu được hoặc backend không khả dụng | Kiểm tra `credential.helper`, cài/cấu hình GCM hoặc backend bảo mật |
| GCM không mở trình duyệt | Thiếu browser, môi trường headless hoặc provider flow không hỗ trợ | Dùng phương thức xác thực được hỗ trợ cho môi trường đó; không chuyển sang lưu token rõ |
| Đăng nhập nhầm tài khoản | Helper đang trả credential cũ cho cùng host | Xóa credential cũ trong helper/kho hệ điều hành rồi đăng nhập đúng tài khoản |
| CI clone được nhưng push thất bại | Secret thiếu quyền ghi hoặc job không được cấp secret | Cấp đúng quyền cho job đáng tin cậy và kiểm tra chính sách bảo vệ nhánh |
| Token bị lộ trong URL/log | Credential được nhúng trực tiếp vào lệnh hoặc cấu hình | Thu hồi token, kiểm tra log/history và cấp token mới an toàn |

Một số lệnh kiểm tra cấu hình không tiết lộ giá trị token:

```bash
git remote -v
git config --show-origin --get-all credential.helper
git config --show-origin --get credential.useHttpPath
git credential-manager --version
```

Không dùng lệnh hoặc chế độ debug có thể in credential đầy đủ ra terminal hoặc log. Nếu cần chẩn đoán, che mọi giá trị bí mật trước khi chia sẻ kết quả.

## 13. Quy trình thiết lập an toàn cho máy developer

Thực hiện trên repository thử nghiệm hoặc repository mà tài khoản của bạn được phép truy cập:

1. Cài Git và Git Credential Manager tương thích với hệ điều hành.
2. Chạy `git credential-manager configure` hoặc cấu hình helper `manager` theo phiên bản đang dùng.
3. Kiểm tra `git config --show-origin --get-all credential.helper`.
4. Xác nhận remote HTTPS không chứa username/token.
5. Dùng `git fetch origin` để khởi tạo luồng đăng nhập.
6. Nếu dịch vụ yêu cầu PAT, tạo token có quyền tối thiểu và thời hạn phù hợp; nhập vào prompt an toàn.
7. Xác nhận lần fetch tiếp theo không yêu cầu nhập lại credential khi token còn hiệu lực.
8. Kiểm tra nơi lưu credential bằng kho bảo mật của hệ điều hành.
9. Thử xóa credential theo host trong môi trường thử nghiệm rồi xác thực lại.
10. Ghi nhận quy trình luân chuyển và thu hồi token theo chính sách nhóm.

## 14. Checklist bảo mật token và credential manager

Trước khi sử dụng token:

- Token chỉ có scope/repository access cần thiết.
- Token có thời hạn và chủ sở hữu rõ ràng.
- Tổ chức đã phê duyệt token hoặc SSO nếu cần.
- Remote URL không chứa thông tin bí mật.

Khi lưu credential:

- Dùng GCM hoặc kho bảo mật được tổ chức phê duyệt.
- Tránh `credential.helper store` cho PAT nhạy cảm.
- Không commit file chứa token hoặc cấu hình cá nhân.
- Không in credential ra terminal, log hoặc báo cáo lỗi.

Khi token không còn dùng hoặc có nguy cơ lộ:

- Thu hồi ở dịch vụ Git.
- Xóa credential khỏi helper/kho hệ điều hành.
- Cập nhật secret store và pipeline liên quan.
- Kiểm tra log hoạt động và xử lý lịch sử nếu token từng được commit.

## 15. Thực hành

Thực hiện trên tài khoản và repository thử nghiệm:

1. Kiểm tra phiên bản Git và GCM bằng `git --version` và `git credential-manager --version`.
2. Cấu hình GCM bằng `git credential-manager configure`.
3. Tạo PAT thử nghiệm chỉ có quyền đọc một repository và đặt thời hạn ngắn phù hợp.
4. Đặt remote bằng URL HTTPS không chứa token.
5. Chạy `git fetch` và hoàn tất xác thực qua GCM hoặc prompt của nhà cung cấp.
6. Kiểm tra `git remote -v` để xác nhận URL không chứa token.
7. Chạy fetch lần nữa để xác nhận helper cung cấp credential đã lưu.
8. Xóa credential của host thử nghiệm bằng giao diện quản lý hoặc `git credential reject`, sau đó xác thực lại.
9. Thu hồi PAT thử nghiệm ở nhà cung cấp và xác nhận token không còn sử dụng được.
10. Thảo luận cách CI lấy secret read-only và credential có quyền ghi mà không in giá trị ra log.

Không dùng token đang phục vụ công việc thật để thực hành xóa hoặc thu hồi. Không sao chép token vào file bài tập, script, issue hoặc nội dung commit.

## 16. Tự kiểm tra kiến thức

1. Vì sao nhiều dịch vụ Git yêu cầu PAT hoặc OAuth thay cho mật khẩu tài khoản khi dùng HTTPS?
2. PAT khác mật khẩu tài khoản ở khả năng giới hạn quyền và thu hồi như thế nào?
3. Credential helper được Git gọi vào thời điểm nào?
4. Git Credential Manager lưu credential ở đâu trên các hệ điều hành phổ biến?
5. Vì sao `credential.helper store` không phù hợp để lưu PAT nhạy cảm?
6. Vì sao không nên nhúng token vào remote URL?
7. `credential.useHttpPath` giúp giải quyết tình huống nào?
8. Khi token bị lộ, vì sao cần thu hồi trước khi viết lại Git history?
9. CI nên dùng credential nào khi chỉ cần clone/fetch?
10. Khi nào nên cân nhắc HTTPS token thay cho SSH key?

## Kết luận

Xác thực HTTPS bằng token cho phép giới hạn quyền và thời hạn truy cập repository. Credential manager như Git Credential Manager giúp Git sử dụng thông tin xác thực qua kho bảo mật của hệ điều hành và các luồng đăng nhập được nhà cung cấp hỗ trợ. Hãy cấp quyền tối thiểu, giữ remote URL sạch, không lưu token dạng rõ, kiểm tra cấu hình helper và có quy trình luân chuyển/thu hồi. Với CI/CD, lấy credential từ secret store hoặc identity ngắn hạn, tách quyền đọc và ghi, đồng thời bảo đảm log không làm lộ bí mật.
