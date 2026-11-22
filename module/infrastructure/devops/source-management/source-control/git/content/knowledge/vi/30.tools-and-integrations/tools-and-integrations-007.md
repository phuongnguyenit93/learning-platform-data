# Cung cấp danh tính và thông tin xác thực cho script không tương tác

Script tự động thường cần chạy các lệnh Git như fetch, pull, push, tạo commit hoặc tạo tag mà không có người ngồi nhập thông tin ở terminal. Để quy trình không bị dừng giữa chừng, bạn phải cung cấp trước hai nhóm thông tin khác nhau: danh tính sẽ được ghi vào commit và credential dùng để xác thực với remote.

Hai nhóm này không thay thế cho nhau. <code>user.name</code> và <code>user.email</code> xác định author/committer trong metadata của commit; chúng không cấp quyền truy cập repository. Ngược lại, token hoặc SSH key cho phép kết nối đến remote nhưng không tự xác định tên và email được ghi vào commit.

Bài thuộc chương **Công cụ và tích hợp** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Bài này tập trung vào cách cung cấp danh tính và credential an toàn cho CI/CD, cron job, script triển khai và các tác vụ Git tự động.

## 1. Hai câu hỏi khác nhau: ai tạo commit và ai được phép truy cập remote?

Khi một script chạy:

~~~bash
git fetch origin
git commit -m "Update generated metadata"
git push origin main
~~~

Git có thể cần giải quyết hai việc:

1. Nếu tạo commit, Git cần biết author và committer là ai.
2. Khi fetch hoặc push, Git cần xác thực với máy chủ và kiểm tra tài khoản có quyền đọc hoặc ghi hay không.

| Nhóm thông tin | Dùng để làm gì? | Ví dụ |
|---|---|---|
| Commit identity | Ghi author và committer vào commit object | <code>user.name</code>, <code>user.email</code>, <code>GIT_AUTHOR_NAME</code>, <code>GIT_COMMITTER_EMAIL</code> |
| Authentication credential | Xác thực khi kết nối remote | HTTPS token, credential manager, SSH key, SSH agent |
| Authorization | Xác định credential được phép làm gì | Quyền đọc repository, quyền push branch, quyền tạo tag/release |
| Commit signing identity | Ký commit hoặc tag để xác minh chữ ký | GPG key hoặc SSH signing key |

Commit identity không phải bằng chứng xác thực. Một người có thể cấu hình <code>user.name</code> thành tên bất kỳ; quyền truy cập remote được máy chủ xác định bằng credential và chính sách quyền.

## 2. Cấu hình danh tính author và committer

Git cần tên và email để tạo commit. Nếu repository hoặc môi trường chưa có cấu hình phù hợp, lệnh commit có thể thất bại hoặc dùng thông tin không mong muốn.

### Cấu hình riêng trong repository

Với một script tạo commit trong repository hiện tại:

~~~bash
git config --local user.name "Automation Bot"
git config --local user.email "automation-bot@example.invalid"
~~~

Phạm vi <code>--local</code> chỉ ảnh hưởng repository hiện tại. Đây thường là lựa chọn phù hợp cho CI vì không làm thay đổi cấu hình của các repository khác trên máy runner.

### Cấu hình trong một lệnh

Nếu chỉ cần identity cho một commit:

~~~bash
git -c user.name="Automation Bot" \
    -c user.email="automation-bot@example.invalid" \
    commit -m "Update generated metadata"
~~~

Các giá trị này áp dụng cho tiến trình Git đó, không ghi vào cấu hình lâu dài.

### Dùng biến môi trường

Git hỗ trợ các biến môi trường riêng:

~~~bash
export GIT_AUTHOR_NAME="Automation Bot"
export GIT_AUTHOR_EMAIL="automation-bot@example.invalid"
export GIT_COMMITTER_NAME="Automation Bot"
export GIT_COMMITTER_EMAIL="automation-bot@example.invalid"

git commit -m "Update generated metadata"
~~~

