# Tạo bản vá commit bằng git format-patch

Git có thể đóng gói các commit thành một chuỗi bản vá để gửi cho người khác review hoặc chuyển thay đổi giữa các repository mà không cần push trực tiếp lên remote chung. Lệnh **git format-patch** tạo các file theo định dạng email (mbox-style) chứa thông tin commit, thông điệp và phần diff. Người nhận có thể áp dụng chuỗi đó bằng **git am**, qua đó tạo lại các commit với nội dung và thông tin tác giả được giữ lại.

Cách làm này hữu ích khi cộng tác qua email, gửi patch cho maintainer, làm việc trong môi trường không có quyền push hoặc chuyển một nhóm commit đã chọn sang repository khác. Điều quan trọng là chọn đúng revision range, giữ thứ tự patch và xác minh patch được tạo từ các commit đã hoàn tất.

## 1. git format-patch dùng để làm gì?

`git format-patch` biến một hoặc nhiều commit thành các bản vá độc lập. Mỗi commit thông thường tạo một file patch riêng, chứa:

- Tiêu đề email được tạo từ commit subject.
- Thông tin tác giả và ngày tác giả.
- Commit message, gồm subject và phần mô tả.
- Diff thể hiện thay đổi của commit so với parent.
- Thông tin bổ sung như diffstat và chữ ký phiên bản Git, tùy tùy chọn.

Ví dụ, một nhánh có ba commit mới so với `main`:

```text
A---B---C---D---E
    ^           ^
   main        topic

Các commit cần gửi: C, D, E
```

Chạy:

```bash
git format-patch main..topic
```

Git tạo ba file tương ứng với ba commit trong dải. Tên file thường có số thứ tự và subject đã được chuẩn hóa, ví dụ:

```text
0001-Add-input-validation.patch
0002-Fix-parser-boundary.patch
0003-Document-new-option.patch
```

Các file này không phải bản sao toàn bộ repository. Chúng là các thông điệp patch có thể được đọc, review và áp dụng bằng Git.

`git format-patch` chỉ đóng gói commit đã tồn tại trong lịch sử. Nó không tự đưa thay đổi chưa commit trong working tree hoặc index vào patch series. Nếu có thay đổi chưa commit, hãy kiểm tra và commit chúng trước, hoặc dùng một cơ chế diff khác nếu mục tiêu là gửi thay đổi chưa tạo commit.

## 2. Chọn đúng revision range

Cách dùng phổ biến nhất là chỉ định commit nền và commit cuối:

```bash
git format-patch <base>..<tip>
```

Range `<base>..<tip>` chọn các commit reachable từ `<tip>` nhưng không reachable từ `<base>`. Nói cách khác, Git lấy các commit có trong lịch sử tip mà chưa có trong lịch sử base.

Ví dụ:

```bash
git format-patch origin/main..HEAD
```

Lệnh tạo patch cho các commit trên HEAD chưa có trong `origin/main`. Điều này giả định `origin/main` đã được fetch gần đây và là base mà bạn muốn so sánh.

Trước khi tạo patch, nên xem danh sách commit:

```bash
git fetch origin
git log --oneline --decorate --reverse origin/main..HEAD
```

`--reverse` giúp hiển thị commit theo thứ tự cũ trước, mới sau. Bạn có thể xác minh base có phải tổ tiên của tip không:

```bash
git merge-base --is-ancestor origin/main HEAD
```

Nếu lệnh trả mã thoát 0, `origin/main` là ancestor của HEAD. Nếu không, lịch sử đã phân kỳ hoặc base không nằm trong lịch sử của HEAD; hãy xem graph và chọn lại range trước khi đóng gói.

Một số cách chọn commit thường dùng:

| Lệnh | Phạm vi |
|---|---|
| `git format-patch -1 HEAD` | Tạo patch cho commit HEAD |
| `git format-patch -3` | Tạo patch cho ba commit mới nhất từ HEAD |
| `git format-patch base..HEAD` | Tạo patch cho các commit có trong HEAD nhưng không có trong base |
| `git format-patch --root HEAD` | Tạo patch cho lịch sử reachable từ HEAD, bao gồm cả root commit |

Cẩn thận với revision range. `A..B` không có nghĩa là “mọi commit nằm giữa A và B trên một đường thẳng” trong mọi đồ thị phân nhánh; nó là phép chọn theo khả năng reachable. Nếu nhánh có merge, tập commit có thể bao gồm commit từ nhánh phụ.

