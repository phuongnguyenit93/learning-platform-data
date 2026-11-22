# Giới hạn của git commit -a đối với tệp chưa được theo dõi

Lệnh `git commit -a` thường được hiểu nhầm là “commit tất cả thay đổi”. Thực tế, tùy chọn `-a` tự động stage những thay đổi và việc xóa trên các tệp đã được Git theo dõi. Nó không tự thêm các tệp mới chưa được theo dõi (untracked files) vào index.

Điểm quan trọng là sau bước tự động stage, Git vẫn tạo commit từ toàn bộ nội dung đang có trong index. Vì vậy, một tệp mới đã được stage từ trước vẫn có thể xuất hiện trong commit `-a`; tệp mới chỉ nằm trong working tree thì không.

Bài học thuộc chương **Tạo commit** của module `SOURCE_CONTROL_GIT`. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; hiểu đúng `git commit -a` giúp bạn kiểm soát phạm vi commit và tránh bỏ sót tệp mới hoặc đưa nhầm thay đổi vào lịch sử.

## 1. Trước hết: tracked, untracked và index

Git phân biệt tệp dựa trên việc tệp đã được đưa vào index/lịch sử hay chưa.

- **Tracked file:** đường dẫn đã được Git quản lý, thường đã có trong commit hoặc đã được thêm vào index.
- **Untracked file:** tệp đang có trong working tree nhưng chưa được đưa vào index.
- **Staged change:** nội dung hoặc thao tác thêm/sửa/xóa đã được ghi vào index để chuẩn bị commit.
- **Unstaged change:** thay đổi trong working tree chưa được cập nhật vào index.

Ví dụ repository có trạng thái:

~~~text
project/
  README.md
  src/
    app.js
    config.js
  docs/
    setup.md
~~~

Giả sử `README.md`, `src/app.js` và `src/config.js` đã được commit. Bạn sửa `src/app.js`, xóa `src/config.js` và tạo mới `docs/setup.md`.

| Đường dẫn | Trạng thái | Git đã biết đường dẫn? |
| --- | --- | --- |
| `src/app.js` | Modified | Có, tracked |
| `src/config.js` | Deleted | Có, tracked |
| `docs/setup.md` | Untracked | Chưa, nếu chưa stage |

Đây là khác biệt quyết định hành vi của `git commit -a`.

## 2. git commit -a thực hiện điều gì?

Lệnh:

~~~bash
git commit -a -m "Update application"
~~~

hoặc dạng viết gọn:

~~~bash
git commit -am "Update application"
~~~

sẽ tự động đưa các thay đổi và việc xóa của những tệp đã được theo dõi vào index, sau đó tạo commit từ index.

Có thể hiểu ngắn gọn:

1. Git tìm các tracked files có thay đổi trong working tree.
2. Git stage nội dung mới của tracked files đã sửa và stage việc xóa tracked files đã bị xóa.
3. Git tạo commit từ toàn bộ nội dung đang có trong index.

Bước thứ ba rất quan trọng: commit không chỉ chứa những thay đổi vừa được `-a` stage. Mọi nội dung đã có sẵn trong index cũng được đưa vào commit, bao gồm tệp mới mà bạn đã stage bằng `git add` trước đó.

### Ví dụ: sửa và xóa tệp tracked

Giả sử:

- `src/app.js` đã được commit và đang sửa.
- `src/config.js` đã được commit và đã bị xóa.
- Chưa có thay đổi nào được stage trước đó.

Chạy:

~~~bash
git commit -am "Update app and remove old config"
~~~

Git tự stage phần sửa của `src/app.js`, stage việc xóa `src/config.js` và tạo commit. Hai thay đổi này được ghi vào lịch sử.

### Ví dụ: tệp mới chưa được theo dõi

Giả sử bạn tạo `docs/setup.md` nhưng chưa chạy `git add`:

~~~bash
git status --short
~~~

Kết quả có thể tương tự:

~~~text
 M src/app.js
 D src/config.js
