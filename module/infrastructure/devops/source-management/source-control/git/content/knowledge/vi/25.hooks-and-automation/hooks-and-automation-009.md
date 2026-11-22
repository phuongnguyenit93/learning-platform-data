# Đọc kết quả, xử lý mã thoát và tránh phân tích đầu ra dành cho người dùng

Git hook là chương trình được Git gọi tại những thời điểm nhất định, chẳng hạn trước khi commit hoặc push. Hook có thể kiểm tra dữ liệu, chạy test, định dạng mã hoặc từ chối thao tác nếu điều kiện chưa đạt. Để hook hoạt động đáng tin cậy, cần phân biệt ba loại thông tin: **mã thoát của lệnh**, **dữ liệu đầu ra dành cho máy đọc** và **thông báo dành cho người dùng**.

Một lỗi thường gặp là viết script dựa vào câu chữ mà Git in ra trên terminal, chẳng hạn tìm chuỗi `nothing to commit` hoặc `Everything up-to-date`. Những thông báo này được thiết kế cho con người; chúng có thể thay đổi theo phiên bản, ngôn ngữ, tùy chọn và ngữ cảnh. Hook nên dựa vào exit status và các định dạng có cấu trúc như `--porcelain`, `-z` hoặc `--format`, rồi tự tạo thông báo rõ ràng cho người dùng.

Bài học này thuộc phần hook và tự động hóa trong quy trình Git: kiểm tra thay đổi trước commit, kiểm tra ref trước push, báo lỗi có ích và bảo đảm một kết quả “không có thay đổi” không bị nhầm thành lỗi thực thi.

## 1. Ba kênh thông tin khi chạy một lệnh

Khi một chương trình Git chạy, nó có thể cung cấp ba loại kết quả:

| Thành phần | Mục đích | Ví dụ |
|---|---|---|
| Exit status (mã thoát) | Cho chương trình gọi biết thao tác thành công, thất bại hoặc một điều kiện đặc biệt. | `0`, `1`, `2` |
| Standard output (`stdout`) | Dữ liệu hoặc kết quả chính của lệnh. | Danh sách ref, tên tệp, commit hash |
| Standard error (`stderr`) | Cảnh báo, chẩn đoán và thông báo lỗi. | Lỗi xác thực, lỗi kết nối, gợi ý cách xử lý |

Ví dụ:

```bash
git status --short
```

Lệnh có thể in danh sách thay đổi ra `stdout` và kết thúc với mã `0`. Working tree bẩn không có nghĩa lệnh `git status` thất bại. Mã thoát cho biết việc truy vấn trạng thái chạy thành công; nội dung trạng thái cho biết repository có thay đổi hay không.

Đây là nguyên tắc quan trọng: **không dùng exit code như một bản tóm tắt mọi trạng thái nghiệp vụ của repository**. Hãy biết chính xác từng lệnh định nghĩa mã thoát của nó như thế nào.

## 2. Exit status có ý nghĩa gì?

Theo quy ước phổ biến của hệ điều hành và shell:

- `0`: lệnh hoàn tất thành công.
- Khác `0`: lệnh báo một trạng thái đặc biệt hoặc có lỗi.

Tuy nhiên, `1` không phải lúc nào cũng có nghĩa là lỗi nghiêm trọng. Một số lệnh dùng `1` để báo “không tìm thấy”, “có khác biệt” hoặc “điều kiện không đúng”. Script cần hiểu hợp đồng của từng lệnh.

### 2.1. Ví dụ với các lệnh Git

| Lệnh | Mã `0` | Mã khác `0` cần hiểu thế nào? |
|---|---|---|
| `git status --short` | Đọc trạng thái thành công; có thể sạch hoặc có thay đổi. | Thường là lỗi truy vấn repository hoặc môi trường. |
| `git diff --quiet` | Không có khác biệt trong phạm vi được so sánh. | `1` nghĩa là có khác biệt; mã lớn hơn có thể là lỗi thực thi. |
| `git diff --cached --quiet` | Không có thay đổi staged so với HEAD. | `1` nghĩa là có thay đổi staged; không nhất thiết là lỗi. |
| `git merge-base --is-ancestor A B` | `A` là tổ tiên của `B`. | `1` nghĩa là không phải tổ tiên; mã khác có thể là lỗi. |
| `git rev-parse --verify <ref>` | Ref phân giải được. | Ref không tồn tại hoặc tên không hợp lệ; cần kiểm tra ngữ cảnh. |
| `git push` | Push hoàn tất theo kết quả Git báo. | Có thể do non-fast-forward, quyền, mạng, hook hoặc chính sách server. |

