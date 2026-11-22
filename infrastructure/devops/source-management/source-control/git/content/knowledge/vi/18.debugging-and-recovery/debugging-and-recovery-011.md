# Giới hạn phục hồi đối với dữ liệu chưa từng được add hoặc commit

Git có thể giúp bạn khôi phục nhiều thay đổi đã mất, nhưng Git không phải công cụ sao lưu mọi file trên máy. Git chỉ quản lý những nội dung đã được đưa vào repository thông qua commit, staging hoặc các thao tác lưu như stash. Một file mới chưa từng được `git add`, chưa được stash và chưa xuất hiện trong bất kỳ commit nào thường không có bản sao trong dữ liệu Git.

Đây là giới hạn quan trọng khi xử lý sự cố. Nếu một file untracked bị xóa, `git restore`, `git reset`, `git checkout`, `git reflog` hay `git fsck` không thể tự tạo lại nội dung mà Git chưa từng lưu. Bạn cần tìm bản sao ở IDE, hệ điều hành, dịch vụ đồng bộ hoặc bản sao lưu khác.

## 1. Git lưu những gì và không lưu những gì?

Git theo dõi nội dung thông qua các đối tượng trong object database và các tham chiếu trong repository. `git add` đưa nội dung file tracked hoặc file mới vào index; khi tạo commit, Git lưu snapshot của index thành một commit. Các thao tác stash cũng lưu thay đổi thành các đối tượng Git để có thể áp dụng lại sau.

| Trạng thái của file | Git có nội dung để phục hồi không? | Nguồn phục hồi có thể dùng |
|---|---|---|
| Đã có trong commit | Có | Commit, branch, tag hoặc reflog còn giữ commit |
| Đã `git add` và đang nằm trong index | Có | Index; có thể khôi phục từ index |
| Đã từng `git add`, sau đó bị bỏ khỏi index nhưng blob chưa bị dọn | Có thể | Dangling blob trong object database, nếu còn tồn tại |
| Đang sửa file tracked nhưng chưa stage | Có bản gốc trong commit/index; phần sửa mới có thể chưa được Git lưu | Có thể lấy lại bản gốc; phần sửa chưa stage cần nguồn khác nếu đã mất |
| File untracked chưa từng được add hoặc stash | Không | IDE, hệ điều hành, dịch vụ đồng bộ hoặc backup |
| File ignored chưa từng được add hoặc stash | Không | IDE, hệ điều hành, dịch vụ đồng bộ hoặc backup |

Git lưu snapshot, không tự ghi lại từng thao tác gõ phím. Vì vậy, với file tracked, Git có thể khôi phục phiên bản commit hoặc index nhưng không nhất thiết khôi phục được những ký tự mới nhất chưa từng được stage. Với file untracked chưa từng được lưu vào Git, repository không có dữ liệu để dựng lại.

## 2. Phân biệt tracked, untracked và ignored

Trước khi phục hồi, hãy xác định Git biết file đó hay chưa:

```bash
git status --short --untracked-files=all
git ls-files -- src/config.yml
git check-ignore -v local.env
```

- **Tracked**: file đã được đưa vào index hoặc đã xuất hiện trong lịch sử Git. Git biết đường dẫn và có thể có snapshot để khôi phục.
- **Untracked**: file tồn tại trong working tree nhưng chưa được index theo dõi. Git có thể liệt kê file, nhưng không lưu nội dung của file.
- **Ignored**: file bị quy tắc ignore loại khỏi trạng thái thông thường. Git không đưa file đó vào commit hoặc stash mặc định.

`git status --short --untracked-files=all` giúp nhìn thấy cả các file untracked bên trong thư mục. `git check-ignore -v` cho biết quy tắc nào đang ignore một đường dẫn. File ignored vẫn có thể được add bằng cách chỉ rõ đường dẫn, nhưng nếu chưa từng add thì Git không có snapshot của nó.

Đừng nhầm việc Git hiển thị tên một file untracked với việc Git đã lưu nội dung file. Trạng thái untracked chỉ có nghĩa là file đang tồn tại trong working tree và chưa được quản lý bởi index.

## 3. Khôi phục file đã từng được Git theo dõi

