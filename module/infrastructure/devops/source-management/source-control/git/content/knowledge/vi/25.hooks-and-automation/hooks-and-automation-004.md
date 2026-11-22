# Mã thoát, tham số, đầu vào và môi trường thực thi của hook

Git hook là chương trình được Git gọi tại những thời điểm nhất định, chẳng hạn trước khi tạo commit, trước khi push hoặc sau khi nhận cập nhật từ remote. Để viết hook đúng, cần hiểu bốn phần của hợp đồng thực thi: **mã thoát**, **tham số dòng lệnh**, **dữ liệu qua standard input (stdin)** và **các biến môi trường** mà Git cung cấp.

Các hook không dùng chung một bộ tham số. Mỗi hook có thời điểm chạy và hợp đồng riêng. Một số hook nhận đường dẫn hoặc tên remote qua `$1`, `$2`; một số hook đọc danh sách ref từ stdin; một số hook không nhận tham số nào. Mã thoát cũng có ý nghĩa khác nhau tùy hook: hook chạy trước thao tác có thể từ chối thao tác, còn hook chạy sau thao tác thường chỉ phục vụ thông báo hoặc tác vụ phụ.

## 1. Git gọi hook khi nào và ở đâu?

Git có nhiều hook phía client và phía server. Hook phía client chạy trên máy người dùng khi họ thực hiện các thao tác như commit, checkout, merge, rebase hoặc push. Hook phía server chạy trên máy nhận push, thường trong repository bare.

Một số hook thường gặp:

| Hook | Thời điểm | Mục đích thường dùng |
|---|---|---|
| `pre-commit` | Trước khi tạo commit | Kiểm tra staged diff, lint hoặc test nhanh |
| `prepare-commit-msg` | Sau khi Git tạo nội dung ban đầu cho commit message, trước khi mở editor | Chuẩn bị hoặc điều chỉnh message theo ngữ cảnh |
| `commit-msg` | Sau khi người dùng soạn message, trước khi commit được tạo | Kiểm tra định dạng commit message |
| `post-commit` | Sau khi commit thành công | Gửi thông báo hoặc ghi nhận sự kiện |
| `pre-rebase` | Trước khi rebase bắt đầu | Kiểm tra có cho phép rebase branch hay không |
| `post-checkout` | Sau khi checkout hoặc switch thành công | Cập nhật môi trường làm việc hoặc dependency |
| `post-merge` | Sau khi merge thành công | Chạy tác vụ cần thiết sau tích hợp |
| `pre-push` | Trước khi Git gửi ref lên remote | Kiểm tra commit sắp push hoặc chạy test |
| `pre-receive` | Trên server, trước khi cập nhật các ref nhận được | Kiểm tra toàn bộ push và từ chối nếu vi phạm chính sách |
| `update` | Trên server, trước khi cập nhật từng ref | Kiểm tra riêng từng branch hoặc tag |
| `post-receive` | Trên server, sau khi cập nhật ref thành công | Kích hoạt deploy, thông báo hoặc xử lý hậu kỳ |

Hook được tìm trong thư mục hooks của repository hoặc thư mục do `core.hooksPath` chỉ định. Trong thư mục mặc định `.git/hooks`, các file mẫu thường có hậu tố `.sample`; Git không tự chạy những file mẫu đó. Hook cần có đúng tên hook và quyền thực thi phù hợp với môi trường.

## 2. Mã thoát của hook có ý nghĩa gì?

Một chương trình hook kết thúc bằng mã thoát (*exit status*). Theo quy ước shell phổ biến:

- `0`: chương trình kết thúc thành công.
- Khác `0`: chương trình báo lỗi hoặc từ chối điều kiện.

Git diễn giải mã thoát theo hợp đồng của từng hook. Với nhiều hook kiểm tra chạy **trước** thao tác, mã khác `0` khiến Git dừng thao tác. Ví dụ, `pre-commit` trả `1` thì commit không được tạo; `pre-push` trả khác `0` thì lần push bị hủy.

Với hook chạy **sau** thao tác, mã khác `0` không thể tự hoàn tác điều đã xảy ra. Ví dụ, `post-commit` chạy sau khi commit đã được tạo; `post-receive` chạy sau khi server đã cập nhật ref. Hook có thể ghi lỗi hoặc cảnh báo, nhưng không thể dùng exit code để từ chối ngược một commit hoặc push đã hoàn tất.

