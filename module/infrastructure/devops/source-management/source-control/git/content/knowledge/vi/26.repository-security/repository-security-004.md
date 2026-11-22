# Không đưa mật khẩu, token và khóa riêng vào URL hoặc cấu hình kho mã

Git cần xác thực khi kết nối đến remote riêng tư, tải submodule hoặc gửi dữ liệu lên máy chủ. Có nhiều cách cung cấp thông tin xác thực như HTTPS với credential helper, SSH key hoặc token do hệ thống CI cấp. Một sai lầm phổ biến là gắn mật khẩu hay token trực tiếp vào URL remote, ghi khóa riêng vào file cấu hình hoặc commit tệp bí mật vào repository.

Những cách này có thể khiến bí mật xuất hiện trong `.git/config`, lịch sử shell, log CI, bản sao lưu, bản clone hoặc lịch sử commit. Xóa chuỗi bí mật khỏi tệp hiện tại không làm nó biến mất khỏi các nơi đã lưu trước đó.

Bài học này hướng dẫn cách nhận diện vị trí dễ rò rỉ, cấu hình xác thực HTTPS và SSH an toàn, quản lý bí mật trong CI, ngăn commit nhầm và xử lý khi thông tin xác thực đã bị lộ.

## 1. Phân biệt URL remote và thông tin xác thực

### 1.1. Remote URL chỉ cần xác định repository

Một remote thường có tên như `origin` hoặc `upstream`. URL của nó xác định máy chủ và repository cần kết nối.

Ví dụ URL HTTPS không chứa thông tin xác thực:

~~~bash
git remote add origin https://github.com/ORG/PROJECT.git
~~~

Hoặc cập nhật URL hiện có:

~~~bash
git remote set-url origin https://github.com/ORG/PROJECT.git
~~~

Khi kết nối, Git sẽ yêu cầu hoặc lấy thông tin xác thực từ credential helper đã cấu hình. Người dùng không cần đưa token vào URL.

URL SSH cũng không cần chứa khóa riêng:

~~~bash
git remote set-url origin git@github.com:ORG/PROJECT.git
~~~

Trong ví dụ, `git@github.com` là tài khoản SSH và máy chủ; SSH client chọn khóa phù hợp thông qua ssh-agent hoặc cấu hình SSH.

### 1.2. Vì sao không nhúng token vào URL?

Không nên dùng dạng URL như:

~~~text
https://USERNAME:TOKEN@github.com/ORG/PROJECT.git
~~~

Cũng không nên gắn token vào query string:

~~~text
https://github.com/ORG/PROJECT.git?access_token=TOKEN
~~~

Các chuỗi này có thể bị lưu trong:

- `.git/config` nếu được đặt làm remote URL ở cấp repository.
- Cấu hình global hoặc system nếu đặt ở cấp tương ứng.
- Lịch sử lệnh của shell.
- Log của script, CI hoặc công cụ GUI.
- Danh sách tiến trình hoặc thông tin chẩn đoán khi lệnh được gọi với đối số chứa bí mật.
- Bản sao lưu, archive hoặc bản sao repository được chia sẻ.

Một URL chứa token cũng có thể được hiển thị bởi `git remote -v`, công cụ quản trị hoặc log debug. Vì vậy, remote URL nên chỉ chứa địa chỉ repository.

### 1.3. .git/config không phải nơi lưu bí mật

Cấu hình local của repository thường nằm trong `.git/config`. File này không được commit như tệp nguồn thông thường, nhưng vẫn có thể chứa dữ liệu nhạy cảm nếu bạn tự ghi token hoặc password vào đó.

Ví dụ, cấu hình remote có thể được lưu dưới dạng:

~~~ini
[remote "origin"]
    url = https://github.com/ORG/PROJECT.git
    fetch = +refs/heads/*:refs/remotes/origin/*
~~~

Đây là dạng phù hợp vì URL không chứa credential.

Dù `.git/config` không được commit, nó vẫn có thể bị lộ khi:

- Nén toàn bộ thư mục repository để gửi hỗ trợ.
- Sao lưu thư mục làm việc lên dịch vụ không được bảo vệ.
- Chia sẻ máy hoặc tài khoản hệ điều hành.
- Công cụ chẩn đoán thu thập Git directory.
- Một script vô tình in toàn bộ cấu hình ra log.

Không nên coi cấu hình local là một kho bí mật. Nó chỉ là file cấu hình văn bản.

## 2. Những vị trí dễ làm lộ mật khẩu, token và khóa riêng

### 2.1. Remote URL và Git config

Kiểm tra URL remote:

~~~bash
git remote -v
~~~

Lệnh này hữu ích để xác nhận remote fetch/push, nhưng nếu URL cũ đã nhúng token, đầu ra có thể hiển thị token đó. Khi chia sẻ kết quả, hãy che phần bí mật trước.

Có thể xem giá trị URL trong cấu hình:

~~~bash
git config --show-origin --get remote.origin.url
~~~

Lệnh cũng có thể in credential nếu URL đang chứa credential. Chỉ chạy và xem kết quả trong môi trường riêng tư; không dán nguyên đầu ra vào ticket, chat hoặc log công khai.

Ngoài remote URL, các khóa cấu hình như `http.<url>.extraheader` có thể chứa header xác thực. Header thường có giá trị mã hóa Base64, nhưng Base64 không phải mã hóa bảo mật và có thể giải mã ngược. Không lưu Authorization header có token dài hạn trong file cấu hình.

### 2.2. File cấu hình được commit

Một số file cấu hình nằm trong working tree và được Git theo dõi, chẳng hạn:

- `.env`
- `config/local.yml`
- `application-prod.properties`
- `settings.json`
- `.npmrc`, `.pypirc` hoặc file cấu hình công cụ khác
- `.gitmodules` nếu submodule URL bị ghi kèm thông tin xác thực

Không phải mọi file có tên cấu hình đều chứa bí mật. Hãy phân biệt cấu hình công khai với credential riêng của từng máy hoặc môi trường.

Ví dụ, repository có thể cung cấp `.env.example` chỉ chứa tên biến và giá trị giả:

~~~dotenv
API_BASE_URL=https://api.example.test
API_TOKEN=
DATABASE_URL=
~~~

File `.env` thực tế chứa token hoặc mật khẩu nên nằm ngoài Git và được cấp qua secret manager hoặc cấu hình môi trường.

### 2.3. Lịch sử commit

Nếu một token từng được commit, việc xóa nó khỏi file ở commit mới không xóa nội dung ở commit cũ. Người có quyền đọc repository vẫn có thể checkout commit cũ hoặc tìm chuỗi bí mật trong lịch sử.

Ví dụ:

~~~text
A --- B --- C
      |
      +-- B chứa token đã commit
~~~

Commit mới D xóa token khỏi file:

~~~text
A --- B --- C --- D
~~~

Token vẫn còn trong B và C. Vì vậy, khi bí mật đã bị commit hoặc push, cần xử lý như một sự cố credential, không chỉ sửa nội dung hiện tại.

### 2.4. Shell history, log và công cụ tự động

Không truyền token trực tiếp trong lệnh nếu có thể tránh:

~~~bash
git clone https://USERNAME:TOKEN@github.com/ORG/PROJECT.git
~~~

Ngay cả khi lệnh chỉ chạy một lần, chuỗi có thể còn trong history, log của runner hoặc thông tin chẩn đoán. Tương tự, tránh:

- In biến môi trường bí mật bằng `echo`, `set` hoặc `env`.
- Bật debug HTTP khi chưa hiểu log sẽ chứa gì.
- Ghi token vào tham số dòng lệnh của tiến trình.
- Lưu credential trong script được commit.
- Gửi file log nguyên bản khi chưa rà soát thông tin nhạy cảm.

Mã hóa Base64, URL encoding hoặc đổi tên biến không biến một token thành dữ liệu an toàn để công khai.

## 3. Xác thực HTTPS bằng credential helper

### 3.1. Credential helper làm gì?

Credential helper là cơ chế để Git lấy và lưu thông tin xác thực mà không cần nhúng chúng vào remote URL. Khi máy chủ yêu cầu xác thực, Git gọi helper đã cấu hình; helper có thể yêu cầu người dùng đăng nhập hoặc lấy credential từ kho lưu trữ bảo mật.

Kiểm tra helper đang cấu hình:

~~~bash
git config --show-origin --get-all credential.helper
~~~

Có thể có nhiều helper hoặc helper ở nhiều cấp cấu hình. Hãy kiểm tra nguồn xuất xứ để hiểu Git đang sử dụng cơ chế nào.

### 3.2. Ưu tiên kho lưu trữ credential của hệ điều hành

Git Credential Manager (GCM) là lựa chọn phổ biến trên Windows, macOS và Linux. GCM hỗ trợ các luồng xác thực hiện đại và tích hợp với kho thông tin xác thực của hệ điều hành hoặc nhà cung cấp.

Khi GCM đã được cài đặt, có thể cấu hình helper:

~~~bash
git config --global credential.helper manager
~~~

Tên helper có thể khác theo phiên bản hoặc gói cài đặt. Hãy kiểm tra tài liệu của bản GCM đang dùng nếu Git không tìm thấy helper.

Một số hệ thống cũng có helper chuyên biệt:

- macOS: `osxkeychain`.
- Linux: helper tích hợp libsecret hoặc kho bí mật desktop.
- Windows: Git Credential Manager thường tích hợp Windows Credential Manager.

Dùng helper phù hợp với môi trường và chính sách tổ chức. Không cần ghi password hoặc token trực tiếp vào file `.gitconfig`.

### 3.3. Phân biệt cache và store

Git có các helper đơn giản với mức bảo vệ khác nhau:

- `cache` giữ credential tạm trong bộ nhớ trong một khoảng thời gian.
- `store` lưu credential lâu dài trong file văn bản thuần, thường là `~/.git-credentials`.

Không nên chọn `store` cho token hoặc password nhạy cảm trên máy dùng chung hay môi trường có rủi ro truy cập file. File được bảo vệ bằng quyền truy cập hệ điều hành vẫn là văn bản có thể đọc được bởi tài khoản có quyền.

Nếu cần lưu lâu dài, ưu tiên helper tích hợp kho bí mật của hệ điều hành hoặc cơ chế SSO/OAuth do nhà cung cấp hỗ trợ.

### 3.4. Sử dụng HTTPS mà không nhúng token vào URL

Đặt remote URL không chứa credential:

~~~bash
git remote set-url origin https://github.com/ORG/PROJECT.git
~~~

Sau đó chạy thao tác cần xác thực:

~~~bash
git fetch origin
~~~

Git Credential Manager hoặc helper đã cấu hình sẽ thực hiện luồng đăng nhập. Nếu nhà cung cấp yêu cầu personal access token (PAT), nhập token qua prompt hoặc luồng xác thực được helper hỗ trợ, không gắn nó vào URL.

Một số nền tảng không còn chấp nhận password tài khoản cho Git qua HTTPS. Khi đó, dùng PAT với quyền tối thiểu hoặc OAuth/SSO theo chính sách của nhà cung cấp.

## 4. Sử dụng token an toàn

### 4.1. Chọn đúng loại token

Token nên có:

- Quyền tối thiểu cần thiết cho công việc.
- Phạm vi repository cụ thể nếu nền tảng hỗ trợ.
- Thời hạn hết hạn phù hợp.
- Chủ sở hữu hoặc mục đích rõ ràng.
- Quy trình thu hồi và thay mới.

Không dùng một token cá nhân có toàn quyền cho mọi script, máy chủ và repository. Với automation, ưu tiên token riêng cho workload hoặc danh tính máy nếu nền tảng hỗ trợ.

### 4.2. Không đưa token vào URL hoặc file cấu hình

Tránh các cách sau:

~~~bash
git remote set-url origin https://USER:TOKEN@github.com/ORG/PROJECT.git
git config --global remote.origin.url https://USER:TOKEN@github.com/ORG/PROJECT.git
~~~

Cả hai đều có thể lưu token dưới dạng văn bản thuần trong cấu hình. Thay vào đó, dùng URL sạch và credential helper.

Nếu một công cụ yêu cầu token qua API, hãy dùng cơ chế secret input hoặc credential provider chính thức của công cụ. Đừng chuyển token thành tham số tùy ý chỉ để làm cho lệnh chạy không tương tác.

### 4.3. Không chia sẻ token qua chat hoặc ticket

Khi cần hỗ trợ lỗi xác thực, chỉ chia sẻ:

- Thông báo lỗi đã loại bỏ token.
- Nhà cung cấp và loại xác thực đang dùng.
- Thời điểm lỗi và thao tác xảy ra.
- Tên remote sau khi đã rà soát URL.
- Mã request hoặc correlation ID nếu không nhạy cảm.

Không gửi token, password, private key, recovery code hoặc file credential cho đồng đội để họ “thử giúp”. Hãy cấp quyền riêng cho tài khoản hoặc workload của người cần truy cập.

## 5. Sử dụng SSH key mà không làm lộ khóa riêng

### 5.1. Phân biệt khóa riêng và khóa công khai

SSH thường dùng một cặp khóa:

- **Private key:** giữ bí mật trên máy hoặc trong hệ thống quản lý khóa. Không commit, gửi qua chat hay tải lên repository.
- **Public key:** có thể đăng ký với Git hosting provider hoặc máy chủ SSH để cấp quyền truy cập.

Ví dụ tên file:

~~~text
~/.ssh/id_ed25519_work       # private key
~/.ssh/id_ed25519_work.pub   # public key
~~~

Chỉ file `.pub` được đưa lên dịch vụ quản lý Git. Không bao giờ đưa private key lên repository.

### 5.2. Tạo khóa riêng cho công việc

Có thể tạo khóa Ed25519:

~~~bash
ssh-keygen -t ed25519 -C "work Git access" -f ~/.ssh/id_ed25519_work
~~~

Khi được hỏi, đặt passphrase mạnh cho private key. Passphrase giúp bảo vệ khóa nếu file bị sao chép.

Trên Windows, macOS và Linux, đường dẫn home và cách quản lý SSH agent có thể khác. Hãy chọn vị trí phù hợp với tài khoản người dùng và bảo đảm quyền truy cập file hạn chế.

### 5.3. Nạp khóa vào SSH agent

Sau khi tạo khóa, nạp vào agent:

~~~bash
ssh-add ~/.ssh/id_ed25519_work
~~~

SSH agent giữ khóa đã mở khóa trong phiên làm việc để không phải nhập passphrase mỗi lần kết nối. Agent không phải nơi để commit khóa; private key vẫn cần được bảo vệ trên đĩa.

Nếu lệnh báo không kết nối được agent, kiểm tra dịch vụ ssh-agent của hệ điều hành và terminal hiện tại.

### 5.4. Cấu hình SSH theo host

Có thể tạo alias trong `~/.ssh/config`:

~~~sshconfig
Host github-work
    HostName github.com
    User git
    IdentityFile ~/.ssh/id_ed25519_work
    IdentitiesOnly yes
~~~

Sau đó dùng alias trong remote:

~~~bash
git remote set-url origin git@github-work:ORG/PROJECT.git
~~~

Cấu hình này chỉ chỉ định SSH client dùng khóa nào khi kết nối. Private key không nằm trong URL và không được ghi vào Git config.

Kiểm tra kết nối:

~~~bash
ssh -T git@github-work
~~~

Thông báo thành công có thể nói rằng máy chủ đã xác thực bạn nhưng không cung cấp shell tương tác. Đây là hành vi bình thường đối với nhiều Git hosting provider.

### 5.5. Kiểm tra host key

SSH cũng cần xác thực máy chủ. Khi kết nối lần đầu, SSH có thể hỏi xác nhận host key. Hãy đối chiếu fingerprint với tài liệu chính thức của nhà cung cấp hoặc nguồn tin cậy của tổ chức.

Không chấp nhận host key mới một cách máy móc khi cảnh báo rằng key đã thay đổi. Điều đó có thể là thay đổi hạ tầng hợp lệ, nhưng cũng có thể báo hiệu kết nối đến máy chủ khác hoặc nguy cơ trung gian. Xác minh fingerprint trước khi cập nhật `known_hosts`.

## 6. Bảo vệ cấu hình và file bí mật trong repository

### 6.1. Dùng .gitignore cho file local

Một `.gitignore` có thể loại các file bí mật khỏi danh sách untracked:

~~~gitignore
.env
.env.*
!.env.example
*.pem
*.key
secrets/
credentials/
~~~

Các pattern chỉ là ví dụ; điều chỉnh theo cấu trúc dự án. Không phải mọi file `.pem` hoặc `.key` đều là private key, nhưng nếu dự án có loại file hợp lệ dùng các phần mở rộng này, hãy tạo quy tắc cụ thể hơn để tránh bỏ sót hoặc loại nhầm.

### 6.2. .gitignore không gỡ file đã được theo dõi

Nếu `.env` đã được commit, thêm nó vào `.gitignore` không làm Git ngừng theo dõi file đó.

Để bỏ file khỏi index nhưng giữ file trên máy:

~~~bash
git rm --cached -- .env
git add .gitignore
git commit -m "Stop tracking local environment file"
~~~

Sau đó, các máy phát triển có thể giữ file local của họ, còn repository không tiếp tục theo dõi file đó.

Tuy nhiên, nếu file từng chứa token hoặc password, bí mật vẫn tồn tại trong các commit cũ. Cần thu hồi credential và đánh giá việc xóa khỏi lịch sử như một sự cố riêng.

### 6.3. Cung cấp file mẫu không chứa bí mật

Có thể commit `.env.example` với placeholder:

~~~dotenv
DATABASE_URL=
API_TOKEN=
PAYMENT_PROVIDER=
~~~

Tài liệu onboarding hướng dẫn mỗi thành viên tạo `.env` cục bộ hoặc lấy giá trị từ secret manager. Không đưa giá trị sản xuất, token thật hoặc mật khẩu dùng chung vào file mẫu.

### 6.4. Kiểm tra trước khi commit

Trước khi commit, xem danh sách và nội dung staged:

~~~bash
git status --short
git diff --cached --name-only
git diff --cached
~~~

Lệnh cuối có thể hiển thị trực tiếp secret nếu nó đã được stage. Hãy xem trong môi trường riêng tư và không sao chép đầu ra chưa rà soát vào chat hoặc ticket.

Có thể dùng secret scanner trong pre-commit, CI hoặc push protection của nền tảng Git hosting. Scanner giúp phát hiện token và khóa theo mẫu, nhưng không bảo đảm phát hiện mọi bí mật, đặc biệt dữ liệu đã mã hóa hoặc nằm trong file nhị phân.

## 7. Quản lý secret trong CI/CD

### 7.1. Lưu secret trong kho bí mật của nền tảng

CI cần token để clone private dependency, push artifact hoặc triển khai. Hãy lưu chúng trong chức năng secrets/variables được bảo vệ của CI hoặc secret manager chuyên dụng.

Không lưu token trong:

- File YAML workflow được commit.
- Script build hoặc deploy.
- Dockerfile và image layer.
- File cấu hình được đóng gói vào artifact.
- Log hoặc output của job.

Workflow chỉ tham chiếu tên secret, ví dụ:

~~~yaml
steps:
  - name: Publish package
    env:
      PACKAGE_TOKEN: ${{ secrets.PACKAGE_TOKEN }}
    run: ./scripts/publish.sh
~~~

Đây là ví dụ cú pháp của GitHub Actions. Với nền tảng CI khác, dùng cơ chế secret injection tương ứng.

### 7.2. Hạn chế quyền và thời hạn

Token CI nên có quyền đúng với tác vụ. Ví dụ, job chỉ cần đọc repository thì không nên nhận quyền ghi. Job phát hành chỉ nên có quyền publish vào tài nguyên cần thiết.

Khi nền tảng hỗ trợ, ưu tiên:

- Token ngắn hạn.
- OIDC hoặc workload identity thay cho secret dài hạn.
- Token riêng theo repository hoặc môi trường.
- Quyền chỉ đọc cho bước tải dependency.
- Phê duyệt môi trường trước khi cấp secret production.

Không tái sử dụng token cá nhân của nhân viên cho pipeline lâu dài.

### 7.3. Không in secret ra log

Tránh các lệnh như:

~~~bash
echo "$PACKAGE_TOKEN"
env
printenv
set
~~~

Một số CI tự che giá trị secret đã đăng ký, nhưng masking không phải bảo đảm tuyệt đối. Secret có thể bị biến đổi, mã hóa, cắt nhỏ hoặc xuất hiện trong thông báo lỗi theo dạng không được nhận diện.

Không bật shell tracing hoặc debug toàn bộ lệnh trong bước xử lý credential nếu có nguy cơ in giá trị. Chỉ log kết quả đã loại bỏ dữ liệu nhạy cảm, chẳng hạn mã trạng thái hoặc tên bước.

### 7.4. Pull request từ fork và secret

Nhiều nền tảng hạn chế cung cấp secret cho workflow chạy từ pull request đến từ fork. Đây là cơ chế bảo vệ vì mã do bên ngoài đề xuất có thể sửa script để đọc và gửi secret ra ngoài.

Không cố vượt qua giới hạn này bằng cách nhúng token vào file workflow hoặc URL. Tách bước kiểm tra không cần secret khỏi bước triển khai có quyền, và chỉ cấp secret sau khi code đã qua kiểm tra/phê duyệt theo chính sách dự án.

## 8. Kiểm tra cấu hình Git mà không làm lộ bí mật

### 8.1. Xem nguồn cấu hình có chọn lọc

Git có thể đọc cấu hình từ system, global, local và worktree. Khi điều tra, dùng truy vấn theo khóa cụ thể:

~~~bash
git config --show-origin --get-all credential.helper
git config --show-origin --get core.hooksPath
~~~

Không gửi nguyên đầu ra `git config --list` ra ngoài khi chưa rà soát. Cấu hình có thể chứa remote URL, header hoặc đường dẫn nội bộ có thông tin nhạy cảm.

### 8.2. Làm sạch remote URL nếu trước đây đã nhúng credential

Nếu remote URL đang chứa token, thay bằng URL sạch:

~~~bash
git remote set-url origin https://github.com/ORG/PROJECT.git
~~~

Kiểm tra lại:

~~~bash
git remote -v
~~~

Trước khi chia sẻ kết quả, xác nhận URL không còn credential. Nếu token từng nằm trong URL, hãy coi token đó đã bị lộ và thu hồi/thay mới. Đổi URL chỉ sửa cấu hình hiện tại, không xóa token khỏi shell history, log hoặc bản sao cũ.

### 8.3. Tránh ghi Authorization header vào cấu hình

Không dùng cấu hình lâu dài để lưu một header chứa token, ví dụ `http.<url>.extraheader` với giá trị Authorization tĩnh. Header có thể được ghi vào `.git/config` hoặc file cấu hình global và lộ khi thu thập cấu hình.

Dùng credential helper hoặc cơ chế xác thực chính thức của công cụ thay thế. Nếu tổ chức có quy trình header tạm thời, hãy cấp từ secret manager ở runtime, hạn chế log và không lưu lại trong file cấu hình lâu dài.

## 9. Xử lý khi token, password hoặc private key đã bị lộ

Hãy coi credential đã lộ là không còn đáng tin cậy. Việc xóa chuỗi khỏi file hoặc commit mới không đủ để bảo vệ tài khoản.

### Bước 1 — Thu hồi hoặc thay mới ngay

Ưu tiên vô hiệu hóa credential tại nơi phát hành:

- Thu hồi PAT hoặc API token.
- Đổi password nếu password bị lộ.
- Xóa SSH public key tương ứng khỏi tài khoản hoặc deploy key list nếu private key bị lộ.
- Thay credential của service account và workload.
- Thu hồi session hoặc refresh token nếu nhà cung cấp hỗ trợ.

Tạo credential mới với quyền tối thiểu và thời hạn phù hợp. Nếu secret có thể truy cập production, đánh giá phạm vi tác động và luân chuyển cả credential phụ thuộc.

### Bước 2 — Xác định nơi bí mật đã xuất hiện

Rà soát các vị trí liên quan:

- File hiện tại và các commit trong lịch sử.
- Remote URL và Git config.
- `.git-credentials` hoặc kho credential của hệ điều hành.
- Shell history, terminal log và script.
- CI logs, artifacts, cache và build output.
- Pull request, issue, chat hoặc ticket.
- Bản clone, fork và bản sao lưu.
- File cấu hình submodule hoặc dependency.

Không đưa giá trị secret vào báo cáo điều tra. Chỉ ghi loại credential, chủ sở hữu, thời điểm, phạm vi quyền và trạng thái thu hồi.

### Bước 3 — Loại bỏ bí mật khỏi code hiện tại

Thay secret bằng biến môi trường hoặc secret manager. Nếu file chỉ dành cho local, thêm quy tắc ignore và cung cấp file mẫu không chứa giá trị thật.

Ví dụ bỏ `.env` khỏi index nhưng giữ bản local:

~~~bash
git rm --cached -- .env
git add .gitignore
git commit -m "Remove local environment file from tracking"
~~~

Đây chỉ là bước làm sạch phiên bản hiện tại. Nếu secret từng được commit, vẫn cần đánh giá lịch sử.

### Bước 4 — Xem xét làm sạch lịch sử

Nếu chính sách yêu cầu loại bỏ secret khỏi lịch sử Git, có thể dùng công cụ viết lại lịch sử như `git filter-repo` theo quy trình của tổ chức. Việc này cần xác định chính xác các ref bị ảnh hưởng: branch, tag và các tham chiếu khác.

Không đưa giá trị token trực tiếp vào câu lệnh hoặc file được commit. Nếu cần file thay thế chứa chuỗi bí mật, bảo vệ file đó như secret, giới hạn quyền truy cập và xóa an toàn sau khi hoàn tất.

Viết lại lịch sử có thể yêu cầu force push và phối hợp với mọi người đang dùng repository. Các bản clone, fork, pull request, cache, artifact và log đã tồn tại có thể vẫn giữ nội dung cũ. Không có thao tác filter nào bảo đảm xóa được mọi bản sao bên ngoài quyền kiểm soát của bạn.

### Bước 5 — Xác minh và thông báo

Sau khi thu hồi credential và làm sạch repository:

- Chạy secret scanner trên nhánh hiện tại và lịch sử theo phạm vi chính sách.
- Xác nhận credential cũ không còn dùng được.
- Kiểm tra CI, deploy key và automation đã chuyển sang credential mới.
- Xem log truy cập để tìm hoạt động bất thường.
- Thông báo cho người quản lý repository và các thành viên cần đồng bộ lịch sử mới.

Không trì hoãn việc thu hồi token để chờ hoàn tất rewrite history. Thu hồi credential là bước giảm rủi ro đầu tiên.

## 10. Những sai lầm thường gặp

- **Nhúng token vào remote URL:** token có thể xuất hiện trong Git config, shell history và log. Dùng URL sạch cùng credential helper.
- **Cho rằng .git/config không commit nên an toàn:** file local vẫn có thể bị sao lưu, nén hoặc chia sẻ. Không lưu bí mật ở đó.
- **Dùng credential.helper store cho token nhạy cảm:** helper này lưu văn bản thuần. Ưu tiên kho bí mật của hệ điều hành hoặc GCM.
- **Commit private SSH key:** private key cấp quyền truy cập và phải được giữ ngoài repository. Chỉ đăng ký public key.
- **Cho rằng .gitignore xóa secret khỏi Git:** ignore chỉ ngăn file chưa được theo dõi được thêm tự động; nó không xóa file đã commit.
- **Chỉ xóa token trong commit mới:** các commit cũ và bản clone vẫn có thể chứa token. Thu hồi trước rồi mới làm sạch lịch sử.
- **Dùng một PAT toàn quyền cho mọi pipeline:** nếu bị lộ, phạm vi ảnh hưởng lớn. Tạo token riêng và cấp quyền tối thiểu.
- **In biến môi trường để debug CI:** log có thể lưu secret lâu dài. Log trạng thái đã được làm sạch.
- **Tin rằng Base64 che giấu credential:** Base64 chỉ là mã hóa biểu diễn, không bảo vệ bí mật.
- **Force push lịch sử đã viết lại mà không báo nhóm:** có thể làm mất commit mới của người khác hoặc khiến clone lệch lịch sử. Lập kế hoạch đồng bộ và hướng dẫn thành viên cập nhật.

## 11. Checklist bảo vệ credential

Trước khi push hoặc chia sẻ repository, xác nhận:

- [ ] Remote URL không chứa username/password/token.
- [ ] Git config không chứa token hoặc Authorization header dài hạn.
- [ ] Private SSH key nằm ngoài repository và có passphrase phù hợp.
- [ ] File `.env`, credential và secret local được ignore nếu không cần commit.
- [ ] File mẫu chỉ chứa placeholder.
- [ ] Credential helper dùng kho lưu trữ phù hợp với hệ điều hành.
- [ ] CI lấy secret từ secret manager và không in giá trị ra log.
- [ ] Token có quyền tối thiểu và thời hạn rõ ràng.
- [ ] Secret scanner hoặc push protection được bật khi nền tảng hỗ trợ.
- [ ] Nếu từng lộ secret, credential cũ đã được thu hồi trước khi xem xét rewrite history.

## 12. Bảng tra cứu nhanh

| Nhu cầu | Lệnh hoặc cách làm |
| --- | --- |
| Xem remote URL | `git remote -v` — rà soát và che credential nếu có |
| Đặt URL HTTPS sạch | `git remote set-url origin https://github.com/ORG/PROJECT.git` |
| Đặt URL SSH | `git remote set-url origin git@github.com:ORG/PROJECT.git` |
| Xem credential helper | `git config --show-origin --get-all credential.helper` |
| Cấu hình Git Credential Manager | `git config --global credential.helper manager` |
| Tạo SSH key | `ssh-keygen -t ed25519 -C "work Git access"` |
| Nạp private key vào agent | `ssh-add ~/.ssh/id_ed25519_work` |
| Kiểm tra SSH | `ssh -T git@github-work` |
| Bỏ file local khỏi index | `git rm --cached -- .env` |
| Xem file đã stage | `git diff --cached --name-only` |
| Thay URL có credential bằng URL sạch | `git remote set-url origin https://github.com/ORG/PROJECT.git` |
| Xử lý secret đã lộ | Thu hồi/thay mới trước, sau đó làm sạch file và lịch sử theo quy trình |

## 13. Tổng kết

Mật khẩu, token, private key và Authorization header là credential nhạy cảm. Không đưa chúng vào remote URL, Git config, file được commit, script hoặc log. Remote URL chỉ nên xác định repository; Git Credential Manager, credential helper phù hợp hoặc SSH agent sẽ xử lý xác thực riêng.

Với repository, hãy dùng `.gitignore` cho file local, cung cấp file mẫu không chứa secret và kiểm tra nội dung staged trước commit. Với CI, lấy credential từ secret manager, cấp quyền tối thiểu và tránh in giá trị ra log.

Nếu credential đã bị lộ, thu hồi hoặc thay mới ngay. Sau đó mới loại bỏ khỏi code hiện tại, đánh giá việc viết lại lịch sử và xử lý các bản clone, fork, artifact hoặc log còn lưu. Cách tiếp cận này bảo vệ cả quyền truy cập lẫn lịch sử quan trọng của repository.

## Tài liệu tham khảo

- [Git credentials — Git documentation](https://git-scm.com/docs/gitcredentials)
- [git-credential — Git documentation](https://git-scm.com/docs/git-credential)
- [Git Credential Manager](https://github.com/git-ecosystem/git-credential-manager)
- [GitHub: About remote repositories](https://docs.github.com/en/get-started/git-basics/about-remote-repositories)
- [GitHub: Removing sensitive data from a repository](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/removing-sensitive-data-from-a-repository)