Hãy đọc tài liệu của lệnh cụ thể trước khi quyết định mã nào phải chặn hook. Một lệnh có thể dùng `1` cho một kết quả bình thường trong logic kiểm tra, trong khi một lệnh khác dùng `1` để báo thất bại.

### 2.2. `git status` trả mã `0` không có nghĩa working tree sạch

Đây là lỗi logic thường thấy trong hook:

```bash
if git status; then
    echo "Repository clean"
fi
```

Điều kiện trên chỉ kiểm tra lệnh `git status` có chạy thành công hay không. Git vẫn trả `0` khi working tree có tệp modified, staged hoặc untracked.

Muốn biết có thay đổi staged hay không, dùng lệnh được thiết kế cho phép kiểm tra đó:

```bash
git diff --cached --quiet
rc=$?
```

Sau đó diễn giải `rc` theo hợp đồng của `git diff --quiet`.

## 3. Đọc mã thoát đúng cách trong shell

### 3.1. Lấy `$?` ngay sau lệnh cần kiểm tra

Trong POSIX shell và Bash, `$?` chứa exit status của lệnh gần nhất. Hãy lưu nó ngay sau lệnh cần kiểm tra:

```bash
git diff --cached --quiet
rc=$?

if [ "$rc" -eq 0 ]; then
    printf '%s\n' "Không có thay đổi staged."
elif [ "$rc" -eq 1 ]; then
    printf '%s\n' "Có thay đổi staged."
else
    printf '%s\n' "Không thể kiểm tra staging area." >&2
    exit "$rc"
fi
```

Nếu chạy thêm `echo`, `printf` hoặc một lệnh khác trước khi lưu `$?`, giá trị này sẽ bị thay bằng exit status của lệnh vừa chạy.

### 3.2. Dùng `if` để xử lý lỗi mà không mất mã thoát

Có thể đặt lệnh trong điều kiện và lấy mã trong nhánh `else`:

```bash
if git diff --cached --check; then
    printf '%s\n' "Kiểm tra whitespace thành công."
else
    rc=$?
    printf '%s\n' "Commit bị chặn: hãy sửa lỗi whitespace trong phần staged." >&2
    exit "$rc"
fi
```

`git diff --cached --check` báo khác `0` khi phát hiện lỗi whitespace hoặc có lỗi thực thi. Hook trên giữ mã lỗi gốc và dừng commit. Nếu cần phân biệt chi tiết hơn giữa các loại lỗi, cần dùng công cụ kiểm tra chuyên biệt hoặc phân tích thông tin có cấu trúc mà công cụ đó cung cấp.

### 3.3. Cẩn thận với pipeline

Trong nhiều shell, mã thoát của pipeline mặc định là mã của lệnh cuối cùng. Ví dụ:

```bash
git status --short | grep '^ M'
```

Mã `$?` sau pipeline thường là mã của `grep`, không phải mã của `git status`. Nếu `grep` không tìm thấy dòng khớp, nó trả `1`; đó có thể chỉ là “không có dòng phù hợp”, không phải Git lỗi.

Trong Bash, `set -o pipefail` giúp pipeline trả mã khác `0` nếu một lệnh trong pipeline thất bại, nhưng vẫn cần hiểu mã của từng chương trình. POSIX shell không yêu cầu hỗ trợ `pipefail`.

Khi cần biết chính xác lệnh Git có chạy thành công không, ưu tiên gọi trực tiếp và lưu mã thoát trước khi xử lý output. Ví dụ dưới đây tạo file tạm để giữ nguyên byte NUL; shell variable không phù hợp để lưu dữ liệu có NUL:

```bash
tmp_file=$(mktemp) || exit $?
trap 'rm -f "$tmp_file"' EXIT HUP INT TERM

git status --porcelain=v1 -z > "$tmp_file"
rc=$?
if [ "$rc" -ne 0 ]; then
    printf '%s\n' "Không đọc được trạng thái Git." >&2
    exit "$rc"
fi

# Đọc "$tmp_file" bằng parser có hỗ trợ NUL.
```

Sau đó phân tích file kết quả bằng chương trình có khả năng xử lý delimiter NUL nếu dùng `-z`.

### 3.4. `set -e` không thay thế xử lý exit status rõ ràng

`set -e` có thể khiến script kết thúc khi một lệnh trả mã khác `0`, nhưng quy tắc có ngoại lệ trong điều kiện `if`, `while`, `&&`, `||`, pipeline, function và command substitution. Điều này dễ gây hành vi bất ngờ khi lệnh dùng `1` cho một trạng thái bình thường.

Với hook có logic điều kiện, nên kiểm tra exit status tường minh thay vì dựa hoàn toàn vào `set -e`. Nếu dùng `set -e`, hãy thiết kế và kiểm thử các nhánh trả mã đặc biệt.

## 4. Đọc mã thoát trong PowerShell

Trên Windows, khi gọi chương trình native như `git.exe`, PowerShell cung cấp:

- `$LASTEXITCODE`: mã thoát số nguyên của chương trình native gần nhất.
- `$?`: trạng thái thành công/thất bại của câu lệnh PowerShell gần nhất; đây là boolean, không phải mã thoát đầy đủ.

Ví dụ kiểm tra staged changes:

```powershell
git diff --cached --quiet
$gitExitCode = $LASTEXITCODE

if ($gitExitCode -eq 0) {
    Write-Output "Không có thay đổi staged."
}
elseif ($gitExitCode -eq 1) {
    Write-Output "Có thay đổi staged."
}
else {
    [Console]::Error.WriteLine("Không thể kiểm tra staging area. Git exit code: $gitExitCode")
    exit $gitExitCode
}
```

Phải lưu `$LASTEXITCODE` ngay sau lệnh Git. Nếu gọi thêm một chương trình native khác trước khi lưu, mã thoát sẽ bị thay thế.

`$ErrorActionPreference = 'Stop'` không tự biến mọi mã thoát khác `0` của chương trình native thành exception trong Windows PowerShell 5.1. Vì vậy, khi viết script hook hoặc automation bằng PowerShell, hãy kiểm tra `$LASTEXITCODE` rõ ràng.

## 5. Tránh phân tích output dành cho người dùng

### 5.1. Vì sao không nên grep câu chữ của Git?

Không nên viết logic như:

```bash
git status | grep "nothing to commit"
git push | grep "Everything up-to-date"
```

Các câu chữ hiển thị có thể thay đổi do:

- Phiên bản Git.
- Ngôn ngữ hoặc locale của môi trường.
- Tùy chọn màu sắc, pager hoặc định dạng.
- Ngữ cảnh lệnh, loại remote và cấu hình người dùng.
- Thay đổi nội dung thông báo trong phiên bản tương lai.

Output dành cho người dùng còn có thể chứa tên tệp, dấu nháy hoặc ký tự đặc biệt khiến cách grep đơn giản không còn chính xác.

### 5.2. Dùng định dạng máy đọc được

Git cung cấp các định dạng ổn định hơn cho script:

| Nhu cầu | Cách nên dùng |
|---|---|
| Đọc trạng thái working tree | `git status --porcelain=v1` hoặc `--porcelain=v2` |
| Xử lý tên tệp có dấu cách/ký tự đặc biệt | Kết hợp `-z` để dùng NUL làm delimiter |
| Liệt kê đường dẫn thay đổi | `git diff --name-only -z` |
| Liệt kê file đang tracked | `git ls-files -z` |
| Lấy thông tin commit | `git log --format=<placeholder>` hoặc `git show --format=...` |
| Liệt kê refs | `git for-each-ref --format=...` |
| Kiểm tra thuộc tính | `git check-attr` với output có cấu trúc |