Không nên áp dụng máy móc quy tắc “non-zero luôn hủy Git command” cho mọi hook. Hãy đọc hợp đồng của hook cụ thể, nhất là những hook server có hành vi khác nhau theo từng giai đoạn.

### Hook kiểm tra trước thao tác

Ví dụ `pre-commit` chạy kiểm tra whitespace trên nội dung đã stage:

```sh
#!/bin/sh

if git diff --cached --check; then
    exit 0
fi

echo "Commit bị dừng: hãy sửa lỗi whitespace trong staged changes." >&2
exit 1
```

Nếu `git diff --cached --check` phát hiện lỗi, hook trả `1`; Git không tạo commit. Người dùng sửa nội dung, stage lại và chạy commit lần nữa.

### Hook chạy sau thao tác

Ví dụ `post-commit` ghi thông báo:

```sh
#!/bin/sh

echo "Commit đã được tạo: $(git rev-parse --short HEAD)"
exit 0
```

Hook này không kiểm soát việc commit có được tạo hay không vì nó chỉ chạy sau khi commit thành công. Nếu nó thất bại, commit vẫn tồn tại.

## 3. Tham số dòng lệnh và stdin là hai kênh khác nhau

Git truyền dữ liệu cho hook theo hai cách:

1. **Argument vector:** tham số nằm sau tên chương trình hook, có thể đọc bằng `$1`, `$2`, `$3` trong shell.
2. **Standard input:** dữ liệu được Git ghi vào stdin của tiến trình hook; script đọc bằng `read`, vòng lặp hoặc chương trình xử lý dữ liệu.

Không phải hook nào cũng dùng cả hai. Ví dụ `pre-push` nhận tên remote và URL bằng tham số, đồng thời nhận danh sách ref qua stdin. Nếu script chỉ đọc `$1` và `$2`, nó sẽ không biết commit/ref nào đang được đẩy. Ngược lại, không nên chờ stdin ở hook không cung cấp dữ liệu qua kênh này.

Một dòng minh họa về cách đọc tham số:

```sh
remote_name=$1
remote_url=$2
```

Một ví dụ đọc stdin:

```sh
while read old_oid new_oid ref_name; do
    printf 'Ref %s: %s -> %s\n' "$ref_name" "$old_oid" "$new_oid"
done
```

Định dạng chính xác của từng dòng phụ thuộc hook. Không dùng ví dụ tổng quát này thay cho đặc tả đầu vào của hook đang triển khai.

## 4. Các tham số và đầu vào của hook phía client thường dùng

### pre-commit

`pre-commit` không nhận tham số dòng lệnh chuẩn và không có payload stdin do Git định nghĩa. Hook thường kiểm tra trạng thái index bằng các lệnh như:

```bash
git diff --cached --name-only
git diff --cached --check
git diff --cached
```

Lưu ý hook cần kiểm tra nội dung **đã stage**, vì đó mới là nội dung dự kiến đưa vào commit. Kiểm tra riêng working tree bằng `git diff` có thể bỏ sót thay đổi đang nằm trong index.

### prepare-commit-msg

Hook này nhận các tham số:

| Tham số | Ý nghĩa |
|---|---|
| `$1` | Đường dẫn đến file chứa commit message ban đầu |
| `$2` | Nguồn tạo message, nếu có; ví dụ `message`, `template`, `merge`, `squash` hoặc `commit` |
| `$3` | Mã commit, khi nguồn là một commit phù hợp |

Ví dụ kiểm tra đầu vào:

```sh
#!/bin/sh

message_file=$1
message_source=${2-}
source_commit=${3-}

printf 'Message file: %s\n' "$message_file"
printf 'Source: %s\n' "$message_source"
printf 'Source commit: %s\n' "$source_commit"
```

Hook có thể sửa file message được truyền vào. Nó chạy trước editor nên người dùng vẫn có thể chỉnh sửa nội dung sau đó. Nếu muốn kiểm tra message cuối cùng sau khi người dùng nhập, dùng `commit-msg`.

### commit-msg

Hook này nhận một tham số:

- `$1`: đường dẫn đến file chứa commit message.

Ví dụ kiểm tra quy ước message đơn giản:

```sh
#!/bin/sh

message_file=$1

if grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([^)]+\))?: .+' "$message_file"; then
    exit 0
fi

echo "Commit message phải có dạng type(scope): subject hoặc type: subject." >&2
exit 1
```