Không nhầm `A..B` với `A...B`. Dạng ba chấm chọn symmetric difference giữa hai phía, thường không phải tập patch bạn muốn gửi từ một branch topic dựa trên base.

## 3. Patch được xuất theo thứ tự nào?

Khi tạo một chuỗi patch từ revision range, Git xuất các commit theo thứ tự phù hợp để áp dụng từ commit cũ tới commit mới. Điều này quan trọng vì commit sau có thể phụ thuộc vào thay đổi của commit trước.

Ví dụ lịch sử:

```text
A---B---C---D---E
    ^
   base

Thứ tự patch:
1. C
2. D
3. E
```

Có thể kiểm tra thứ tự dự kiến trước khi tạo:

```bash
git log --oneline --reverse base..HEAD
```

Sau khi chạy `git format-patch`, tên file thường được đánh số `0001`, `0002`, `0003` theo thứ tự áp dụng. Khi chuyển patch cho người nhận, hãy giữ nguyên các file và số thứ tự. Không tự sắp xếp theo subject hoặc ngày sửa file.

Nếu dùng `--stdout`, Git ghi các thông điệp patch liên tiếp vào một luồng mbox. Thứ tự trong luồng cũng là thứ tự áp dụng.

## 4. Tạo patch cho một commit hoặc một nhóm commit

Để xuất commit mới nhất:

```bash
git format-patch -1 HEAD
```

Để xuất năm commit gần nhất:

```bash
git format-patch -5
```

Để xuất một nhóm commit trên nhánh topic so với base:

```bash
git format-patch origin/main..feature/login
```

Nếu muốn xuất patch vào thư mục riêng, dùng `-o` hoặc `--output-directory`:

```bash
git format-patch -o patches origin/main..feature/login
```

Git tạo các file patch trong thư mục `patches`. Nên dùng thư mục mới hoặc thư mục đã được dọn đúng cách để tránh nhầm file cũ với patch của lần tạo hiện tại.

Kiểm tra danh sách file sau khi tạo:

```bash
git status --short
```

Nếu thư mục patch nằm bên trong repository và chưa được ignore, các file patch có thể xuất hiện như untracked files. Điều đó bình thường; patch là artifact được tạo ra, không tự động trở thành commit của dự án.

## 5. Gộp chuỗi patch vào một file bằng --stdout

Nếu muốn tạo một file mbox duy nhất thay vì nhiều file riêng, dùng `--stdout`:

```bash
git format-patch --stdout origin/main..HEAD > feature-login.mbox
```

File `feature-login.mbox` chứa các thông điệp patch liên tiếp. Người nhận có thể áp dụng cả chuỗi bằng:

```bash
git am feature-login.mbox
```

Cách này thuận tiện khi gửi một artifact duy nhất hoặc lưu trữ một patch series. Đừng dùng `git apply` với file mbox như thể nó là một unified diff đơn giản; `git am` hiểu cấu trúc email và metadata commit của format-patch.

Nếu cần xem nội dung file trước khi gửi, có thể mở bằng trình soạn thảo văn bản hoặc xem phần đầu:

```bash
head -n 40 feature-login.mbox
```

Trên PowerShell, có thể dùng `Get-Content -TotalCount 40 feature-login.mbox`. File mbox có thể chứa nhiều header email và phần diff, nên không nên sửa thủ công các trường metadata nếu chưa hiểu định dạng.

## 6. Tạo cover letter cho patch series

Khi gửi nhiều commit, người review thường cần một lời giới thiệu giải thích mục tiêu chung, phạm vi và thứ tự các patch. Dùng `--cover-letter`:

```bash
git format-patch --cover-letter origin/main..HEAD
```

Git tạo thêm một file cover letter, thường có số thứ tự `0000`, bên cạnh các patch được đánh số từ `0001`.

Cover letter là nơi trình bày:

- Vấn đề hoặc mục tiêu của toàn bộ patch series.
- Cách các patch phụ thuộc hoặc nối tiếp nhau.
- Những điểm cần người review chú ý.
- Kết quả kiểm thử liên quan.
- Các thay đổi so với phiên bản gửi trước nếu đây là bản cập nhật.

Git tạo phần khung cover letter; bạn cần mở file và điền nội dung trước khi gửi. Không để nguyên các placeholder hoặc phần mô tả mẫu nếu người nhận cần một lời giải thích thực tế.

Ví dụ tạo cả cover letter và lưu vào thư mục:

```bash
git format-patch --cover-letter -o patches origin/main..HEAD
```