Ví dụ:

```bash
git status --porcelain=v1 -z
git diff --cached --name-only -z
git log -5 --format='%H%x09%an%x09%s'
git for-each-ref --format='%(refname)%09%(objectname)'
```

`--porcelain` được thiết kế cho script và có định dạng ổn định hơn output thông thường. `-z` dùng byte NUL để phân tách đường dẫn, tránh nhầm khi tên tệp chứa dấu cách, tab hoặc newline. Chương trình đọc kết quả phải xử lý NUL đúng cách; không dùng `for file in $(...)` vì shell sẽ tách theo whitespace và làm hỏng tên tệp.

### 5.3. Không bỏ qua quoting và ký tự đặc biệt

Tên tệp trong repository có thể chứa dấu cách, dấu nháy, dấu `*`, dấu `;` hoặc newline. Khi xử lý đường dẫn:

- Ưu tiên output NUL với `-z`.
- Truyền đường dẫn dưới dạng argument riêng, không ghép thành chuỗi lệnh shell.
- Quote biến shell như `"$path"`.
- Không dùng `eval` để chạy dữ liệu lấy từ Git.
- Không giả định mỗi dòng output tương ứng một đường dẫn nếu tên tệp có thể chứa newline.

Đây vừa là yêu cầu độ chính xác vừa là biện pháp tránh lỗi injection khi repository có dữ liệu do người khác đóng góp.

## 6. Phân biệt dữ liệu hook nhận qua stdin, argument và output

Không phải mọi hook đều nhận dữ liệu bằng cách đọc stdout của Git. Nhiều hook nhận tham số qua argument hoặc dữ liệu qua stdin.

| Hook | Dữ liệu đầu vào chính | Vai trò |
|---|---|---|
| `pre-commit` | Không có argument đặc biệt; đọc index/working tree qua Git command. | Kiểm tra trước khi tạo commit. |
| `prepare-commit-msg` | Đường dẫn file message, nguồn message và có thể có commit ID. | Chuẩn bị nội dung commit message. |
| `commit-msg` | Đường dẫn file commit message. | Kiểm tra hoặc chỉnh message trước commit. |
| `pre-push` | Tên remote và URL qua argument; danh sách ref update qua stdin. | Kiểm tra nội dung sắp push. |
| `post-checkout` | OID HEAD cũ, OID HEAD mới và cờ branch checkout. | Thông báo hoặc cập nhật công việc sau checkout. |
| `post-merge` | Cờ cho biết merge có phải squash merge không. | Thực hiện tác vụ sau merge. |

Ví dụ, `pre-push` nhận mỗi dòng stdin theo cấu trúc gồm local ref, local object name, remote ref và remote object name. Hook nên đọc stdin theo từng trường, không gọi `git push` lần nữa để cố suy ra nội dung đã có sẵn trong đầu vào.

Ví dụ shell tối giản:

```bash
#!/bin/sh

remote_name=$1
remote_url=$2

while IFS=' ' read -r local_ref local_oid remote_ref remote_oid
do
    [ -n "$local_ref" ] || continue
    printf 'Đang kiểm tra %s -> %s\n' "$local_ref" "$remote_ref" >&2
done

exit 0
```

Tên ref không chứa dấu cách, nên tách bốn trường theo cấu trúc trên là phù hợp. Với dữ liệu đường dẫn tùy ý, cần dùng định dạng NUL hoặc parser chuyên dụng.

## 7. Exit status quyết định một số hook có chặn thao tác hay không

Hook thường được phân thành hook kiểm soát (có thể từ chối thao tác) và hook thông báo (chạy sau khi thao tác đã hoàn tất).

### 7.1. Một số client-side hook quan trọng