Nếu hook trả khác `0`, commit bị từ chối và người dùng có thể sửa message rồi thử lại. Hãy điều chỉnh biểu thức kiểm tra theo quy ước thực tế của nhóm; ví dụ trên chỉ minh họa một dạng Conventional Commits rút gọn.

### post-checkout

Hook nhận ba tham số:

| Tham số | Ý nghĩa |
|---|---|
| `$1` | Mã commit trước checkout |
| `$2` | Mã commit sau checkout |
| `$3` | `1` nếu checkout/switch branch; `0` nếu checkout đường dẫn/tệp |

Ví dụ:

```sh
#!/bin/sh

old_head=$1
new_head=$2
branch_checkout=$3

if [ "$branch_checkout" = "1" ]; then
    echo "Đã chuyển branch đến $new_head"
fi
```

Hook này chạy sau checkout thành công. Nó có thể dùng để thông báo hoặc cập nhật cache, nhưng không thể từ chối thao tác checkout đã hoàn tất.

### post-merge

Hook nhận một tham số:

- `$1` là `1` nếu merge được thực hiện với tùy chọn squash; ngược lại là `0`.

Ví dụ:

```sh
#!/bin/sh

if [ "$1" = "1" ]; then
    echo "Merge theo chế độ squash đã hoàn tất."
else
    echo "Merge đã hoàn tất."
fi
```

Hook chạy sau khi merge thành công. Nó không thể làm merge bị từ chối bằng cách trả mã khác `0`.

### pre-rebase

Hook nhận upstream làm tham số đầu tiên và branch đang rebase làm tham số thứ hai nếu được chỉ định. Nếu không chỉ định branch, Git có thể không truyền tham số thứ hai.

```sh
#!/bin/sh

upstream=$1
branch=${2-}

printf 'Rebase upstream: %s\n' "$upstream"
printf 'Branch: %s\n' "$branch"
```

Hook có thể trả mã khác `0` để từ chối bắt đầu rebase, ví dụ khi branch đang nằm trong danh sách không được rebase theo quy trình của nhóm.

## 5. pre-push: tham số remote và danh sách ref qua stdin

`pre-push` là ví dụ điển hình cho hook dùng đồng thời hai kênh đầu vào.

Git gọi hook với:

- `$1`: tên remote, ví dụ `origin`.
- `$2`: URL của remote.
- stdin: một dòng cho mỗi ref được push, gồm bốn trường cách nhau bởi dấu cách:

```text
<local-ref> <local-object-name> <remote-ref> <remote-object-name>
```

Ví dụ:

```text
refs/heads/feature/login 1234567890abcdef refs/heads/feature/login 0987654321abcdef
refs/tags/v1.2.0 abcdef1234567890 refs/tags/v1.2.0 0000000000000000000000000000000000000000
```

Trong đó:

- `local-ref`: ref phía local đang được gửi.
- `local-object-name`: object ID phía local; độ dài phụ thuộc định dạng hash của repository.
- `remote-ref`: ref đích ở remote.
- `remote-object-name`: object ID hiện có ở remote; chuỗi toàn số 0 biểu thị ref đích chưa tồn tại, thường là push tạo mới.

Nếu local object ID là chuỗi toàn số 0, đó là thao tác xóa ref. Hook nên xử lý riêng trường hợp này thay vì cố đọc object không tồn tại.

Ví dụ hook ghi nhận các ref được push và từ chối nếu có thao tác xóa branch chính. Để không cố định độ dài OID theo SHA-1, script nhận diện chuỗi chỉ gồm các số `0`:

```sh
#!/bin/sh

remote_name=$1
remote_url=$2

echo "Kiểm tra push tới $remote_name ($remote_url)"

while read local_ref local_oid remote_ref remote_oid; do
    case "$local_oid" in
        *[!0]*|'') ;;
        *)
            if [ "$remote_ref" = "refs/heads/main" ]; then
                echo "Không cho phép xóa branch main." >&2
                exit 1
            fi
            ;;
    esac
done

exit 0
```

Đây chỉ là kiểm tra phía client trên máy người dùng. Nó có thể bị bỏ qua hoặc không được cài ở clone khác; quy tắc bảo vệ branch chính thức phải được thực thi ở server hoặc nền tảng lưu trữ.

## 6. Các tham số và đầu vào của hook phía server

Hook phía server được cấu hình trên repository nhận push. Các hook này là nơi phù hợp để thực thi chính sách chung vì mọi client push đến repository đều đi qua server.