<code>GIT_AUTHOR_*</code> xác định người được ghi nhận là tác giả thay đổi. <code>GIT_COMMITTER_*</code> xác định người tạo commit object. Nếu không đặt riêng, Git thường dùng cấu hình <code>user.name</code> và <code>user.email</code> cho cả hai vai trò.

Kiểm tra cấu hình:

~~~bash
git config --show-origin --get user.name
git config --show-origin --get user.email
~~~

Để kiểm tra các biến môi trường đang có mà không in credential:

~~~bash
printf 'Author: %s <%s>\n' "$GIT_AUTHOR_NAME" "$GIT_AUTHOR_EMAIL"
printf 'Committer: %s <%s>\n' "$GIT_COMMITTER_NAME" "$GIT_COMMITTER_EMAIL"
~~~

Tên và email được ghi vào lịch sử commit. Hãy dùng địa chỉ bot hoặc địa chỉ noreply được tổ chức phê duyệt nếu không muốn lộ email cá nhân.

### Cấu hình identity trong PowerShell

~~~powershell
git config --local user.name "Automation Bot"
git config --local user.email "automation-bot@example.invalid"

$env:GIT_AUTHOR_NAME = "Automation Bot"
$env:GIT_AUTHOR_EMAIL = "automation-bot@example.invalid"
$env:GIT_COMMITTER_NAME = "Automation Bot"
$env:GIT_COMMITTER_EMAIL = "automation-bot@example.invalid"
~~~

Biến môi trường PowerShell áp dụng cho tiến trình con được chạy từ phiên đó. Xóa chúng sau khi dùng nếu không muốn các lệnh Git tiếp theo trong cùng phiên tiếp tục dùng identity này:

~~~powershell
Remove-Item Env:GIT_AUTHOR_NAME, Env:GIT_AUTHOR_EMAIL, Env:GIT_COMMITTER_NAME, Env:GIT_COMMITTER_EMAIL -ErrorAction SilentlyContinue
~~~

## 3. Xác thực với remote qua HTTPS

Với URL HTTPS, Git có thể cần username và password. Trên nhiều nền tảng, password ở đây là personal access token, project token, job token hoặc credential do nhà cung cấp cấp, không phải mật khẩu đăng nhập thông thường.

Ví dụ remote:

~~~text
https://git.example.com/team/payment-service.git
~~~

Không đặt token trực tiếp trong URL:

~~~text
https://username:token@git.example.com/team/payment-service.git
~~~

URL có thể được ghi vào <code>.git/config</code>, log, shell history, output chẩn đoán hoặc danh sách tiến trình. Dùng URL không chứa bí mật và để credential helper hoặc askpass cung cấp credential khi Git yêu cầu.

### Credential helper cho máy phát triển

Credential helper cho phép Git lấy thông tin đăng nhập từ một nơi lưu trữ riêng. Ví dụ, Git Credential Manager tích hợp với cơ chế lưu trữ an toàn của hệ điều hành và có thể thực hiện đăng nhập qua trình duyệt.

Trên Git for Windows hoặc máy phát triển đã cài Git Credential Manager, kiểm tra:

~~~bash
git credential-manager --version
git config --show-origin --get-all credential.helper
~~~

Với phiên bản GCM hiện đại, cấu hình thường dùng:

~~~bash
git config --global credential.helper manager
~~~

Tên helper cụ thể phụ thuộc phiên bản Git/GCM đã cài. GCM phù hợp với người dùng phát triển tương tác; script không tương tác chỉ chạy ổn nếu credential đã được cấp trước và helper có thể sử dụng mà không cần mở trình duyệt hoặc hỏi người dùng.

### Các helper khác