?? docs/setup.md
~~~

Chạy:

~~~bash
git commit -am "Update application"
~~~

Commit sẽ chứa thay đổi của `src/app.js` và việc xóa `src/config.js`. `docs/setup.md` vẫn là untracked và không xuất hiện trong commit.

Sau commit, kiểm tra:

~~~bash
git status --short
~~~

Bạn sẽ vẫn thấy:

~~~text
?? docs/setup.md
~~~

Đây là giới hạn cốt lõi của `-a`: Git không tự quyết định thêm tệp mới vì chưa có chỉ dẫn rõ ràng rằng bạn muốn quản lý chúng.

## 3. Tệp mới đã stage vẫn được commit

Cần phân biệt hai trường hợp:

- Tệp mới chỉ tồn tại trong working tree: chưa có trong index, `git commit -a` bỏ qua.
- Tệp mới đã được `git add`: đã nằm trong index, `git commit -a` sẽ commit nó cùng các thay đổi khác đang có trong index.

Ví dụ:

~~~bash
git add docs/setup.md
git commit -am "Add setup guide and update app"
~~~

Ở đây `docs/setup.md` được commit vì bạn đã stage nó trước đó. Tùy chọn `-a` không tự thêm tệp này; nó chỉ thực hiện bước stage bổ sung cho các tracked files.

Nếu bạn đã stage một số thay đổi từ trước, hãy xem `git diff --cached` trước khi chạy commit. Những thay đổi staged đó có thể được đưa vào cùng commit, dù chúng không liên quan trực tiếp đến nội dung bạn nghĩ `-a` sẽ xử lý.

## 4. So sánh git commit -a, git add -u và git add -A

Các lệnh có vẻ gần nhau nhưng khác mục đích:

| Lệnh | Tệp tracked sửa/xóa | Tệp mới untracked | Tạo commit? |
| --- | --- | --- | --- |
| `git commit -a -m "..."` | Tự stage | Không tự stage | Có |
| `git add -u` | Stage | Không stage | Không |
| `git add -A` | Stage | Stage nếu không bị ignore | Không |
| `git add .` | Stage trong phạm vi pathspec hiện tại | Stage trong phạm vi pathspec hiện tại nếu không bị ignore | Không |
| `git commit -m "..."` | Không tự stage thay đổi chưa stage | Không tự stage | Có, từ index hiện tại |

### git add -u: chỉ cập nhật các đường dẫn đã được theo dõi

~~~bash
git add -u
~~~

Lệnh này stage thay đổi và việc xóa trên các đường dẫn tracked trong phạm vi áp dụng. Nó không thêm tệp untracked.

Sau đó bạn có thể kiểm tra nội dung index:

~~~bash
git diff --cached
git status --short
~~~

Khi đã hài lòng, tạo commit:

~~~bash
git commit -m "Update tracked files"
~~~

Cách này hữu ích khi bạn muốn tách rõ bước stage khỏi bước commit để review nội dung sẽ được ghi vào lịch sử.

### git add -A: thêm, sửa và xóa

~~~bash
git add -A
~~~

Lệnh này cập nhật index với mọi thay đổi được Git nhìn thấy trong phạm vi áp dụng: tệp mới, tệp đã sửa và tệp đã xóa. Tệp bị ignore vẫn không được thêm theo cách thông thường.

Khi chạy từ repository root, lệnh thường được dùng để stage tất cả thay đổi hợp lệ của repository. Sau đó review và commit:

~~~bash
git diff --cached --stat
git diff --cached
git commit -m "Update project"
~~~

### git add .: phụ thuộc thư mục hiện tại

~~~bash
git add .
~~~

Dấu `.` là pathspec cho thư mục hiện tại. Vì vậy, nếu chạy từ thư mục con, phạm vi stage có thể chỉ gồm thư mục đó và các đường dẫn bên dưới, không nhất thiết là toàn bộ repository.

Hãy chú ý thư mục hiện tại khi dùng lệnh này. Nếu muốn stage toàn bộ repository, chuyển về root rồi dùng `git add -A`.