### pre-receive

`pre-receive` không nhận tham số dòng lệnh chuẩn. Git gửi qua stdin một dòng cho mỗi ref được đề nghị cập nhật:

```text
<old-oid> <new-oid> <ref-name>
```

Ví dụ:

```text
1111111111111111111111111111111111111111 2222222222222222222222222222222222222222 refs/heads/main
0000000000000000000000000000000000000000 3333333333333333333333333333333333333333 refs/heads/feature/search
```

`old-oid` là object ID hiện tại của ref; `new-oid` là object ID được đề nghị. Chuỗi số 0 ở `old-oid` biểu thị ref mới. Chuỗi số 0 ở `new-oid` biểu thị thao tác xóa ref.

Nếu `pre-receive` trả mã khác `0`, toàn bộ push bị từ chối, kể cả khi push chứa nhiều ref. Hook này phù hợp để kiểm tra chính sách áp dụng đồng thời cho cả lần push.

### update

Hook `update` được gọi riêng cho từng ref và nhận ba tham số:

| Tham số | Ý nghĩa |
|---|---|
| `$1` | Tên ref đang được cập nhật, ví dụ `refs/heads/main` |
| `$2` | Object ID hiện tại của ref |
| `$3` | Object ID mới được đề nghị |

Ví dụ kiểm tra không cho cập nhật trực tiếp branch release:

```sh
#!/bin/sh

ref_name=$1
old_oid=$2
new_oid=$3

case "$ref_name" in
    refs/heads/release/*)
        echo "Branch release chỉ được cập nhật qua quy trình phát hành." >&2
        exit 1
        ;;
esac

exit 0
```

Nếu hook `update` trả khác `0`, ref tương ứng bị từ chối. Các ref khác trong cùng lần push có thể vẫn được cập nhật nếu không bị hook hoặc chính sách khác từ chối. Điều này khác với `pre-receive`, vốn từ chối toàn bộ push.

### post-receive

`post-receive` không nhận tham số dòng lệnh chuẩn. Stdin chứa danh sách các ref đã được cập nhật thành công, cùng định dạng ba trường như `pre-receive`:

```text
<old-oid> <new-oid> <ref-name>
```

Hook này thường dùng để gửi thông báo, ghi audit hoặc kích hoạt hệ thống triển khai. Vì ref đã được cập nhật trước khi hook chạy, mã thoát khác `0` không thể từ chối push đã thành công.

## 7. Các biến môi trường Git cung cấp cho hook

Hook được chạy trong ngữ cảnh Git nên thường kế thừa các biến môi trường giúp xác định repository, index, editor và thông tin commit. Một số biến thường gặp:

| Biến | Ý nghĩa khái quát |
|---|---|
| `GIT_DIR` | Đường dẫn đến thư mục metadata Git đang dùng |
| `GIT_WORK_TREE` | Đường dẫn working tree nếu được thiết lập tường minh |
| `GIT_INDEX_FILE` | Đường dẫn index file đang được dùng; có thể không phải `.git/index` mặc định |
| `GIT_PREFIX` | Tiền tố đường dẫn liên quan đến thư mục hiện tại khi Git được gọi từ bên trong repository |
| `GIT_EDITOR` | Editor Git sẽ dùng cho thao tác cần chỉnh sửa nội dung |
| `GIT_AUTHOR_NAME`, `GIT_AUTHOR_EMAIL` | Biến môi trường có thể được thiết lập để xác định danh tính tác giả commit |
| `GIT_COMMITTER_NAME`, `GIT_COMMITTER_EMAIL` | Biến môi trường có thể được thiết lập để xác định danh tính người ghi commit |

Các biến định danh ở bảng trên có thể được kế thừa từ môi trường của tiến trình gọi; không nên giả định Git luôn tự đặt chúng cho mọi hook. Git còn có thể cung cấp biến thời gian, cấu hình hoặc biến riêng cho một luồng thao tác. Không nên giả định mọi biến luôn tồn tại; hãy kiểm tra trước khi sử dụng và ưu tiên các lệnh `git rev-parse` hoặc `git config` để lấy thông tin repository cần thiết.

Ví dụ in một số thông tin phục vụ chẩn đoán:

```sh
#!/bin/sh

printf 'GIT_DIR=%s\n' "${GIT_DIR-}"
printf 'GIT_WORK_TREE=%s\n' "${GIT_WORK_TREE-}"
printf 'GIT_INDEX_FILE=%s\n' "${GIT_INDEX_FILE-}"
printf 'Repository root: '
git rev-parse --show-toplevel 2>/dev/null || echo "không có working tree"
```

Trong repository bare, `git rev-parse --show-toplevel` không có working tree để trả về. Hook server không nên giả định luôn tồn tại thư mục source được checkout.

## 8. Thư mục làm việc và gọi Git từ bên trong hook

Ngữ cảnh thư mục hiện tại phụ thuộc loại hook và repository. Nhiều hook phía client chạy từ thư mục gốc working tree; một số hook trong repository bare hoặc hook nhận push chạy trong thư mục Git. Vì vậy, đừng giả định `pwd` luôn là thư mục project có source code.

Khi cần lấy root của working tree, có thể dùng:

```sh
repo_root=$(git rev-parse --show-toplevel) || exit 1
```

Khi cần truy cập một tệp trong repository, dùng đường dẫn được tính từ root thay vì dựa vào thư mục hiện tại:

```sh
config_file="$repo_root/.editorconfig"
```

### Gọi Git trong repository khác

Git truyền các biến môi trường như `GIT_DIR`, `GIT_WORK_TREE` hoặc `GIT_INDEX_FILE` vào hook để các lệnh Git con tiếp tục làm việc với repository hiện tại. Nếu hook muốn chạy lệnh trong một repository **khác**, những biến này có thể khiến Git hiểu nhầm ngữ cảnh.

Có thể xóa các biến môi trường repository-local trước khi gọi Git ở repository khác:

```sh
for var in $(git rev-parse --local-env-vars); do
    unset "$var"
done

git -C /path/to/another/repository status
```

Chỉ làm điều này khi thực sự muốn chuyển sang repository khác. Nếu vẫn đang thao tác với repository hiện tại, giữ nguyên môi trường Git mà hook nhận được.

## 9. Cấu hình vị trí hook bằng core.hooksPath

Mặc định, Git tìm hook trong thư mục hooks của repository. Có thể xem vị trí mặc định:

```bash
git rev-parse --git-path hooks
```

Có thể cấu hình thư mục hook khác bằng `core.hooksPath`:

```bash
git config --local core.hooksPath .githooks
```

Ví dụ repository có cấu trúc:

```text
project/
├── .githooks/
│   ├── pre-commit
│   └── commit-msg
├── src/
└── .git/
```

Thư mục `.githooks` có thể được commit để chia sẻ nội dung hook trong repository. Tuy nhiên, cấu hình `core.hooksPath` là cấu hình local của từng clone; thành viên mới cần chạy lệnh thiết lập hoặc dùng script bootstrap của dự án.

Kiểm tra cấu hình và nguồn:

```bash
git config --show-origin --get core.hooksPath
```

Hook phải có tên đúng, nội dung có thể chạy trong môi trường shell tương ứng và quyền thực thi phù hợp. Trên Unix, thường cần:

```bash
chmod +x .githooks/pre-commit
chmod +x .githooks/commit-msg
```

Với Windows, Git for Windows cung cấp môi trường thực thi hook tương thích; cần kiểm tra shell và định dạng script mà nhóm chọn. Tránh dùng đường dẫn interpreter hoặc lệnh chỉ tồn tại trên một máy nếu hook cần chạy cho cả nhóm.

## 10. Hook có thể bị bỏ qua và không phải ranh giới bảo mật

Một số lệnh hỗ trợ tùy chọn bỏ qua hook phía client:

```bash
git commit --no-verify
git push --no-verify
```

`git commit --no-verify` bỏ qua các hook `pre-commit` và `commit-msg`; nó không có nghĩa mọi hook commit đều bị bỏ qua. `git push --no-verify` bỏ qua `pre-push`. Ngoài ra, người dùng có quyền trên máy có thể thay đổi hoặc không cài hook local.

Vì vậy:

- Dùng hook phía client để tăng phản hồi sớm, giúp người phát triển phát hiện lỗi ngay trên máy.
- Dùng CI, branch protection hoặc hook phía server để thực thi điều kiện bắt buộc đối với repository chung.
- Không đặt bí mật hoặc thông tin xác thực quan trọng trong hook được commit vào repository; người dùng có thể đọc nội dung đó.
- Ghi rõ cách cài hook và cách cập nhật phiên bản hook trong tài liệu dự án.