| Helper | Cách hoạt động | Lưu ý |
|---|---|---|
| <code>manager</code> | Dùng Git Credential Manager | Ưu tiên cho máy phát triển khi được cài và cấu hình |
| <code>cache</code> | Giữ credential tạm trong bộ nhớ trong một khoảng thời gian | Hữu ích cho phiên làm việc ngắn; không phải kho bí mật dài hạn |
| <code>store</code> | Lưu credential trong file văn bản | Không phù hợp cho credential nhạy cảm trên máy dùng chung hoặc CI |
| Helper của nền tảng/CI | Lấy token từ môi trường hoặc secret store do nền tảng cấp | Ưu tiên token ngắn hạn và quyền tối thiểu |

Tránh cấu hình <code>credential.helper store</code> để lưu token thật dưới dạng văn bản thuần. Nếu file credential bị đọc, token có thể bị sử dụng cho đến khi bị thu hồi.

## 4. Cấp HTTPS credential cho script bằng GIT_ASKPASS

Khi chạy trong CI, cách phổ biến là lưu token trong secret store của hệ thống CI, đưa token vào biến môi trường của đúng job, rồi cung cấp cho Git qua một chương trình askpass.

<code>GIT_ASKPASS</code> chỉ định chương trình được Git gọi khi cần câu trả lời cho prompt xác thực. Script askpass phải ghi câu trả lời ra standard output; không được in token vào log.

### Ví dụ Bash

Tạo một script askpass trong thư mục tạm của job, ví dụ <code>ci-askpass.sh</code>:

~~~bash
#!/bin/sh
case "$1" in
  *Username*)
    test -n "$GIT_HTTP_USERNAME" || exit 1
    printf '%s\n' "$GIT_HTTP_USERNAME"
    ;;
  *Password*)
    test -n "$GIT_HTTP_TOKEN" || exit 1
    printf '%s\n' "$GIT_HTTP_TOKEN"
    ;;
  *)
    exit 1
    ;;
esac
~~~

Script không chứa token. Token và username được cung cấp từ secret store:

~~~bash
chmod 700 ci-askpass.sh

export GIT_HTTP_USERNAME="$CI_GIT_USERNAME"
export GIT_HTTP_TOKEN="$CI_GIT_TOKEN"
export GIT_ASKPASS="$PWD/ci-askpass.sh"
export GIT_TERMINAL_PROMPT=0

git -c credential.helper= fetch https://git.example.com/team/payment-service.git
~~~

Trong ví dụ:

- <code>CI_GIT_USERNAME</code> và <code>CI_GIT_TOKEN</code> phải được job lấy từ secret store hoặc biến bí mật đã bảo vệ.
- <code>GIT_ASKPASS</code> trỏ đến chương trình trả lời prompt.
- <code>GIT_TERMINAL_PROMPT=0</code> ngăn Git chờ người dùng nhập trong terminal.
- <code>-c credential.helper=</code> vô hiệu hóa danh sách helper đã cấu hình cho lệnh này, để ví dụ sử dụng askpass được kiểm soát.

Tùy nền tảng, username có thể là tên tài khoản, tên đặc biệt như <code>oauth2</code>, hoặc giá trị được nhà cung cấp yêu cầu. Hãy dùng đúng quy ước của máy chủ Git. Token phải có quyền đọc cho <code>fetch</code>; nếu job cần push, token phải được cấp thêm quyền ghi tương ứng.

Sau khi job hoàn tất, bỏ các biến môi trường:

~~~bash
unset GIT_HTTP_USERNAME GIT_HTTP_TOKEN GIT_ASKPASS GIT_TERMINAL_PROMPT
~~~

Đảm bảo shell không bật trace như <code>set -x</code> trong lúc xử lý secret. Không chạy <code>env</code>, <code>printenv</code> hoặc lệnh debug in toàn bộ biến môi trường.

### Ví dụ PowerShell trên Windows

Có thể dùng một wrapper CMD gọi PowerShell script để trả lời prompt. Tạo <code>git-askpass.cmd</code> trong thư mục tạm của job:

~~~bat
@echo off
powershell.exe -NoLogo -NoProfile -NonInteractive -File "%~dp0git-askpass.ps1" -Prompt "%~1"
~~~

Tạo <code>git-askpass.ps1</code> cùng thư mục:

~~~powershell
param([string]$Prompt)

if ($Prompt -match "Username") {
    if ([string]::IsNullOrEmpty($env:GIT_HTTP_USERNAME)) { exit 1 }
    [Console]::Out.WriteLine($env:GIT_HTTP_USERNAME)
    exit 0
}

if ($Prompt -match "Password") {
    if ([string]::IsNullOrEmpty($env:GIT_HTTP_TOKEN)) { exit 1 }
    [Console]::Out.WriteLine($env:GIT_HTTP_TOKEN)
    exit 0
}

exit 1
~~~

Trong bước chạy job:

~~~powershell
$env:GIT_HTTP_USERNAME = $env:CI_GIT_USERNAME
$env:GIT_HTTP_TOKEN = $env:CI_GIT_TOKEN
$env:GIT_ASKPASS = (Join-Path $PSScriptRoot "git-askpass.cmd")
$env:GIT_TERMINAL_PROMPT = "0"

try {
    git -c credential.helper= fetch https://git.example.com/team/payment-service.git
    if ($LASTEXITCODE -ne 0) {
        throw "Git fetch failed"
    }
}
finally {
    Remove-Item Env:GIT_HTTP_USERNAME, Env:GIT_HTTP_TOKEN, Env:GIT_ASKPASS, Env:GIT_TERMINAL_PROMPT -ErrorAction SilentlyContinue
}
~~~

Các file askpass chỉ chứa logic, không chứa giá trị bí mật. Tạo chúng trong workspace tạm được bảo vệ và xóa theo chính sách cleanup của runner. Wrapper dùng chính sách thực thi PowerShell hiện có của máy; nếu runner yêu cầu script được ký, hãy ký hoặc dùng cơ chế được quản trị viên phê duyệt thay vì bỏ qua chính sách. Biến môi trường có thể được tiến trình con đọc; vì vậy chỉ cấp token cho job cần nó và không chạy mã không tin cậy trong cùng phạm vi quyền.

## 5. Ngăn script treo khi thiếu credential

Một script không tương tác không nên dừng vô thời hạn để chờ username hoặc password. Với HTTPS, đặt:

~~~bash
export GIT_TERMINAL_PROMPT=0
git fetch origin
~~~

Trong PowerShell:

~~~powershell
$env:GIT_TERMINAL_PROMPT = "0"
git fetch origin
if ($LASTEXITCODE -ne 0) {
    throw "Git fetch failed: credentials or remote access may be unavailable"
}
~~~

Nếu không có credential hợp lệ, Git sẽ thất bại thay vì chờ người dùng nhập. <code>GIT_TERMINAL_PROMPT=0</code> không cấp credential; nó chỉ tắt prompt tương tác ở terminal. Askpass hoặc credential helper vẫn cần được cấu hình nếu máy chủ yêu cầu xác thực.

Đối với Git Credential Manager, đảm bảo job không phụ thuộc vào đăng nhập trình duyệt tương tác. Nếu runner chưa có credential, hãy cấp token qua secret store hoặc cơ chế identity do nền tảng CI hỗ trợ.

## 6. Xác thực qua SSH bằng ssh-agent

Với SSH, Git sử dụng SSH client để kết nối. Trong script, cách thuận tiện là nạp private key vào SSH agent trước khi chạy Git, rồi cấu hình SSH không được hỏi người dùng.

Ví dụ trên môi trường Linux runner:

~~~bash
eval "$(ssh-agent -s)"
ssh-add "$SSH_PRIVATE_KEY_FILE"

export GIT_SSH_COMMAND='ssh -o BatchMode=yes'
git fetch git@git.example.com:team/payment-service.git
~~~

Trong ví dụ, <code>SSH_PRIVATE_KEY_FILE</code> là đường dẫn đến file key do secret store hoặc cơ chế secure file của CI cấp. File private key không được commit vào repository. Hạn chế quyền đọc file và xóa file tạm sau khi job hoàn tất.