Nếu file đã có trong commit, bạn có thể lấy lại phiên bản từ commit hiện tại. Ví dụ file `src/config.yml` bị xóa khỏi working tree nhưng vẫn tồn tại trong `HEAD`:

```bash
git status
git restore --source=HEAD --worktree -- src/config.yml
```

Lệnh này khôi phục nội dung từ `HEAD` vào working tree. Nếu file đã được stage với nội dung khác, hãy kiểm tra index trước khi chọn nguồn khôi phục. Để lấy phiên bản đã stage hiện tại, có thể dùng:

```bash
git restore --worktree -- src/config.yml
```

Không dùng các lệnh này để khôi phục file untracked chưa từng được add: không có phiên bản trong `HEAD` hoặc index để Git lấy.

Nếu cần lấy file từ một commit cũ:

```bash
git log --all --oneline -- src/config.yml
git restore --source=<COMMIT_ID> --worktree -- src/config.yml
```

Lệnh đầu tìm commit có thay đổi liên quan đến đường dẫn. Lệnh sau khôi phục file theo snapshot của commit được chọn. Hãy xác nhận đúng commit và đường dẫn trước khi ghi đè nội dung hiện tại.

## 4. Trường hợp file đã `git add` nhưng chưa commit

`git add` không chỉ đánh dấu file trong staging area; Git còn ghi nội dung file thành blob object trong object database và lưu mã blob trong index. Nếu file đã stage rồi bị xóa khỏi working tree, bạn có thể khôi phục từ index:

```bash
git status
git restore --worktree -- src/new-report.md
```

Lệnh này lấy nội dung đang có trong index và ghi lại file vào working tree. Nếu index còn chứa phiên bản bạn muốn giữ, đây là cách khôi phục trực tiếp.

Nếu bạn đã bỏ staging bằng `git reset` hoặc thay mục index bằng một phiên bản khác, blob cũ có thể không còn được tham chiếu bởi index hay commit. Tuy nhiên, dữ liệu blob có thể vẫn tồn tại trong object database một thời gian trước khi Git dọn rác.

Trong trường hợp đó, có thể thử tìm các object không còn được tham chiếu:

```bash
git fsck --full --no-reflogs --unreachable
```

Nếu kết quả có `unreachable blob <OBJECT_ID>` hoặc `dangling blob <OBJECT_ID>`, kiểm tra nội dung bằng:

```bash
git cat-file -p <OBJECT_ID>
```

Hoặc yêu cầu Git ghi các object dangling vào thư mục `lost-found` trong metadata của repository:

```bash
git fsck --full --lost-found
```

Các blob được tìm thấy thường không còn tên file gốc hoặc đường dẫn ban đầu. Bạn phải đọc nội dung để xác định blob nào là file cần phục hồi. Kết quả cũng không được đảm bảo: object có thể đã bị garbage collection xóa, hoặc blob chưa từng được tạo ra.

Một lưu ý: `git add -N <file>` (intent-to-add) chủ yếu ghi nhận ý định thêm đường dẫn để diff có thể hiển thị nội dung. Không nên xem thao tác này là bằng chứng rằng toàn bộ nội dung file đã được lưu thành blob có thể phục hồi.

## 5. File untracked chưa từng được add hoặc stash

Đây là trường hợp Git không thể phục hồi nội dung. Ví dụ:

```bash
git status --short
# ?? notes/draft.md
```

File `notes/draft.md` đang tồn tại nhưng chưa được add. Nếu bạn xóa file bằng trình quản lý tệp, lệnh shell hoặc một công cụ dọn dẹp, Git không có blob hay commit chứa nội dung để khôi phục.

Các lệnh sau không thể tái tạo nội dung của file chưa từng được lưu trong Git:

- `git restore` lấy nội dung từ index hoặc commit.
- `git reset` cập nhật index và/hoặc di chuyển tham chiếu commit.
- `git checkout` lấy phiên bản từ commit hoặc chuyển nhánh.
- `git reflog` ghi lại việc di chuyển các tham chiếu như `HEAD` và branch, không ghi lịch sử sửa file untracked.
- `git fsck` kiểm tra object database, không quét ổ đĩa để tìm nội dung chưa từng được ghi vào Git.