| Hook | Thời điểm | Nếu trả mã khác `0` |
|---|---|---|
| `pre-commit` | Trước khi tạo commit | Hủy commit. Có thể bị bỏ qua bằng `git commit --no-verify`. |
| `prepare-commit-msg` | Sau khi Git chuẩn bị message, trước khi mở editor | Hủy commit. Hook này không bị bỏ qua bởi `--no-verify`. |
| `commit-msg` | Sau khi người dùng chuẩn bị message | Hủy commit. Có thể bị bỏ qua bằng `--no-verify`. |
| `pre-push` | Trước khi cập nhật remote | Hủy push. Có thể bị bỏ qua bằng `git push --no-verify`. |
| `post-commit` | Sau khi commit thành công | Không thể hủy commit đã tạo. |
| `post-checkout` | Sau checkout/switch | Không thể làm checkout thất bại bằng exit status. |
| `post-merge` | Sau merge thành công | Không thể hủy merge đã hoàn tất. |

Đây là các hook phổ biến, không phải danh sách đầy đủ. Hành vi cụ thể của từng hook được mô tả trong tài liệu `githooks` của phiên bản Git đang dùng.

### 7.2. Hook kiểm soát nên trả mã khác `0` khi điều kiện không đạt

Ví dụ `pre-commit` kiểm tra whitespace trong phần staged:

```bash
#!/bin/sh

if git diff --cached --check; then
    exit 0
else
    rc=$?
    printf '%s\n' "Commit bị chặn: hãy sửa lỗi whitespace trong thay đổi đã stage." >&2
    exit "$rc"
fi
```

Git sẽ hủy commit nếu hook trả mã khác `0`. Thông báo được ghi ra `stderr` để người dùng thấy lý do. Hook không cần phân tích dòng chữ Git in ra; nó dùng exit status của phép kiểm tra.

### 7.3. Hook thông báo không thể thay đổi kết quả đã xảy ra

`post-commit` chạy sau khi commit đã được tạo. Nếu hook này phát hiện lỗi và trả `1`, commit vẫn tồn tại. Hook có thể báo lỗi, gửi thông báo hoặc ghi log, nhưng không nên trình bày exit code của nó như thể commit đã bị từ chối.

Nếu một tác vụ bắt buộc phải chặn commit, đặt kiểm tra trong hook phù hợp như `pre-commit` hoặc `commit-msg`.

### 7.4. `--no-verify` không bỏ qua mọi hook

`git commit --no-verify` bỏ qua `pre-commit` và `commit-msg`; nó không bỏ qua `prepare-commit-msg`. `git push --no-verify` bỏ qua `pre-push`. Không nên xem `--no-verify` là cách sửa lỗi hook; nếu dùng để xử lý tình huống khẩn cấp, cần chạy lại các kiểm tra bị bỏ qua bằng quy trình thay thế và ghi nhận lý do.

## 8. Ví dụ hook dùng mã thoát thay vì parse thông báo

### 8.1. Chặn commit nếu staged diff có whitespace error

Tạo hook `pre-commit`:

```sh
#!/bin/sh

if git diff --cached --check; then
    printf '%s\n' "Pre-commit: kiểm tra whitespace thành công."
    exit 0
else
    rc=$?
    printf '%s\n' "Pre-commit thất bại: kiểm tra whitespace không đạt." >&2
    exit "$rc"
fi
```

Hook gọi trực tiếp `git diff --cached --check` và dùng exit status để quyết định. Nó không tìm câu `no whitespace errors` trong output. Khi kiểm tra thất bại, Git nhận mã khác `0` và hủy commit.

### 8.2. Kiểm tra staged diff có tồn tại hay không

```sh
#!/bin/sh

git diff --cached --quiet
rc=$?

case "$rc" in
    0)
        printf '%s\n' "Không có thay đổi staged."
        ;;
    1)
        printf '%s\n' "Có thay đổi staged để commit."
        ;;
    *)
        printf '%s\n' "Không thể đọc staged diff." >&2
        exit "$rc"
        ;;
esac

exit 0
```

Mã `1` trong ví dụ này có nghĩa là có khác biệt, không phải lỗi Git. Nếu nhầm mọi mã khác `0` thành thất bại, hook có thể chặn một thao tác hợp lệ.

### 8.3. Kiểm tra nhánh hiện tại có nằm sau remote không

Một hook hoặc script có thể kiểm tra quan hệ tổ tiên bằng:

```bash
git merge-base --is-ancestor origin/main HEAD
rc=$?

case "$rc" in
    0)
        printf '%s\n' "HEAD chứa lịch sử của origin/main."
        ;;
    1)
        printf '%s\n' "HEAD chưa chứa origin/main; hãy cập nhật branch nền."
        exit 1
        ;;
    *)
        printf '%s\n' "Không thể kiểm tra quan hệ lịch sử." >&2
        exit "$rc"
        ;;
esac
```

Điều kiện này chỉ có ý nghĩa nếu `origin/main` đã được fetch gần đây và đúng là branch nền cần kiểm tra. Nếu remote-tracking ref cũ, kết luận có thể không phản ánh trạng thái server hiện tại. Hook `pre-push` không nên giả định ref local luôn mới hơn remote.

## 9. Dùng output máy đọc được trong hook

### 9.1. Kiểm tra staged file bằng porcelain

```bash
git status --porcelain=v1
```

Ví dụ output:

```text
M  src/payment.js
?? tests/payment-timeout.test.js
```

Định dạng porcelain v1 dùng hai ký tự trạng thái ở đầu dòng. Tuy nhiên, nếu cần xử lý tên tệp một cách chắc chắn, hãy thêm `-z` và dùng parser NUL-safe:

```bash
git status --porcelain=v1 -z
```

Đối với hook kiểm tra nội dung sẽ commit, thường chỉ cần các đường dẫn staged:

```bash
git diff --cached --name-only -z
```

Không dùng `git status` human-readable rồi grep từ `modified:` hoặc `new file:` vì output đó không phải giao diện dành cho script.

### 9.2. Lấy commit metadata bằng format tùy chỉnh

```bash
git log -1 --format='%H%n%an%n%ae%n%s'
```

`--format` cho phép chọn trường rõ ràng thay vì parse bảng log mặc định. Nếu trường có thể chứa delimiter, chọn delimiter không nhập nhằng hoặc dùng parser có quy tắc escape phù hợp. Với tên tệp, ưu tiên `-z`.

### 9.3. Tắt pager và màu khi chạy automation

Trong script, nên tránh output phụ thuộc terminal:

```bash
git --no-pager log --no-color --oneline -5
```

Tuy nhiên, tắt pager hoặc màu chỉ làm output dễ đọc hơn; nó không biến output human-readable thành API ổn định. Khi có tùy chọn porcelain hoặc format riêng, vẫn nên dùng chúng.

## 10. Thiết kế thông báo cho người dùng

Hook nên đưa ra thông báo ngắn, cụ thể và có thể hành động:

```text
Commit bị chặn: phát hiện lỗi whitespace trong phần staged.
Hãy chạy git diff --cached --check, sửa các dòng được chỉ ra rồi stage lại.
```

Một thông báo tốt nên nói:

- Thao tác nào bị chặn (commit hoặc push).
- Kiểm tra nào không đạt.
- Phạm vi nào bị ảnh hưởng (tệp, branch hoặc ref nếu có).
- Người dùng cần chạy lệnh hoặc sửa điều gì tiếp theo.

Nên ghi thông báo lỗi và chẩn đoán ra `stderr`. `stdout` có thể dùng cho kết quả chính hoặc thông báo thành công. Không in token, mật khẩu, private key, nội dung secret hoặc toàn bộ môi trường vào log hook.

Với lỗi dài, lưu log vào vị trí phù hợp hoặc cung cấp đường dẫn log; tránh in hàng nghìn dòng làm che mất nguyên nhân chính. Khi cần debug, có thể thêm chế độ verbose được bật có chủ đích.

## 11. Cài đặt và kiểm tra hook

### 11.1. Xác định thư mục hook

Theo mặc định, hook nằm trong thư mục hooks của Git directory. Có thể kiểm tra:

```bash
git rev-parse --git-path hooks
git config --show-origin --get core.hooksPath
```

Nếu `core.hooksPath` được cấu hình, Git dùng thư mục đó thay cho vị trí mặc định. Điều này thường được hook manager hoặc dự án dùng để tổ chức script.

### 11.2. Hook không tự được chia sẻ chỉ vì nằm trong `.git/hooks`