Hook server cũng cần được triển khai và quản trị cẩn thận; quyền truy cập trực tiếp vào máy chủ hoặc cấu hình Git hosting có thể ảnh hưởng chính sách thực thi.

## 11. Những lỗi thường gặp khi viết hook

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Hook luôn thất bại | Script kết thúc với mã khác `0` hoặc một lệnh trung gian trả lỗi | Kiểm tra từng lệnh và chỉ `exit 0` khi tất cả điều kiện đạt |
| `pre-commit` không thấy thay đổi | Script dùng `git diff` thay vì diff của index | Dùng `git diff --cached` để kiểm tra nội dung sẽ commit |
| `pre-push` không biết branch nào được gửi | Chỉ đọc `$1`, `$2` mà bỏ qua stdin | Đọc từng dòng bốn trường từ stdin theo hợp đồng pre-push |
| Script đọc sai tham số | Giả định mọi hook nhận cùng số đối số | Tra hợp đồng của hook cụ thể và kiểm tra `${2-}` khi tham số có thể vắng mặt |
| Hook gọi Git nhầm repository | Biến môi trường Git từ tiến trình cha còn hiệu lực | Giữ môi trường cho repo hiện tại; unset local Git env trước khi gọi repo khác |
| Hook không chạy | Sai tên file, sai `core.hooksPath`, thiếu quyền thực thi hoặc chỉ có file `.sample` | Kiểm tra đường dẫn hook, tên và quyền |
| Hook local bị vượt qua | Người dùng dùng `--no-verify` hoặc không cài hook | Đưa điều kiện bắt buộc lên CI/server-side policy |
| `post-*` hook thất bại nhưng thao tác đã xong | Hook chạy sau khi Git hoàn tất hành động | Thiết kế xử lý hậu kỳ có retry/logging; không kỳ vọng exit code hoàn tác thao tác |

Khi debug, nên ghi log ra stderr để tránh làm nhiễu output được các công cụ khác parse. Tránh in token, mật khẩu hoặc toàn bộ biến môi trường vào log.

## 12. Quy trình thiết kế và kiểm thử hook

Trước khi viết hook, xác định rõ:

1. Hook chạy ở phía client hay server?
2. Hook chạy trước hay sau thao tác cần kiểm soát?
3. Git truyền những tham số nào qua argument vector?
4. Có dữ liệu nào được gửi qua stdin và định dạng từng dòng ra sao?
5. Biến môi trường nào cần dùng, biến nào có thể không tồn tại?
6. Mã thoát nào cho phép tiếp tục và mã nào từ chối thao tác?
7. Hook cần chạy trên Windows, macOS, Linux hay môi trường server cụ thể nào?
8. Có thể bỏ qua hook không, và điều kiện bắt buộc có được kiểm tra ở CI/server không?

Một cách kiểm thử đơn giản là tạo repository thử nghiệm, cài hook vào đúng vị trí, thực hiện thao tác tương ứng và kiểm tra cả trường hợp thành công lẫn thất bại. Ví dụ với `commit-msg`, thử một message đúng mẫu và một message sai mẫu; với `pre-push`, thử push branch mới, cập nhật branch hiện có và xóa ref trong repository thử nghiệm.

Không nên kiểm thử hook có khả năng từ chối push hoặc cập nhật ref trực tiếp trên repository production. Dùng repository thử nghiệm hoặc remote riêng để xác minh tham số, stdin, mã thoát và hành vi thực tế.

## 13. Ghi nhớ

Hợp đồng hook gồm bốn phần cần kiểm tra riêng: thời điểm thực thi, tham số dòng lệnh, dữ liệu stdin và biến môi trường. `pre-commit` thường kiểm tra index; `commit-msg` nhận đường dẫn file message; `pre-push` nhận remote name/URL qua `$1` và `$2`, đồng thời nhận danh sách ref qua stdin; `pre-receive` nhận các cập nhật ref qua stdin; `update` nhận tên ref cùng old/new OID qua ba tham số.

Mã `0` thường cho phép hook hoàn tất; mã khác `0` có thể từ chối thao tác nếu hook chạy trước và hợp đồng quy định như vậy. Hook chạy sau thao tác không thể dùng mã lỗi để đảo ngược hành động đã hoàn tất. Cuối cùng, hook local giúp kiểm tra sớm nhưng có thể bị bỏ qua; chính sách bắt buộc cần được thực thi ở CI hoặc phía server.