Nếu file đã bị xóa, hãy tìm bản sao ngoài Git. Tùy cách làm việc, các nguồn có thể gồm:

- **IDE/editor**: Local History, Timeline, Local History của JetBrains, lịch sử file hoặc bản nháp tự lưu.
- **Hệ điều hành**: Recycle Bin/Thùng rác, File History, Previous Versions hoặc snapshot của ổ đĩa.
- **Dịch vụ đồng bộ**: lịch sử phiên bản của OneDrive, Dropbox, Google Drive hoặc hệ thống lưu trữ doanh nghiệp.
- **Backup**: bản sao lưu định kỳ, snapshot máy ảo, bản sao thư mục dự án hoặc backup của thiết bị.
- **Khôi phục dữ liệu**: công cụ phục hồi file đã xóa của hệ thống tệp, nếu dữ liệu chưa bị ghi đè; với SSD, TRIM có thể làm giảm đáng kể khả năng phục hồi.

Nếu file vừa bị xóa khỏi ổ đĩa và có giá trị quan trọng, hạn chế ghi thêm dữ liệu lên cùng ổ đĩa trước khi thử phục hồi. Mọi thao tác mới có thể ghi đè vùng lưu trữ cũ. Khả năng phục hồi phụ thuộc hệ thống tệp, thiết bị và cơ chế đồng bộ; không có bảo đảm thành công.

## 6. File ignored và giới hạn của stash

File ignored cũng không được Git lưu mặc định. Ví dụ `.env.local`, file build hoặc cấu hình riêng của máy thường nằm trong `.gitignore` để tránh commit nhầm. Nếu file đó chưa từng được add hoặc stash, Git không thể phục hồi nội dung khi nó bị xóa.

Trước khi có sự cố, nếu muốn cất tạm file untracked, dùng:

```bash
git stash push -u -m "WIP: include new test"
```

Nếu cần cất cả file ignored:

```bash
git stash push -a -m "WIP: include local config"
```

`-u` bao gồm file untracked; `-a` bao gồm cả untracked và ignored. Stash phải được tạo trước khi file bị mất. Nếu file đã bị xóa trước đó, lệnh stash không thể tái tạo nội dung.

Với file chứa secret như token, mật khẩu hoặc khóa riêng, không nên dùng stash hoặc commit như một kho lưu trữ thông thường. Hãy dùng secret manager hoặc cơ chế backup an toàn được tổ chức phê duyệt.

## 7. Cẩn trọng với reset và clean

`git reset --hard` đưa index và working tree của các file tracked về commit đích. Nó không phải lệnh dọn toàn bộ file untracked, nhưng file untracked nằm chắn đường ghi một file tracked có thể bị xóa trong quá trình cập nhật.

`git clean` mới là lệnh chuyên dọn file untracked. Luôn xem trước danh sách trước khi xóa:

```bash
git clean -nd
```

`-n` là dry-run, `-d` cho phép hiển thị thư mục untracked. Để xem cả file ignored:

```bash
git clean -ndx
```

`-x` bao gồm cả file ignored. `-X` chỉ nhắm đến file ignored:

```bash
git clean -ndX
```

Chỉ sau khi kiểm tra kỹ kết quả dry-run mới cân nhắc lệnh xóa thực tế như `git clean -fd`. Lệnh xóa không đưa file vào Recycle Bin theo cách thông thường và có thể làm mất nội dung không có trong Git. Không dùng `git clean -fdx` trong repository đang chứa dữ liệu local cần giữ.

## 8. Quy trình xử lý khi phát hiện mất file

Khi một file biến mất, hãy kiểm tra theo thứ tự để tránh làm tình trạng khó phục hồi hơn:

1. **Dừng thao tác ghi đè hoặc dọn dẹp.** Không chạy thêm `git clean`, reset hoặc script xóa file khi chưa hiểu nguyên nhân.
2. **Xác định trạng thái trước khi mất.** Dùng `git status --short --untracked-files=all`, `git ls-files -- <path>` và `git check-ignore -v <path>` nếu file còn tồn tại hoặc cần xác định cách Git quản lý đường dẫn.
3. **Kiểm tra lịch sử Git.** Tìm file trong `git log --all -- <path>` và kiểm tra index nếu file đã từng được stage.
4. **Tìm stash hoặc commit liên quan.** Xem `git stash list`, branch, tag và reflog nếu nghi ngờ nội dung từng được lưu qua các thao tác đó.
5. **Thử tìm object dangling nếu file đã từng được add.** Dùng `git fsck` và kiểm tra blob còn tồn tại.
6. **Nếu file chưa từng được Git lưu, kiểm tra nguồn ngoài Git.** Xem IDE Local History, thùng rác, version history của dịch vụ đồng bộ và backup.
7. **Sau khi phục hồi, lưu lại một bản an toàn.** Kiểm tra nội dung, rồi add/commit hoặc đưa vào backup phù hợp với loại dữ liệu.

Ví dụ kiểm tra một đường dẫn:

```bash
git status --short --untracked-files=all
git ls-files -- notes/draft.md
git log --all --oneline -- notes/draft.md
git stash list
```

Nếu `git ls-files` và `git log` đều không cho thấy đường dẫn, điều đó không chứng minh tuyệt đối file chưa từng tồn tại trong Git ở một thời điểm khác, nhưng là dấu hiệu cho thấy không có phiên bản dễ truy cập trong index hoặc lịch sử hiện tại. Nếu file chưa từng được add/stash ở bất kỳ trạng thái nào, hãy chuyển sang các nguồn phục hồi ngoài Git.

## 9. Phòng tránh mất dữ liệu chưa được Git quản lý

- **Commit theo từng mốc nhỏ.** Khi một phần công việc đã ổn định, tạo commit để có snapshot có thể truy cập lại.
- **Stage sớm khi phù hợp.** `git add` lưu blob vào object database và tạo mục trong index. Việc này giúp Git có thể giữ nội dung staged, dù vẫn không thay thế backup.
- **Cất untracked trước khi chuyển việc.** Dùng `git stash push -u` nếu cần giữ file mới chưa được theo dõi.
- **Kiểm tra trước khi dọn.** Dùng `git clean -n` hoặc `git clean -ndx` để xem trước; đọc kỹ đường dẫn sẽ bị ảnh hưởng.
- **Dùng backup cho file ignored.** File local, file cấu hình và dữ liệu sinh ra có thể cần backup riêng theo chính sách dự án.
- **Bật lịch sử file trong IDE hoặc hệ điều hành.** Tính năng local history và version history giúp phục hồi những thay đổi Git chưa từng nhìn thấy.
- **Không xem Git là bản sao lưu duy nhất.** Git lưu lịch sử source code đã được đưa vào repository, không tự bảo vệ mọi dữ liệu trên ổ đĩa.

## 10. Bài tập thực hành

Trong một repository thử nghiệm, tạo một file tracked, một file untracked và một file ignored. Dùng nội dung giả lập, không dùng dữ liệu nhạy cảm.

1. Commit file tracked, chỉnh sửa nó nhưng chưa stage, rồi xóa file khỏi working tree. Khôi phục bản đã commit bằng `git restore --source=HEAD --worktree -- <file>` và ghi nhận phần chỉnh sửa chưa stage không còn trong bản phục hồi.
2. Tạo file mới, `git add` file đó rồi xóa file khỏi working tree. Khôi phục nội dung đã stage bằng `git restore --worktree -- <file>`.
3. Tạo một file untracked khác nhưng không add. Xóa file bằng trình quản lý tệp trong môi trường thử nghiệm và thử xác định xem Git có thể khôi phục nội dung hay không.
4. Dùng `git stash push -u` trên một file untracked khác và quan sát rằng file được cất vì đã có thao tác lưu vào stash.
5. Chạy `git clean -nd` và `git clean -ndx` để so sánh danh sách file untracked và ignored có thể bị xóa.
6. Giải thích vì sao `git reflog` không thể phục hồi file chưa từng được add, stash hoặc commit.

Bạn hoàn thành bài tập khi phân biệt được dữ liệu Git đã lưu với dữ liệu chỉ tồn tại trong working tree, biết lúc nào `git fsck` có thể hữu ích và xác định được nguồn phục hồi ngoài Git khi file chưa từng được lưu vào repository.