## 5. Tình huống xóa và đổi tên tệp

`git commit -a` tự stage việc xóa một tracked file. Nhưng nếu bạn tự đổi tên tệp bằng trình quản lý tệp hoặc lệnh hệ điều hành, Git có thể nhìn thấy hai sự kiện:

- Đường dẫn cũ là tracked và đã bị xóa.
- Đường dẫn mới là untracked.

Ví dụ đổi tên thủ công:

~~~text
src/old-name.js  ->  src/new-name.js
~~~

Nếu chưa stage đường dẫn mới, chạy:

~~~bash
git commit -am "Rename module"
~~~

có thể chỉ commit việc xóa `src/old-name.js`. Tệp `src/new-name.js` vẫn untracked. Git thường nhận diện rename bằng cách so sánh nội dung sau khi các đường dẫn được stage/commit; rename không phải một loại object riêng trong commit.

Cách rõ ràng là dùng `git mv`:

~~~bash
git mv src/old-name.js src/new-name.js
git status --short
git commit -m "Rename module"
~~~

`git mv` cập nhật index cho thao tác đổi tên. Nếu dùng thao tác đổi tên thủ công, hãy stage cả đường dẫn mới và việc xóa đường dẫn cũ:

~~~bash
git add -A -- src/old-name.js src/new-name.js
git diff --cached --summary
git commit -m "Rename module"
~~~

## 6. -a có thể làm mất ý định partial staging

Đây là một giới hạn quan trọng khi bạn dùng `git add -p` để chia một tệp thành nhiều phần commit.

Giả sử `src/app.js` có hai thay đổi độc lập:

- Hunk A: sửa lỗi tính tiền.
- Hunk B: thêm log debug.

Bạn chỉ muốn stage hunk A:

~~~bash
git add -p src/app.js
~~~

Sau đó kiểm tra:

~~~bash
git diff --cached -- src/app.js
git diff -- src/app.js
~~~

`git diff --cached` hiển thị hunk A đã stage; `git diff` hiển thị hunk B còn ở working tree.

Nếu tiếp theo bạn chạy:

~~~bash
git commit -am "Fix invoice calculation"
~~~

`-a` sẽ tự stage các thay đổi hiện có của tracked file `src/app.js`. Điều này có thể đưa cả hunk B vào index, khiến commit chứa cả hai thay đổi. Vì vậy, `git commit -a` không phù hợp khi bạn muốn giữ ranh giới partial staging trên các tracked files đang thay đổi.

Để giữ đúng phần đã chọn, hãy dùng:

~~~bash
git commit -m "Fix invoice calculation"
~~~

Lệnh `git commit` thông thường chỉ commit nội dung đã có trong index. Hunk B tiếp tục nằm trong working tree để bạn xử lý ở commit sau.

Nếu muốn kiểm soát chặt từng phần, quy trình nên là:

~~~bash
git add -p src/app.js
git diff --cached
git diff
git commit -m "Fix invoice calculation"
~~~

Trước khi commit, hãy kiểm tra các tệp staged khác nữa vì commit luôn lấy toàn bộ index, không chỉ một hunk bạn vừa chọn.

## 7. git commit -a vẫn commit mọi nội dung đã staged

Tên tùy chọn `-a` có thể khiến bạn nghĩ commit chỉ bao gồm các thay đổi tracked mà nó tự stage. Thực tế, lệnh commit vẫn lấy toàn bộ index.

Ví dụ:

~~~bash
git add docs/new-guide.md
git add src/feature.js
git commit -am "Update feature"
~~~

Commit sẽ chứa cả `docs/new-guide.md` và `src/feature.js`, nếu cả hai đang staged. Nếu bạn không muốn đưa `docs/new-guide.md` vào commit này, hãy xem index trước và bỏ stage đúng đường dẫn:

~~~bash
git restore --staged -- docs/new-guide.md
git diff --cached --name-status
git commit -am "Update feature"
~~~

