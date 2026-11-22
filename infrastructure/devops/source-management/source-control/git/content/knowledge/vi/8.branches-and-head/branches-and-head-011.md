# Quy tắc tên nhánh, tên tham chiếu và kiểm tra bằng git check-ref-format

Branch và tag trong Git có tên để người dùng dễ tham chiếu đến commit. Những tên này không phải chuỗi tùy ý: Git áp dụng quy tắc cho *refname* để tránh nhập nhằng khi phân tích revision, reflog, refspec, đường dẫn và cấu trúc lưu trữ. Vì vậy, một tên như `feature/add-login` thường hợp lệ, trong khi `feature//add-login`, `feature name` hoặc `feature/topic.lock` không hợp lệ.

Lệnh `git check-ref-format` giúp kiểm tra một tên tham chiếu có tuân thủ cú pháp Git hay không. Khi kiểm tra tên branch rút gọn, dùng `git check-ref-format --branch`. Lệnh này chỉ xác nhận cú pháp; nó không kiểm tra tên có đang tồn tại, có tuân thủ quy ước của nhóm, có được hosting cho phép hay người dùng có quyền tạo branch hay không.

## 1. Branch, ref và HEAD liên hệ với nhau thế nào?

Trong Git, branch là một loại ref trỏ đến commit. Một branch không phải bản sao thư mục hay một vùng làm việc độc lập; nó là một tên có thể di chuyển khi bạn tạo commit mới hoặc cập nhật branch.

Các namespace ref phổ biến:

| Loại tham chiếu | Ví dụ tên đầy đủ | Ý nghĩa |
|---|---|---|
| Branch local | `refs/heads/main` | Branch `main` trong repository hiện tại |
| Branch local theo nhóm | `refs/heads/feature/add-login` | Branch `feature/add-login` |
| Remote-tracking branch | `refs/remotes/origin/main` | Trạng thái branch `main` mà lần fetch gần nhất từ remote `origin` ghi nhận |
| Tag | `refs/tags/v2.1.0` | Tag `v2.1.0` |
| Notes | `refs/notes/commits` | Namespace Git notes |

Tên branch người dùng thường gõ là phần sau `refs/heads/`. Ví dụ `feature/add-login` tương ứng ref đầy đủ `refs/heads/feature/add-login`.

`HEAD` là tham chiếu đặc biệt cho biết vị trí làm việc hiện tại. Khi đang ở branch bình thường, `HEAD` thường là symbolic ref trỏ đến `refs/heads/<branch>`. Khi detached HEAD, `HEAD` trỏ trực tiếp đến một commit thay vì branch. `HEAD` không phải tên branch mà bạn tạo theo cách thông thường.

Kiểm tra branch hiện tại:

```bash
git branch --show-current
git symbolic-ref --short HEAD
git rev-parse --short HEAD
```

Trong detached HEAD, `git branch --show-current` có thể không in tên branch và `git symbolic-ref` không tìm được symbolic ref; `git rev-parse HEAD` vẫn cho biết commit hiện tại.

## 2. Vì sao Git giới hạn tên ref?

Git dùng refname trong nhiều ngữ cảnh:

- Xác định branch, tag và các ref khác.
- Phân tích biểu thức revision như `HEAD~2`, `main^` hoặc `v1.0.0^{commit}`.
- Xác định reflog với cú pháp `@{...}`.
- Xử lý refspec khi fetch/push.
- Lưu ref trong cấu trúc file/thư mục của repository hoặc backend ref tương ứng.

Một số ký tự có ý nghĩa đặc biệt trong shell hoặc cú pháp Git. Nếu cho phép chúng tùy ý, tên ref có thể bị hiểu nhầm là toán tử revision, dấu phân cách refspec hoặc cú pháp reflog. Quy tắc tên ref giúp các công cụ có thể xử lý tên một cách nhất quán.

## 3. Các quy tắc cú pháp chính của refname

Một refname thông thường phải tuân thủ các điều kiện sau:

1. Không chứa ký tự điều khiển ASCII, dấu cách hoặc các ký tự đặc biệt bị cấm.
2. Không chứa hai dấu chấm liên tiếp `..`.
3. Không kết thúc bằng dấu chấm `.`.
4. Không bắt đầu hoặc kết thúc bằng dấu gạch chéo `/`.
5. Không chứa hai dấu gạch chéo liên tiếp `//`.
6. Không chứa chuỗi `@{`.
7. Không phải chỉ một ký tự `@`.
8. Không có thành phần đường dẫn bắt đầu bằng dấu chấm `.`.
9. Không có thành phần đường dẫn kết thúc bằng `.lock`.
10. Không chứa dấu gạch chéo ngược `\`.

Các ký tự bị cấm trực tiếp gồm:

| Ký tự/nhóm | Lý do cần tránh |
|---|---|
| Ký tự điều khiển ASCII (byte nhỏ hơn `0x20`) và `DEL` (`0x7f`) | Không phù hợp để biểu diễn tên ref và gây khó khăn cho công cụ |
| Dấu cách | Dễ gây nhập nhằng khi truyền đối số trong shell và script |
| `~` | Là toán tử chọn ancestor trong revision syntax |
| `^` | Là toán tử parent trong revision syntax |
| `:` | Có ý nghĩa trong cú pháp refspec và một số biểu thức Git |
| `?`, `*`, `[` | Có thể xung đột với pattern/wildcard và cú pháp pathspec |
| `\` | Gây vấn đề về cách diễn giải đường dẫn và tính tương thích |

Các ví dụ không hợp lệ:

```text
feature//login       # Hai dấu / liên tiếp
/feature/login       # Bắt đầu bằng /
feature/login/       # Kết thúc bằng /
feature..login       # Có ..
feature/login.       # Kết thúc bằng .
feature/login.lock   # Thành phần kết thúc bằng .lock
feature/.private     # Thành phần bắt đầu bằng .
feature/@{backup     # Có chuỗi @{
@                    # Chỉ có một ký tự @
feature/login test   # Có dấu cách
feature/login?       # Có ký tự ?
```

Ngoài các quy tắc trên, Git còn yêu cầu refname đầy đủ thường có ít nhất một dấu `/`. Vì vậy `refs/heads/main` là refname hợp lệ, còn `main` là tên một cấp và chỉ được chấp nhận trong một số chế độ kiểm tra đặc biệt như `--branch` hoặc `--allow-onelevel`.

## 4. Thành phần đường dẫn và quy tắc `.lock`

Refname được phân cấp bằng dấu `/`. Mỗi phần giữa hai dấu `/` là một thành phần đường dẫn.

Ví dụ:

```text
refs/heads/feature/add-login
          |       |   |
          |       |   +-- thành phần: add-login
          |       +------ thành phần: feature
          +-------------- namespace: heads
```

Không thành phần nào được bắt đầu bằng dấu chấm. Do đó `refs/heads/.hidden` và `refs/heads/feature/.private` không hợp lệ.

Không thành phần nào được kết thúc bằng `.lock`. Ví dụ `refs/heads/feature.lock` và `refs/heads/feature/login.lock` không hợp lệ. Quy tắc này tránh xung đột với file lock mà Git dùng khi cập nhật refs.

Git cũng không thể lưu đồng thời một ref là file và một ref khác cần chính đường dẫn đó làm thư mục trong backend ref dạng file. Ví dụ, không nên tạo cả branch `feature` và branch `feature/login`: hai tên có quan hệ tiền tố và có thể xung đột về cấu trúc lưu trữ. Hãy chọn một quy ước phân cấp nhất quán, chẳng hạn luôn đặt branch tính năng dưới `feature/<tên>` thay vì dùng đồng thời `feature` làm branch độc lập.

## 5. Kiểm tra tên ref đầy đủ bằng git check-ref-format

Cú pháp cơ bản:

```bash
git check-ref-format <refname>
```

Ví dụ kiểm tra một branch ref đầy đủ:

```bash
git check-ref-format refs/heads/feature/add-login
```

Kiểm tra tag ref:

```bash
git check-ref-format refs/tags/v2.1.0
```

Kiểm tra remote-tracking ref:

```bash
git check-ref-format refs/remotes/origin/feature/add-login
```

Nếu refname hợp lệ, lệnh kết thúc với exit code `0` và thường không in gì. Nếu không hợp lệ, lệnh trả exit code khác `0` và có thể hiển thị thông báo lỗi.

Trong shell, kiểm tra exit code:

```bash
if git check-ref-format "refs/heads/feature/add-login"; then
    echo "Tên ref hợp lệ"
else
    echo "Tên ref không hợp lệ"
fi
```

Trong PowerShell:

```powershell
git check-ref-format "refs/heads/feature/add-login"
if ($LASTEXITCODE -eq 0) {
    "Tên ref hợp lệ"
} else {
    "Tên ref không hợp lệ"
}
```

Lệnh kiểm tra không tạo branch, không tạo tag và không thay đổi repository.

## 6. Kiểm tra tên branch bằng --branch

Tên branch mà người dùng nhập thường là tên rút gọn, ví dụ `feature/add-login`, không phải full ref `refs/heads/feature/add-login`. Dùng `--branch` để kiểm tra đúng loại tên này:

```bash
git check-ref-format --branch feature/add-login
```

Ví dụ không hợp lệ:

```bash
git check-ref-format --branch "feature//add-login"
git check-ref-format --branch "feature/login.lock"
git check-ref-format --branch "feature/login test"
```

Phân biệt hai cách kiểm tra:

| Lệnh | Đối tượng được kiểm tra |
|---|---|
| `git check-ref-format refs/heads/feature/add-login` | Tên ref đầy đủ trong namespace `refs/heads/` |
| `git check-ref-format --branch feature/add-login` | Tên branch rút gọn |

`--branch` còn hiểu cú pháp tên branch trước đó như `@{-1}` và mở rộng nó thành branch đã checkout trước đó khi có thể. Nếu đang viết script để kiểm tra chuỗi literal do người dùng nhập, cần lưu ý hành vi đặc biệt này; đừng mặc định mọi chuỗi truyền vào luôn được kiểm tra như văn bản nguyên trạng.

## 7. Chuẩn hóa tên ref bằng --normalize

Tùy chọn `--normalize` chuẩn hóa một refname bằng cách bỏ dấu `/` ở đầu và gộp nhiều dấu `/` liên tiếp thành một dấu `/`. Nếu kết quả sau chuẩn hóa hợp lệ, Git in ra tên đã chuẩn hóa.

Ví dụ:

```bash
git check-ref-format --normalize "refs//heads///feature/login"
```

Output:

```text
refs/heads/feature/login
```

Tùy chọn này hữu ích khi muốn kiểm tra hoặc chuẩn hóa một full ref trong công cụ nội bộ. Tuy nhiên, không nên âm thầm sửa tên branch do người dùng nhập mà không thông báo. Nếu người dùng nhập `feature//login`, việc tự đổi thành `feature/login` có thể che giấu lỗi hoặc khiến tên được tạo khác với ý định ban đầu.

Một quy trình an toàn là:

1. Nhận tên branch.
2. Kiểm tra trực tiếp bằng `git check-ref-format --branch`.
3. Nếu không hợp lệ, trả thông báo cụ thể và yêu cầu nhập lại.
4. Chỉ chuẩn hóa khi chính sách ứng dụng cho phép và người dùng hiểu kết quả.

`--normalize` áp dụng cho full refname và không kết hợp với `--branch`.

## 8. Các tùy chọn --allow-onelevel và --refspec-pattern

### --allow-onelevel

Mặc định, refname đầy đủ cần có ít nhất một dấu `/`. `--allow-onelevel` nới điều kiện này để chấp nhận tên chỉ có một cấp:

```bash
git check-ref-format --allow-onelevel release
```

Tùy chọn này hữu ích khi kiểm tra các refname ở ngữ cảnh đặc biệt. Với tên branch thông thường, nên dùng `--branch`; không cần dùng `--allow-onelevel` để kiểm tra tên rút gọn.

### --refspec-pattern

Refspec có thể dùng wildcard `*` để đại diện cho một phần tên ref. Mặc định, ký tự `*` bị cấm trong refname thông thường. `--refspec-pattern` cho phép một dấu `*` trong vị trí pattern:

```bash
git check-ref-format --refspec-pattern "refs/heads/*"
```

Tùy chọn này dành cho kiểm tra pattern refspec, không phải để tạo branch có dấu `*` trong tên. Một pattern chỉ được có một dấu `*` theo quy tắc này.

## 9. Đặt quy ước tên branch cho nhóm

`git check-ref-format` chỉ kiểm tra cú pháp Git. Nhóm vẫn cần quy ước tên để dễ tìm kiếm, lọc branch và tự động hóa.

Một số dạng phổ biến:

| Prefix | Mục đích | Ví dụ |
|---|---|---|
| `feature/` | Phát triển chức năng | `feature/checkout-flow` |
| `fix/` | Sửa lỗi thông thường | `fix/payment-timeout` |
| `hotfix/` | Sửa lỗi khẩn cấp | `hotfix/critical-auth` |
| `release/` | Chuẩn bị phiên bản phát hành | `release/2.4.0` |
| `chore/` | Công việc bảo trì | `chore/update-dependencies` |
| `docs/` | Tài liệu | `docs/git-branch-guide` |

Một số khuyến nghị:

- Dùng chữ thường để giảm khác biệt giữa filesystem phân biệt hoa thường và không phân biệt hoa thường.
- Dùng dấu gạch ngang `-` để phân tách từ trong mỗi thành phần.
- Tránh dấu cách, ký tự có dấu hoặc ký tự đặc biệt nếu branch đi qua nhiều hệ thống và script.
- Dùng prefix ngắn, nhất quán như `feature/`, `fix/`, `release/`.
- Nếu nhóm dùng mã ticket, đặt ở đầu hoặc cuối theo một mẫu duy nhất, ví dụ `feature/PROJ-123-checkout`.
- Tránh nhúng tên người dùng, dữ liệu khách hàng hoặc thông tin nhạy cảm vào tên branch.
- Không tạo branch chỉ khác nhau về chữ hoa/chữ thường nếu nhóm có thành viên dùng Windows hoặc filesystem không phân biệt hoa thường.

Đây là quy ước nhóm, không phải yêu cầu cú pháp bắt buộc của Git. Một tên như `task/123_add-user` có thể hợp lệ về mặt Git nhưng vẫn không đúng naming policy của tổ chức.

## 10. Kiểm tra tên hợp lệ không đồng nghĩa tên chưa tồn tại

`git check-ref-format` không kiểm tra ref đã tồn tại hay chưa. Ví dụ `feature/add-login` có thể hợp lệ về cú pháp nhưng branch cùng tên đã được tạo trên local hoặc remote.

Kiểm tra branch local:

```bash
git show-ref --verify --quiet refs/heads/feature/add-login
```

Kiểm tra remote-tracking branch:

```bash
git show-ref --verify --quiet refs/remotes/origin/feature/add-login
```

Kiểm tra trực tiếp refs đang được remote quảng bá:

```bash
git ls-remote --heads origin feature/add-login
```

Các lệnh trên kiểm tra những phạm vi khác nhau. Remote có thể có branch mà local chưa fetch, vì vậy `git branch --list` hoặc `git show-ref` local không phải bằng chứng rằng branch chưa tồn tại trên server.

Ngay cả khi tên chưa tồn tại, lệnh tạo branch vẫn có thể thất bại vì quyền, branch protection, hook hoặc chính sách hosting. Cần phân biệt cú pháp, trạng thái tồn tại và quyền thao tác.

## 11. Kiểm tra trước khi tạo branch trong script

Một script có thể kiểm tra tên trước khi gọi `git switch -c`. Ví dụ Bash:

```bash
branch_name="feature/PROJ-123-checkout"

if ! git check-ref-format --branch "$branch_name"; then
    echo "Tên branch không hợp lệ: $branch_name" >&2
    exit 1
fi

if git show-ref --verify --quiet "refs/heads/$branch_name"; then
    echo "Branch local đã tồn tại: $branch_name" >&2
    exit 1
fi

git switch -c "$branch_name"
```

Script trên tách hai điều kiện: tên đúng cú pháp và branch local chưa tồn tại. Lệnh `git switch -c` vẫn là bước tạo branch thực tế; nếu remote có branch cùng tên, script cần fetch/kiểm tra remote riêng theo workflow.

Ví dụ PowerShell:

```powershell
$branchName = "feature/PROJ-123-checkout"

git check-ref-format --branch $branchName
if ($LASTEXITCODE -ne 0) {
    throw "Tên branch không hợp lệ: $branchName"
}

git show-ref --verify --quiet "refs/heads/$branchName"
if ($LASTEXITCODE -eq 0) {
    throw "Branch local đã tồn tại: $branchName"
}

git switch -c $branchName
if ($LASTEXITCODE -ne 0) {
    throw "Không thể tạo branch: $branchName"
}
```

Trong script production, cần kiểm tra đầu vào rỗng, xử lý lỗi của Git và tuân thủ naming policy của nhóm. Không dùng chuỗi người dùng nhập để ghép thành lệnh shell không được quote.

## 12. Lưu ý về tính tương thích giữa hệ điều hành và hosting

Git cho phép một số tên khác thường nhưng công cụ khác có thể không xử lý tốt. Đặc biệt:

- **Khác biệt hoa thường:** `Feature/Login` và `feature/login` có thể phân biệt trên một số filesystem nhưng xung đột trên filesystem không phân biệt hoa thường.
- **Tên có ký tự Unicode:** có thể được Git chấp nhận, nhưng cách chuẩn hóa Unicode, encoding hoặc hiển thị có thể khác giữa công cụ và hệ điều hành.
- **Tên có dấu cách hoặc ký tự shell đặc biệt:** nhiều tên như vậy đã bị Git cấm; những ký tự còn được phép vẫn cần quote đúng trong script.
- **Prefix xung đột:** `feature` và `feature/login` có thể xung đột về cấu trúc refs.
- **Quy tắc hosting:** nền tảng có thể áp dụng thêm giới hạn hoặc policy riêng ngoài quy tắc Git.

Để repository hoạt động ổn định trên nhiều môi trường, nên dùng bộ ký tự ASCII đơn giản, chữ thường, số, dấu gạch ngang và dấu `/` phân cấp. Không nên dựa vào khác biệt chữ hoa/chữ thường để tạo hai branch riêng.

## 13. Ví dụ kiểm tra một số tên

Các lệnh sau minh họa cách kiểm tra:

```bash
# Hợp lệ: tên branch có phân cấp.
git check-ref-format --branch "feature/add-login"

# Hợp lệ: tên branch release.
git check-ref-format --branch "release/2.4.0"

# Không hợp lệ: hai dấu slash liên tiếp.
git check-ref-format --branch "feature//add-login"

# Không hợp lệ: thành phần bắt đầu bằng dấu chấm.
git check-ref-format --branch "feature/.private"

# Không hợp lệ: thành phần kết thúc bằng .lock.
git check-ref-format --branch "feature/add-login.lock"

# Kiểm tra full ref.
git check-ref-format "refs/heads/feature/add-login"
```

Trong Bash, có thể kiểm tra nhiều tên và in kết quả:

```bash
for name in "feature/add-login" "feature//bad" "release/2.4.0"; do
    if git check-ref-format --branch "$name" >/dev/null 2>&1; then
        printf 'OK      %s\n' "$name"
    else
        printf 'INVALID %s\n' "$name"
    fi
done
```

Đưa lệnh kiểm tra vào script tạo branch hoặc công cụ nội bộ giúp phát hiện lỗi sớm, trước khi thao tác tạo ref hoặc gọi API hosting.

## 14. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| Tên branch là một chuỗi tùy ý | Branch là refname và phải tuân thủ quy tắc cú pháp Git |
| `main` và `refs/heads/main` là cùng một dạng đầu vào | `main` là tên branch rút gọn; `refs/heads/main` là full refname |
| `git check-ref-format` kiểm tra branch đã tồn tại | Nó chỉ kiểm tra cú pháp tên |
| Tên hợp lệ chắc chắn tạo branch được | Quyền, ref trùng, hook và policy hosting vẫn có thể từ chối |
| Có thể tạo đồng thời branch `feature` và `feature/login` | Hai ref có thể xung đột cấu trúc file/thư mục |
| `--normalize` chỉ kiểm tra, không thay đổi chuỗi | Nó in tên đã chuẩn hóa; không nên âm thầm dùng kết quả nếu chưa có policy |
| `--refspec-pattern` cho phép tạo branch có `*` | Tùy chọn chỉ cho phép wildcard khi kiểm tra pattern refspec |
| Git phân biệt hoa thường giống nhau trên mọi máy | Filesystem và hosting có thể xử lý khác nhau; nên dùng chữ thường nhất quán |
| `HEAD` là một branch bình thường | `HEAD` là tham chiếu đặc biệt, có thể symbolic hoặc detached |

## 15. Ghi nhớ

Branch và tag là các ref trỏ đến object. Branch local nằm trong namespace `refs/heads/`, remote-tracking branch trong `refs/remotes/` và tag trong `refs/tags/`. Tên branch rút gọn như `feature/add-login` khác với full ref `refs/heads/feature/add-login`; dùng `git check-ref-format --branch` để kiểm tra dạng rút gọn và `git check-ref-format <full-ref>` để kiểm tra tên đầy đủ.

Refname không được chứa các ký tự đặc biệt bị cấm, khoảng trắng hoặc ký tự điều khiển; không có `..`, `@{`, `//`, slash ở đầu/cuối, thành phần bắt đầu bằng dấu chấm hoặc kết thúc bằng `.lock`. Dùng `--normalize` để xem tên full ref sau chuẩn hóa, `--allow-onelevel` cho ref một cấp và `--refspec-pattern` khi kiểm tra wildcard refspec.

Cuối cùng, cú pháp hợp lệ không bảo đảm branch chưa tồn tại hoặc người dùng có quyền tạo. Hãy kiểm tra riêng ref local/remote và naming policy. Dùng tên ngắn, chữ thường, có phân cấp nhất quán để giảm lỗi khi cộng tác qua nhiều hệ điều hành và dịch vụ lưu trữ.