<code>ssh-add</code> nạp khóa vào agent; Git gọi SSH client và agent cung cấp khóa khi máy chủ yêu cầu. <code>BatchMode=yes</code> yêu cầu SSH không hỏi câu hỏi tương tác, chẳng hạn passphrase hoặc xác nhận nhập liệu. Nếu agent hoặc key không sẵn sàng, lệnh sẽ thất bại nhanh.

Nếu private key có passphrase, hãy dùng tích hợp SSH agent của nền tảng CI hoặc quy trình nạp key có hỗ trợ passphrase từ secret store. Không bỏ passphrase chỉ để pipeline dễ chạy hơn. <code>BatchMode=yes</code> áp dụng cho kết nối SSH của Git; bước nạp key vào agent phải được cấu hình riêng để cũng không cần nhập tay.

Kiểm tra agent:

~~~bash
ssh-add -l
~~~

Lệnh này liệt kê fingerprint các key đang được nạp, không cần in private key. Không dùng <code>cat</code> hoặc <code>type</code> để in private key vào log.

### Chỉ định key qua SSH config

Nếu runner có nhiều key, có thể cấu hình host cụ thể trong file SSH config:

~~~sshconfig
Host git-ci
    HostName git.example.com
    User git
    IdentityFile ~/.ssh/id_ed25519_ci
    IdentitiesOnly yes
    BatchMode yes
    StrictHostKeyChecking yes
~~~

Remote có thể dùng alias:

~~~bash
git clone git-ci:team/payment-service.git
~~~

Đảm bảo public key tương ứng đã được cấp quyền trên máy chủ. Nếu dùng alias trong SSH config, host trong URL phải khớp với alias.

### Xác minh host key

SSH host key giúp client xác minh máy chủ đang kết nối. Trong CI, provision <code>known_hosts</code> từ nguồn tin cậy và xác minh fingerprint qua kênh độc lập. Không tự động chấp nhận mọi host key mới chỉ để làm pipeline chạy qua.

<code>StrictHostKeyChecking=yes</code> giúp job thất bại nếu host key chưa được tin cậy hoặc thay đổi. Đây là hành vi mong muốn trong môi trường tự động có cấu hình known_hosts rõ ràng.

## 7. Dùng SSH key hay HTTPS token?

| Tiêu chí | SSH key | HTTPS token |
|---|---|---|
| Cách xác thực | Cặp khóa công khai/riêng | Token do nền tảng cấp |
| Cấp quyền | Gắn public key với tài khoản hoặc deploy key | Gắn token với tài khoản, project hoặc job |
| Phạm vi quyền | Có thể dùng deploy key riêng cho repository | Có thể giới hạn scope, repository và thời hạn tùy nền tảng |
| Cung cấp cho CI | Secure file hoặc SSH agent | Secret variable/secret manager và askpass/helper |
| Rủi ro cần quản lý | Lộ private key, host key chưa xác minh | Token bị log, lộ qua URL hoặc biến môi trường |
| Thu hồi | Gỡ key hoặc vô hiệu hóa deploy key | Revoke/expire token |

Không có lựa chọn nào tự động an toàn nếu cấp quyền quá rộng hoặc lưu bí mật sai cách. Chọn phương thức phù hợp với nền tảng, quy trình cấp quyền và khả năng xoay vòng credential của nhóm.

## 8. Cấp quyền tối thiểu cho script

Credential cho job chỉ nên có quyền cần thiết:

- Job chỉ clone hoặc fetch: cấp quyền đọc repository.
- Job tạo artifact hoặc kiểm tra mã: thường chỉ cần đọc.
- Job push branch tự động: chỉ cấp quyền ghi cho repository hoặc phạm vi cần thiết.
- Job phát hành package hoặc tag: cấp quyền phát hành đúng nơi cần dùng.
- Job triển khai: ưu tiên identity riêng cho môi trường triển khai, tách khỏi quyền quản trị repository nếu có thể.