Lệnh `git restore --staged` bỏ thay đổi khỏi index nhưng giữ nội dung trong working tree. Với repository chưa có commit đầu tiên, cần lưu ý `HEAD` chưa tồn tại; có thể dùng `git rm --cached` cho một tệp mới đã stage và cần giữ trên đĩa.

Không nên chạy `git commit -a` khi chưa biết index đang chứa những gì.

## 8. Tệp bị ignore và tệp đã tracked

`.gitignore` chủ yếu ngăn các tệp chưa tracked được thêm vào index một cách thông thường. Nó không tự ngừng theo dõi các tệp đã được commit.

Ví dụ `config/local.yml` đã tracked, sau đó bạn thêm pattern vào `.gitignore`:

~~~gitignore
config/local.yml
~~~

Tệp vẫn là tracked. Nếu bạn sửa nó, `git commit -a` vẫn có thể stage thay đổi và commit nội dung mới.

Để kiểm tra một tệp có tracked hay không:

~~~bash
git ls-files -- config/local.yml
~~~

Để kiểm tra quy tắc ignore:

~~~bash
git check-ignore -v -- config/local.yml
~~~

Nếu tệp đã tracked và nhóm quyết định ngừng quản lý nó, cần thay đổi index một cách có chủ đích, ví dụ:

~~~bash
git rm --cached -- config/local.yml
~~~

Lệnh này giữ file local trên đĩa nhưng xóa nó khỏi index trong commit kế tiếp. Hãy phối hợp với nhóm trước khi thay đổi một file cấu hình được nhiều thành viên dùng chung.

## 9. Cách kiểm tra trước khi dùng git commit -a

Trước khi chạy commit, kiểm tra trạng thái tổng thể:

~~~bash
git status --short
~~~

Xem thay đổi chưa stage:

~~~bash
git diff
~~~

Xem nội dung đã stage:

~~~bash
git diff --cached
~~~

Liệt kê tệp untracked chưa bị ignore:

~~~bash
git ls-files --others --exclude-standard
~~~

Liệt kê tệp ignored nếu cần rà soát:

~~~bash
git ls-files --others --ignored --exclude-standard
~~~

Bạn cũng có thể yêu cầu Git chạy thử chế độ dry-run:

~~~bash
git commit --dry-run -a
~~~

Dry-run giúp xem tóm tắt những gì lệnh commit dự kiến xử lý mà không tạo commit. Để review chính xác nội dung sẽ được commit, hãy xem diff của index và working tree; nếu cần kiểm tra bước tự stage riêng, có thể dùng `git add -u` rồi xem `git diff --cached`, sau đó commit bằng `git commit` thông thường.

Lưu ý rằng `git add -u` sẽ cập nhật index cho các tracked files. Nếu bạn đang dựa vào partial staging, thao tác này cũng có thể thay thế phần stage riêng của các tệp đó. Hãy chọn quy trình phù hợp với ý định commit.

## 10. Ví dụ thực tế: commit cả sửa đổi tracked và tệp mới

Giả sử bạn đang làm một tính năng và có các thay đổi:

~~~text
 M src/payment.js
 M README.md
?? tests/payment-new.test.js
?? docs/payment-flow.md
~~~

Bạn muốn commit cả bốn đường dẫn.

Cách dùng `git commit -a` một mình sẽ bỏ qua hai tệp mới. Có hai cách phù hợp.

**Cách 1: Stage tệp mới trước, rồi dùng -a cho phần tracked**

~~~bash
git add tests/payment-new.test.js docs/payment-flow.md
git commit -am "Add payment flow and tests"
~~~

Commit chứa các tệp mới đã stage và các thay đổi tracked mà `-a` tự stage.

**Cách 2: Stage toàn bộ rồi commit bình thường**

~~~bash
git add -A
git diff --cached --stat
git diff --cached
git commit -m "Add payment flow and tests"
~~~