Sau đó mở file `0000` được tạo trong thư mục `patches` và hoàn thiện nội dung. Tên file cụ thể phụ thuộc subject. Giữ cover letter cùng các patch thuộc cùng series.

## 7. Đặt subject prefix và đánh số phiên bản gửi

Mặc định, subject patch thường bắt đầu bằng `[PATCH]` hoặc `[PATCH n/m]`. Có thể thay prefix:

```bash
git format-patch --subject-prefix="RFC PATCH" origin/main..HEAD
```

Điều này giúp người nhận nhận biết loại đề xuất hoặc quy ước của dự án. Hãy thống nhất prefix với maintainer hoặc quy trình review.

Nếu gửi lại một patch series đã được review, dùng reroll count:

```bash
git format-patch -v2 --cover-letter -o patches-v2 origin/main..HEAD
```

`-v2` tạo subject có phiên bản `v2`, giúp phân biệt với series trước. Lần tiếp theo có thể dùng `-v3`. Nên dùng thư mục riêng cho từng lần gửi để không trộn patch cũ và mới.

Có thể điều chỉnh số bắt đầu bằng `--start-number`:

```bash
git format-patch --start-number=5 -4 HEAD
```

Tùy chọn này thay đổi số thứ tự trong tên/subject patch, không thay đổi commit hoặc thứ tự lịch sử. Trong đa số patch series thông thường, nên để Git đánh số từ 1.

## 8. Giữ quan hệ thread và thông tin người nhận

Nếu patch series được gửi qua email, Git có thể tạo header để các thư trong series nằm trong cùng một thread:

```bash
git format-patch --thread --cover-letter origin/main..HEAD
```

`--thread` thêm thông tin tham chiếu giữa các message. `--no-thread` tắt cơ chế này. Có thể chỉ định địa chỉ người nhận trong header bằng `--to` hoặc `--cc`:

```bash
git format-patch --to=maintainer@example.com --cc=reviewer@example.com origin/main..HEAD
```

Các tùy chọn này chỉ tạo header trong file patch; chúng không tự gửi email. Bạn vẫn cần dùng công cụ gửi thư hoặc nền tảng review được nhóm chấp thuận. Không đưa địa chỉ người nhận không cần thiết vào patch metadata.

Nếu gửi qua một hệ thống review khác, các header email có thể không cần thiết. Khi đó có thể tạo patch bình thường rồi đính kèm artifact theo quy trình của hệ thống đó.

## 9. Bao gồm file nhị phân và diff đầy đủ

Patch văn bản thông thường thể hiện thay đổi dòng. Với file nhị phân, diff mặc định có thể chỉ báo rằng file đã thay đổi mà không chứa đủ dữ liệu để tái tạo nội dung mới.

Nếu patch series cần chuyển cả thay đổi file nhị phân, dùng `--binary`:

```bash
git format-patch --binary -1 HEAD
```

Tùy chọn này tạo binary diff có thể áp dụng bởi các công cụ Git tương ứng. Với các công cụ cần OID đầy đủ trong diff, có thể thêm `--full-index`:

```bash
git format-patch --binary --full-index origin/main..HEAD
```

Không phải mọi hệ thống review hoặc công cụ xử lý patch bên ngoài đều hiển thị binary diff thân thiện. Nếu series có file lớn hoặc artifact sinh tự động, hãy cân nhắc chuyển chúng qua kho artifact hoặc cơ chế phân phối phù hợp thay vì đưa tất cả vào patch email.

## 10. Xác minh patch trước khi chia sẻ

Trước khi gửi, xác nhận patch được tạo từ đúng commit và không chứa thay đổi ngoài ý muốn.

Xem danh sách commit:

```bash
git log --oneline --decorate --reverse origin/main..HEAD
```

Kiểm tra trạng thái working tree:

```bash
git status --short
git diff
git diff --cached
```

Hai lệnh diff cuối cho biết thay đổi chưa stage và đã stage. Chúng không được đóng gói bởi `git format-patch` nếu chưa được commit.

Tạo patch vào thư mục riêng:

```bash
git format-patch -o patches origin/main..HEAD
```

Xem thống kê từng patch hoặc nội dung commit:

```bash
git show --stat --oneline <commit>
git show <commit>
```

Có thể kiểm tra file patch bằng `git apply --stat` để xem thống kê thay đổi, nhưng lệnh này chỉ kiểm tra dạng diff và không xác minh đầy đủ metadata email/commit như `git am`.

Nếu muốn thử khả năng áp dụng trên một worktree hoặc clone tạm, hãy dùng một bản làm việc sạch ở đúng base và chạy `git am` theo chính sách dự án. Không thử áp dụng patch lên working tree đang có công việc chưa commit.