Tách credential theo job hoặc theo môi trường. Token cho pipeline test không nên tự động có quyền xóa branch, quản lý thành viên hoặc thay đổi cấu hình repository.

Nếu nền tảng hỗ trợ token ngắn hạn, job token hoặc workload identity, ưu tiên chúng thay cho token cá nhân dài hạn. Đặt thời hạn hết hạn, scope hẹp và quy trình revoke rõ ràng.

## 9. Kiểm tra quyền đọc và quyền ghi mà không thay đổi remote

Trước khi chạy tác vụ thật, có thể xác minh quyền đọc:

~~~bash
git ls-remote origin HEAD
~~~

Lệnh này hỏi remote về refs mà không checkout hoặc thay đổi branch local. Nếu thất bại, kiểm tra URL, mạng, credential và quyền đọc.

Để kiểm tra khả năng push, có thể dùng dry-run:

~~~bash
git push --dry-run origin HEAD
~~~

Dry-run không cập nhật branch trên remote, nhưng vẫn có thể yêu cầu xác thực và kiểm tra quyền. Nó không bảo đảm một lần push thật chắc chắn thành công vì trạng thái remote có thể thay đổi sau đó, hook hoặc chính sách máy chủ có thể áp dụng khác.

Kiểm tra remote URL:

~~~bash
git remote -v
~~~

Nếu URL chứa username/token hoặc thông tin xác thực, thay bằng URL sạch rồi dùng credential helper hoặc askpass. Không đưa output có thông tin nhạy cảm vào log công khai.

## 10. Viết script Git không tương tác có kiểm tra lỗi

Script nên thất bại rõ ràng khi thiếu credential, không tiếp tục các bước sau khi fetch hoặc push lỗi.

Ví dụ Bash:

~~~bash
#!/usr/bin/env bash
set -euo pipefail

export GIT_TERMINAL_PROMPT=0
export GIT_AUTHOR_NAME="Automation Bot"
export GIT_AUTHOR_EMAIL="automation-bot@example.invalid"
export GIT_COMMITTER_NAME="$GIT_AUTHOR_NAME"
export GIT_COMMITTER_EMAIL="$GIT_AUTHOR_EMAIL"

# Credential phải được cấp sẵn qua helper, askpass hoặc SSH agent.
git fetch origin

# Các bước kiểm tra và tạo thay đổi ở đây.
git add generated/
git diff --cached --check

if git diff --cached --quiet; then
    echo "No staged changes"
else
    diff_status=$?
    if [ "$diff_status" -ne 1 ]; then
        exit "$diff_status"
    fi
    git commit -m "Update generated files"
    git push origin HEAD
fi
~~~

<code>set -euo pipefail</code> giúp script dừng khi lệnh thất bại, biến chưa được khai báo hoặc pipeline có lệnh lỗi. Trong pipeline, vẫn cần chú ý cách runner xử lý exit code và log.

Ví dụ PowerShell:

~~~powershell
$ErrorActionPreference = "Stop"
$env:GIT_TERMINAL_PROMPT = "0"
$env:GIT_AUTHOR_NAME = "Automation Bot"
$env:GIT_AUTHOR_EMAIL = "automation-bot@example.invalid"
$env:GIT_COMMITTER_NAME = $env:GIT_AUTHOR_NAME
$env:GIT_COMMITTER_EMAIL = $env:GIT_AUTHOR_EMAIL

git fetch origin
if ($LASTEXITCODE -ne 0) { throw "git fetch failed" }

git add generated/
if ($LASTEXITCODE -ne 0) { throw "git add failed" }

git diff --cached --check
if ($LASTEXITCODE -ne 0) { throw "staged diff check failed" }

git diff --cached --quiet
if ($LASTEXITCODE -eq 1) {
    git commit -m "Update generated files"
    if ($LASTEXITCODE -ne 0) { throw "git commit failed" }

    git push origin HEAD
    if ($LASTEXITCODE -ne 0) { throw "git push failed" }
}
elseif ($LASTEXITCODE -ne 0) {
    throw "git diff check failed"
}
~~~