Thư mục `.git/hooks` thuộc Git directory và không được commit như source code thông thường. Vì vậy, clone mới không tự nhận các hook cục bộ trong thư mục này.

Nếu nhóm muốn chia sẻ hook, cần quản lý script trong repository hoặc dùng công cụ hook manager, rồi có bước cài đặt rõ ràng để cấu hình `core.hooksPath` hoặc sao chép hook vào vị trí Git sử dụng. Cần tài liệu hóa cách cài đặt và phiên bản công cụ.

### 11.3. Quyền thực thi và môi trường

Trên Linux/macOS, script hook cần có quyền thực thi và shebang phù hợp, ví dụ `#!/bin/sh`. Trên Windows, Git for Windows thường cung cấp môi trường shell để chạy các hook dạng shell; vẫn cần kiểm tra cách cài đặt, đường dẫn, line ending và runtime thực tế.

Hook nên tránh giả định working directory luôn là thư mục con cụ thể. Có thể xác định root bằng:

```bash
repo_root=$(git rev-parse --show-toplevel) || exit $?
```

Sau đó dùng đường dẫn tuyệt đối hoặc thay đổi thư mục có chủ đích.

### 11.4. Kiểm thử hook trong repository thử nghiệm

Trước khi áp dụng cho cả nhóm:

1. Tạo repository thử nghiệm hoặc branch dùng riêng.
2. Chạy trường hợp hợp lệ để xác nhận hook trả `0`.
3. Tạo trường hợp vi phạm để xác nhận hook trả khác `0` và thao tác bị chặn nếu đó là hook kiểm soát.
4. Kiểm tra trường hợp “không có kết quả” như `git diff --quiet` trả `1` nhưng không phải lỗi.
5. Kiểm tra tên tệp có dấu cách hoặc ký tự đặc biệt nếu script xử lý đường dẫn.
6. Kiểm tra cả shell và hệ điều hành mà nhóm hỗ trợ.
7. Xác nhận hook không in secret và thông báo chỉ rõ cách khắc phục.

Một số phiên bản Git hỗ trợ `git hook run <hook-name>` để chạy hook theo cách Git quản lý; kiểm tra `git hook run --help` trên phiên bản đang dùng. Với hook phụ thuộc ngữ cảnh như `pre-push`, cần cung cấp stdin và argument phù hợp hoặc kiểm thử qua thao tác Git thật trong repository thử nghiệm.

## 12. Hook phía server

Ngoài client-side hook, máy chủ Git có thể chạy server-side hook khi nhận push. Ví dụ:

- `pre-receive`: nhận danh sách ref update qua stdin; trả khác `0` sẽ từ chối toàn bộ push.
- `update`: được gọi cho từng ref; trả khác `0` từ chối cập nhật ref tương ứng.
- `post-receive`: chạy sau khi các ref được cập nhật; không thể hoàn tác việc cập nhật bằng exit status.

Các hook server hữu ích để thực thi chính sách ở nơi tập trung, chẳng hạn cấm force push lên branch chính, kiểm tra commit signature hoặc ghi nhận sự kiện triển khai. Không nên chỉ dựa vào hook local để bảo vệ quy tắc quan trọng, vì người dùng có thể không cài hook hoặc bỏ qua một số hook bằng tùy chọn phù hợp.

## 13. Các lỗi thiết kế thường gặp

### 13.1. Xem mọi mã khác `0` là lỗi

`git diff --quiet` trả `1` khi có khác biệt; `git merge-base --is-ancestor` trả `1` khi quan hệ tổ tiên không đúng. Đây có thể là kết quả logic cần xử lý, không phải lỗi thực thi.

### 13.2. Xem mã `0` là repository sạch

`git status` trả `0` khi đọc trạng thái thành công, kể cả repository có thay đổi. Dùng porcelain output hoặc lệnh kiểm tra riêng.

### 13.3. Parse thông báo terminal

Không grep câu tiếng Anh hoặc câu tiếng Việt từ `git status`, `git push` hay `git commit`. Dùng exit status, porcelain, `-z` và `--format`.