## 11. Áp dụng patch series bằng git am

Người nhận thường bắt đầu từ branch có base phù hợp với patch series. Sau đó áp dụng các file patch theo thứ tự. Ví dụ, nếu series có ba patch:

```bash
git am patches/0001-Add-input-validation.patch
git am patches/0002-Fix-parser-boundary.patch
git am patches/0003-Document-new-option.patch
```

Tên file ở ví dụ chỉ minh họa; dùng tên thật do `git format-patch` tạo ra. Nếu có cover letter, không đưa file `0000` vào lệnh `git am`; cover letter không phải commit patch thông thường.

Nếu dùng một file mbox được tạo bằng `--stdout`:

```bash
git am feature-login.mbox
```

`git am` đọc metadata email/patch và tạo commit tương ứng. Thông tin author và author date từ patch được giữ lại; committer là người áp dụng patch theo cấu hình Git của môi trường nhận.

Sau khi áp dụng, kiểm tra:

```bash
git log --oneline --decorate -5
git status
```

Nếu patch được tạo từ một base khác hoặc nội dung trên branch nhận đã thay đổi, việc áp dụng có thể conflict hoặc thất bại.

## 12. Xử lý conflict khi git am

Nếu patch không áp dụng sạch, Git dừng chuỗi và để lại trạng thái am đang diễn ra. Xem trạng thái:

```bash
git status
```

Giải quyết các file conflict như khi xử lý merge:

1. Mở file bị conflict và kết hợp nội dung phù hợp.
2. Stage file đã giải quyết.
3. Tiếp tục chuỗi bằng `git am --continue`.

Ví dụ:

```bash
git add src/parser.java
git am --continue
```

Nếu muốn bỏ qua patch hiện tại và tiếp tục patch tiếp theo:

```bash
git am --skip
```

Chỉ skip khi đã xác nhận thay đổi trong patch không cần thiết hoặc đã được tích hợp bằng cách khác. Nếu muốn hủy toàn bộ lần áp dụng đang dở:

```bash
git am --abort
```

`--abort` đưa repository trở lại trạng thái trước khi bắt đầu chuỗi am. Nếu cần thử lại với một base khác, hãy kiểm tra trạng thái sau khi abort rồi mới bắt đầu lại.

Khi patch có đủ thông tin blob trong diff, có thể yêu cầu Git thử 3-way merge:

```bash
git am --3way patches/0001-Add-input-validation.patch
```

`--3way` giúp Git tìm cách hợp nhất dựa trên blob base khi áp dụng trực tiếp không thành công và các object cần thiết có sẵn. Nó không đảm bảo mọi conflict sẽ tự giải quyết; nếu vẫn có conflict, xử lý rồi dùng `--continue`, `--skip` hoặc `--abort`.

## 13. Phân biệt git format-patch, git diff và git bundle

Ba công cụ có mục đích khác nhau:

| Công cụ | Đóng gói gì? | Giữ metadata commit? | Cách sử dụng chính |
|---|---|---|---|
| `git format-patch` | Một chuỗi commit thành email patch | Có: author, ngày, message và diff | Review/chuyển commit bằng `git am` |
| `git diff` | Khác biệt giữa hai trạng thái/path | Không đóng gói commit metadata | Xem hoặc áp dụng thay đổi bằng `git apply` |
| `git bundle` | Object và ref/lịch sử cần thiết theo phạm vi | Có, vì mang commit object thật | Chuyển lịch sử Git khi không dùng remote trực tiếp |

Nếu cần chuyển các commit riêng lẻ và muốn người nhận tạo commit tương ứng, dùng `format-patch`/`git am`. Nếu chỉ cần một diff không kèm metadata commit, dùng `git diff`/`git apply`. Nếu cần giữ cả graph, branch và object history (bao gồm cấu trúc merge), cân nhắc `git bundle` hoặc trao đổi qua remote.

`format-patch` không phải bản sao đầy đủ của repository. Mặc định, merge commit không được xuất thành patch commit thông thường; patch series cũng không giữ nguyên topology branch/merge. Nếu lịch sử merge là một phần quan trọng của yêu cầu, hãy dùng phương thức chuyển object/ref phù hợp thay vì kỳ vọng patch series tái tạo nguyên đồ thị.