PowerShell không tự biến mọi exit code khác 0 của chương trình native thành exception. Kiểm tra <code>$LASTEXITCODE</code> sau mỗi lệnh Git quan trọng để pipeline không báo thành công giả.

## 11. Credential helper, askpass và SSH agent hoạt động ở đâu?

Các cơ chế này thường được Git hoặc SSH gọi khi cần xác thực:

~~~text
Script / CI job
      |
      v
    Git CLI
      |
      +---- HTTPS ----> credential helper / GIT_ASKPASS
      |                         |
      |                         v
      |                  secret store / CI secret
      |
      +---- SSH ------> SSH client
                                |
                                v
                           ssh-agent
                                |
                                v
                         private key đã nạp
~~~

Script chỉ nên biết cách gọi Git và cách nhận credential từ nguồn được bảo vệ. Không nên tự nhúng token hoặc private key vào mã nguồn của script.

## 12. Những nơi không nên lưu credential

Tránh các cách sau:

- Ghi token vào file <code>.git/config</code> hoặc URL remote.
- Commit file <code>.env</code>, private key hoặc file credential.
- Đưa token trực tiếp vào tham số dòng lệnh nếu nó có thể xuất hiện trong process list hoặc log.
- Dùng <code>echo $TOKEN</code> hoặc bật shell tracing khi token đang nằm trong môi trường.
- Lưu token trong <code>credential.helper store</code> trên runner hoặc máy dùng chung.
- Đưa private key vào artifact, cache hoặc output debug.
- Cấp token cá nhân dài hạn với quyền quản trị cho mọi pipeline.

Một số hệ thống CI che giá trị secret trong log, nhưng masking không thay thế cho việc không in secret. Biến đổi, encode, chia nhỏ hoặc in một phần token vẫn có thể làm lộ dữ liệu.

## 13. Phân biệt lỗi identity và lỗi authentication

| Thông báo hoặc hiện tượng | Nhóm lỗi | Cách kiểm tra |
|---|---|---|
| <code>Author identity unknown</code> | Commit identity | Kiểm tra <code>user.name</code>, <code>user.email</code> và <code>GIT_AUTHOR_*</code> |
| <code>Please tell me who you are</code> | Commit identity | Cấu hình identity cho repository hoặc tiến trình |
| <code>Authentication failed</code> | Authentication | Kiểm tra token, helper, askpass và thời hạn credential |
| <code>Permission denied (publickey)</code> | SSH authentication | Kiểm tra key, agent, host alias và quyền của public key |
| <code>Repository not found</code> | URL hoặc authorization | Kiểm tra URL và quyền đọc; repository private có thể trả thông báo chung |
| <code>Could not read Username</code> | Không có phương thức cấp credential | Kiểm tra <code>GIT_ASKPASS</code>, helper và <code>GIT_TERMINAL_PROMPT</code> |
| <code>Permission to ... denied</code> | Authorization | Credential hợp lệ nhưng thiếu quyền thao tác |
| <code>non-fast-forward</code> | Lịch sử branch | Fetch và tích hợp commit remote theo quy trình nhóm; đây không phải lỗi credential |

Đừng thay token chỉ vì commit báo thiếu <code>user.name</code>; cũng đừng đổi <code>user.email</code> để xử lý lỗi SSH. Xác định đúng lớp lỗi trước khi thay cấu hình.

## 14. Debug xác thực mà không làm lộ bí mật

Khi Git không kết nối được, kiểm tra từng lớp:

1. URL remote có đúng host và repository không?
2. Runner có kết nối mạng và DNS đến host không?
3. Với HTTPS, credential helper hoặc askpass có sẵn không?
4. Với SSH, agent có key phù hợp và known_hosts có host key đáng tin không?
5. Credential có còn hạn và có đúng scope không?
6. Tài khoản/identity có quyền đọc hoặc ghi cần thiết không?

Các lệnh ít rủi ro:

~~~bash
git remote -v
git config --show-origin --get-all credential.helper
git config --show-origin --get user.name
git config --show-origin --get user.email
git ls-remote origin HEAD
ssh-add -l
~~~

Không bật <code>GIT_TRACE_CURL</code>, <code>GIT_CURL_VERBOSE</code>, <code>GIT_TRACE</code> hoặc debug SSH chi tiết trong log công khai nếu chưa hiểu dữ liệu chúng có thể ghi ra. Một số trace có thể chứa URL, header, prompt hoặc thông tin môi trường nhạy cảm. Nếu cần trace, giới hạn người xem, dùng token thử nghiệm có quyền tối thiểu và kiểm tra log trước khi chia sẻ.

## 15. Credential và commit signing là hai cơ chế khác nhau

Xác thực với remote cho biết client có quyền đọc/ghi repository hay không. Commit signing cho biết commit được ký bởi khóa nào để người nhận có thể xác minh chữ ký.

Một pipeline có thể:

- Xác thực bằng HTTPS token nhưng không ký commit.
- Xác thực bằng SSH key nhưng dùng GPG key riêng để ký commit.
- Dùng SSH signing key cho commit và một deploy key khác để fetch/push.

Không dùng private key xác thực SSH như khóa ký commit trừ khi nhóm đã thiết kế và cấu hình rõ ràng cho mục đích đó. Không commit private signing key vào repository.

## 16. Checklist triển khai Git trong CI/CD

Trước khi đưa script vào pipeline:

- Chọn identity bot và email được tổ chức chấp nhận.
- Xác định job cần đọc, ghi hay phát hành.
- Cấp token hoặc key với quyền tối thiểu và thời hạn phù hợp.
- Lưu credential trong secret store của CI, không lưu trong repository.
- Cấp secret chỉ cho job và nhánh đáng tin cậy cần dùng.
- Chọn HTTPS askpass/credential helper hoặc SSH agent.
- Tắt terminal prompt để job thất bại nhanh khi thiếu credential.
- Với SSH, xác minh host key qua nguồn tin cậy.
- Không in biến môi trường, token, private key hoặc trace nhạy cảm.
- Kiểm tra quyền đọc bằng <code>git ls-remote</code>; cân nhắc <code>git push --dry-run</code> cho quyền ghi.
- Kiểm tra exit code và không bỏ qua lỗi fetch/commit/push.
- Có quy trình revoke và rotate khi credential bị lộ.

## 17. Bài tập tự kiểm tra

Thực hành trong repository thử nghiệm hoặc pipeline sandbox:

1. Tạo commit với <code>user.name</code> và <code>user.email</code> được cấu hình local.
2. Đặt <code>GIT_AUTHOR_*</code> và <code>GIT_COMMITTER_*</code>, rồi kiểm tra metadata commit.
3. Xác minh rằng cấu hình identity không cấp quyền truy cập remote.
4. Tạo askpass script không chứa secret và cung cấp token thử nghiệm từ biến môi trường bảo vệ.
5. Đặt <code>GIT_TERMINAL_PROMPT=0</code>, chạy <code>git ls-remote</code> và xác nhận job không chờ nhập tay.
6. Cấu hình SSH agent với deploy key chỉ đọc và kiểm tra <code>ssh-add -l</code>.
7. Thử chạy fetch khi thiếu credential để quan sát lỗi không tương tác.
8. Phân biệt lỗi <code>Author identity unknown</code>, <code>Authentication failed</code> và <code>Permission denied</code>.
9. Kiểm tra log pipeline để chắc chắn không có token, private key hoặc URL chứa credential.
10. Viết một checklist revoke/rotate credential nếu token của job bị lộ.

Một script Git không tương tác cần identity rõ ràng, credential được cấp từ nguồn bảo vệ và cách thất bại nhanh khi xác thực không thành công. Hãy tách riêng metadata commit khỏi quyền truy cập remote, giới hạn quyền của bot theo đúng nhiệm vụ và giữ mọi bí mật ngoài lịch sử mã nguồn.