Cách thứ hai giúp review index trước khi commit. Đây thường là lựa chọn dễ kiểm soát hơn khi thay đổi gồm nhiều loại tệp hoặc cần kiểm tra nội dung kỹ.

## 11. Khi nào nên và không nên dùng git commit -a?

| Tình huống | Có nên dùng -a? | Lý do |
| --- | --- | --- |
| Sửa một vài tracked files và muốn commit nhanh | Có thể | -a tự stage phần sửa |
| Xóa tracked files và muốn commit việc xóa | Có thể | -a tự stage deletion |
| Có tệp mới chưa stage | Không đủ | Tệp mới sẽ bị bỏ qua |
| Tệp mới đã được stage từ trước | Có thể, sau khi review index | Commit sẽ lấy cả staged additions |
| Đang dùng git add -p để tạo commit từng phần | Không nên | -a có thể stage thêm các hunk chưa chọn |
| Index đang có thay đổi từ công việc khác | Cần kiểm tra kỹ | Commit sẽ chứa toàn bộ index |
| Muốn review đầy đủ trước commit | Nên stage tường minh | git add riêng rồi xem git diff --cached |

`git commit -a` phù hợp với thao tác nhanh trên các tệp tracked khi bạn chủ ý commit toàn bộ thay đổi của chúng. Khi có tệp mới, partial staging hoặc nhiều thay đổi độc lập, stage tường minh thường dễ kiểm soát hơn.

## 12. Sơ đồ quyết định

~~~mermaid
flowchart TD
    A[Cần tạo commit] --> B{Có tệp tracked sửa hoặc xóa?}
    B -- Không --> C{Có nội dung đã staged?}
    B -- Có --> D{Có tệp mới untracked cần commit?}
    D -- Không --> E{Có cần partial staging?}
    E -- Không --> F[git commit -a -m]
    E -- Có --> G[Review index và dùng git commit]
    D -- Có --> H[Stage tệp mới bằng git add]
    H --> I{Có muốn tự stage mọi tracked changes?}
    I -- Có --> J[Review index rồi git commit -a]
    I -- Không --> K[Stage chọn lọc rồi git commit]
    C -- Có --> L[Review git diff --cached rồi git commit]
    C -- Không --> M[Kiểm tra status và xác định nội dung cần stage]
~~~

Trước khi dùng `git commit -a`, hãy tự xác nhận:

1. Các tệp tôi muốn commit đã tracked hoặc đã được stage chưa?
2. Có tệp mới untracked nào cần thêm bằng `git add` không?
3. Có thay đổi staged từ công việc khác đang nằm trong index không?
4. Tôi có đang dùng partial staging và cần giữ các hunk chưa chọn không?
5. Tôi đã kiểm tra `git diff`, `git diff --cached` và `git status` chưa?
6. Commit message có mô tả đúng toàn bộ nội dung sẽ được commit không?

`git commit -a` là tiện ích để tự stage thay đổi và việc xóa của tracked files trước khi commit. Nó không tự thêm tệp mới chưa được theo dõi, nhưng vẫn commit mọi nội dung đã có trong index. Khi nắm rõ ranh giới giữa working tree, index và tracked files, bạn sẽ biết lúc nào có thể dùng `-a` nhanh gọn và lúc nào cần stage tường minh để giữ commit chính xác.

## Tài liệu tham khảo

- [Git documentation: git-commit](https://git-scm.com/docs/git-commit) — hành vi của `-a`, `--all`, `--dry-run` và commit từ index.
- [Git documentation: git-add](https://git-scm.com/docs/git-add) — cập nhật index với tệp mới, sửa đổi và xóa.
- [Git documentation: git-status](https://git-scm.com/docs/git-status) — phân biệt staged, unstaged và untracked.
- [Git documentation: git-diff](https://git-scm.com/docs/git-diff) — xem khác biệt giữa working tree, index và commit.
- [Pro Git: Recording Changes to the Repository](https://git-scm.com/book/en/v2/Git-Basics-Recording-Changes-to-the-Repository) — staging area và quy trình commit.