### 13.4. Để pipeline che mất lỗi của Git

Pipeline có thể trả mã của lệnh cuối thay vì lệnh Git. Lưu mã thoát trực tiếp hoặc dùng `pipefail` khi shell hỗ trợ và đã hiểu hành vi.

### 13.5. In thông báo lỗi ra stdout rồi để hook trả `0`

Nếu hook kiểm soát không đạt nhưng vẫn exit `0`, Git tiếp tục thao tác. Hãy dùng `stderr` cho chẩn đoán và trả mã khác `0` khi cần từ chối.

### 13.6. Dùng hook thông báo để cố chặn thao tác

`post-commit` chạy sau khi commit đã hoàn tất. Muốn ngăn commit, kiểm tra phải nằm trong hook trước commit.

### 13.7. Tin rằng mọi thành viên đều chạy local hook

Hook cục bộ có thể không được cài hoặc bị bỏ qua. Chính sách bắt buộc cần được kiểm tra lại ở CI hoặc server-side hook.

## 14. Quy trình xử lý một hook thất bại

Giả sử `git commit` bị chặn bởi `pre-commit`:

**Bước 1: Đọc thông báo và xác định hook**

Xem tên hook trong thông báo hoặc cấu hình `core.hooksPath`. Không vội dùng `--no-verify`.

**Bước 2: Kiểm tra trạng thái repository**

```bash
git status --short --branch
git diff --cached --check
git diff --cached --stat
```

**Bước 3: Chạy lại đúng lệnh kiểm tra**

Ghi nhận exit status và output riêng. Phân biệt lỗi kiểm tra với trạng thái như “có thay đổi” hoặc “không tìm thấy”.

**Bước 4: Sửa dữ liệu hoặc script**

Nếu staged diff vi phạm, sửa tệp, stage lại và chạy kiểm tra. Nếu hook script lỗi, kiểm tra argument, stdin, biến môi trường, quyền thực thi và runtime.

**Bước 5: Kiểm tra mã thoát và thông báo**

Thử trường hợp đạt và không đạt để xác nhận hook trả đúng mã. Đảm bảo thông báo đi ra đúng stream và không phụ thuộc câu chữ của Git.

**Bước 6: Thực hiện lại thao tác Git**

Chỉ commit hoặc push sau khi kiểm tra đã đạt. Nếu buộc phải bỏ qua hook trong tình huống khẩn cấp, chạy kiểm tra thay thế và ghi nhận lý do theo quy trình nhóm.

## 15. Ghi nhớ

- Exit status cho biết lệnh chạy thế nào; stdout/stderr chứa dữ liệu và thông báo.
- Mã `0` thường là thành công, nhưng mã `1` có thể biểu diễn một kết quả logic bình thường.
- `git status` trả `0` không có nghĩa working tree sạch.
- `git diff --quiet`: `0` là không khác biệt, `1` là có khác biệt; cần phân biệt với mã lỗi thực thi.
- Lấy `$?` trong shell hoặc `$LASTEXITCODE` trong PowerShell ngay sau lệnh native cần kiểm tra.
- Không dựa hoàn toàn vào `set -e`; xử lý các mã thoát đặc biệt một cách tường minh.
- Tránh parse output human-readable; dùng `--porcelain`, `-z`, `--format` và các option dành cho script.
- Xử lý tên tệp bằng NUL-safe parser, quote argument và không dùng `eval` với dữ liệu từ repository.
- Hook nhận dữ liệu qua argument, stdin hoặc Git command tùy loại hook; hãy đọc đúng hợp đồng của từng hook.
- Hook kiểm soát trả khác `0` để từ chối thao tác; hook thông báo chạy sau thao tác không thể hủy kết quả đã hoàn tất.
- Local hook không phải cơ chế bảo vệ duy nhất; quy tắc quan trọng nên được kiểm tra thêm ở CI hoặc server.

Một hook tốt không đoán trạng thái Git từ câu chữ trên terminal. Nó gọi đúng lệnh, hiểu mã thoát, đọc dữ liệu theo định dạng dành cho máy và đưa ra thông báo đủ rõ để người dùng biết cách xử lý.