## 14. Các lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không có file patch được tạo | Range rỗng hoặc không có commit phù hợp | Kiểm tra `git log base..tip` |
| Patch chứa commit không mong muốn | Chọn sai base hoặc range | Xem graph và kiểm tra ancestor trước khi tạo |
| Patch không chứa thay đổi đang sửa | `format-patch` chỉ đóng gói commit | Commit thay đổi cần gửi hoặc dùng diff cho thay đổi chưa commit |
| Patch áp dụng sai thứ tự | File bị đổi tên/sắp xếp hoặc trộn nhiều series | Giữ số thứ tự và dùng thư mục riêng |
| `git am` báo patch không áp dụng được | Base khác, nội dung đã thay đổi hoặc conflict | Thử `--3way`, giải quyết conflict rồi continue |
| File nhị phân không được tái tạo | Patch không chứa binary data | Tạo lại với `--binary` |
| Người nhận không biết mục tiêu series | Thiếu mô tả chung | Tạo `--cover-letter` và điền nội dung |
| Lịch sử merge không được tái tạo | Format-patch không giữ topology merge | Dùng bundle hoặc remote để chuyển lịch sử |

## 15. Quy trình thực tế: gửi ba commit cho maintainer

Giả sử bạn đang phát triển trên branch `feature/login`, base là `origin/main` và đã có ba commit hoàn chỉnh. Bạn muốn gửi một series có cover letter.

**Bước 1: Cập nhật base và kiểm tra danh sách commit.**

```bash
git fetch origin
git log --oneline --reverse origin/main..feature/login
git status
```

Đảm bảo working tree/index không có thay đổi cần đưa vào series nhưng chưa commit.

**Bước 2: Tạo patch series trong thư mục riêng.**

```bash
git format-patch --cover-letter -o patches origin/main..feature/login
```

**Bước 3: Hoàn thiện cover letter.**

Mở file `0000` được tạo trong thư mục `patches`, ghi mục tiêu, thứ tự patch, cách kiểm thử và các lưu ý cho người review.

**Bước 4: Kiểm tra các patch.**

```bash
git log --oneline --reverse origin/main..feature/login
git status --short
```

Đối chiếu số lượng và thứ tự patch với danh sách commit. Đọc nội dung từng patch để chắc chắn không có thay đổi ngoài phạm vi.

**Bước 5: Chia sẻ toàn bộ series.**

Gửi cover letter cùng tất cả file patch theo kênh nhóm sử dụng. Giữ nguyên tên và số thứ tự; không gửi riêng một patch phụ thuộc vào patch trước mà không giải thích base và thứ tự.

**Bước 6: Người nhận áp dụng và kiểm tra.**

Trên branch nhận dựa trên base tương thích, áp dụng từng patch theo thứ tự và bỏ qua cover letter:

```bash
git am patches/0001-Add-input-validation.patch
git am patches/0002-Fix-parser-boundary.patch
git am patches/0003-Document-new-option.patch
git log --oneline --decorate -5
git status
```

Tên file ở đây là ví dụ. Có thể áp dụng nhiều patch trong một lần gọi khi đã chọn đúng danh sách file và loại trừ cover letter. Sau khi hoàn tất, chạy test của dự án trước khi merge hoặc phát hành.

## 16. Checklist trước khi tạo và gửi patch

- [ ] Base và tip đã được xác định đúng.
- [ ] Remote-tracking refs đã được fetch nếu dùng base từ remote.
- [ ] Danh sách commit trong range đã được review.
- [ ] Các thay đổi cần gửi đã được commit.
- [ ] Patch được tạo trong thư mục riêng hoặc thành một mbox có kiểm soát.
- [ ] Thứ tự patch được giữ nguyên.
- [ ] Có cover letter nếu series cần giải thích tổng thể.
- [ ] Binary diff được bao gồm nếu có file nhị phân cần chuyển.
- [ ] Patch được kiểm tra trước khi gửi.
- [ ] Người nhận biết base cần có và cách áp dụng bằng `git am`.

## Kết luận

Dùng `git format-patch <base>..<tip>` để tạo một patch cho mỗi commit trong phạm vi cần chia sẻ; dùng `-1`, `-n`, `-o` hoặc `--stdout` để điều chỉnh số lượng và cách xuất. Thêm `--cover-letter` khi cần mô tả toàn bộ series, `-v2` khi gửi lại phiên bản đã cập nhật và `--binary` nếu cần chuyển thay đổi file nhị phân. Người nhận áp dụng bằng `git am`, giữ metadata tác giả và tạo commit mới trong repository của họ. Hãy nhớ format-patch chuyển nội dung commit theo dạng patch, không mang toàn bộ object graph hay topology merge như `git bundle`.
