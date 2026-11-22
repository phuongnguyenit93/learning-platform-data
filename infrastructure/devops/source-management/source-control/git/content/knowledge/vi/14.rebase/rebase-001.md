# Rebase sao chép commit lên nền mới và thay đổi mã định danh

Rebase giúp đưa các commit riêng của một nhánh lên trên một nền lịch sử mới. Git lấy những thay đổi của từng commit, lần lượt áp dụng chúng lên commit nền mới rồi tạo các commit thay thế. Vì commit mới có quan hệ cha khác với commit cũ, mã định danh của chúng cũng thay đổi, dù nội dung thay đổi có thể gần như giống hệt. Hiểu cơ chế này giúp bạn đọc lịch sử sau rebase, so sánh commit trước và sau, đồng thời tránh viết lại lịch sử mà đồng đội đang sử dụng.

## 1. Rebase giải quyết tình huống nào?

Giả sử bạn tạo nhánh `feature/report` từ `main`. Sau đó, trong khi bạn phát triển tính năng, `main` tiếp tục nhận commit mới. Nhánh tính năng vẫn dựa trên nền cũ và có một số commit riêng.

Trước khi rebase, lịch sử có thể như sau:

```text
      D---E  feature/report
     /
A---B---C    main
```

- `B` là commit chung nơi nhánh tính năng tách ra.
- `C` là commit mới được thêm vào `main` sau khi nhánh tính năng tách ra.
- `D` và `E` là các commit riêng của nhánh tính năng.

Nếu muốn nhánh tính năng tiếp tục dựa trên `C`, bạn có thể rebase `feature/report` lên `main`. Sau khi rebase thành công, lịch sử nhìn theo nhánh mới sẽ là:

```text
A---B---C---D'---E'  feature/report
        ^
        main
```

Các thay đổi từ `D` và `E` được phát lại trên nền `C`, tạo thành `D'` và `E'`. Dấu nháy (`'`) trong sơ đồ chỉ để phân biệt commit mới với commit cũ; đó không phải ký hiệu Git hiển thị trong mã commit.

Kết quả là lịch sử nhánh tính năng trở thành một đường thẳng từ `main` tới các commit mới. Rebase không tạo merge commit để nối hai nhánh như merge thông thường.

## 2. Rebase thực hiện việc gì bên trong?

Ở mức khái niệm, Git thực hiện các bước sau:

1. Xác định commit nền chung giữa nhánh hiện tại và nhánh đích.
2. Xác định các commit có trên nhánh hiện tại nhưng chưa có trong lịch sử nhánh đích.
3. Tạm thời đưa nhánh đang rebase về commit nền mới.
4. Lần lượt lấy thay đổi của từng commit riêng và áp dụng lên nền mới.
5. Tạo commit mới cho mỗi thay đổi được áp dụng thành công, rồi cập nhật nhánh hiện tại tới commit cuối cùng.

Có thể hình dung thao tác này giống việc phát lại từng bản vá (*patch*) theo thứ tự. Git không đơn giản di chuyển nguyên commit cũ sang vị trí khác, vì commit là một đối tượng bất biến và có liên kết tới commit cha.

Trong ví dụ trên, quan hệ cha thay đổi như sau:

| Commit | Commit cha trước rebase | Commit cha sau rebase |
|---|---|---|
| `D` và `D'` | `B` | `C` |
| `E` và `E'` | `D` | `D'` |

Commit `D'` được tạo trên `C`, nên commit tiếp theo `E'` phải tham chiếu `D'` làm cha. Vì thế, khi commit đầu tiên được tạo lại với mã mới, các commit sau trong chuỗi cũng thường có mã mới theo.

## 3. Vì sao mã định danh commit thay đổi?

Mã định danh commit (commit ID hoặc hash) được tính từ nội dung đối tượng commit. Đối tượng này chứa nhiều thông tin, trong đó có:

- Tree ID: cây thư mục và nội dung file mà commit ghi nhận.
- Parent ID: commit cha; commit merge có thể có nhiều cha.
- Author: người tạo thay đổi và thời điểm tác giả.
- Committer: người tạo đối tượng commit và thời điểm ghi commit.
- Commit message và các metadata khác; commit đã ký còn có dữ liệu chữ ký.

Chỉ cần một phần của đối tượng commit thay đổi thì mã định danh cũng thay đổi. Trong rebase, parent ID gần như chắc chắn thay đổi khi commit được đặt lên nền mới. Thời điểm committer cũng thường được cập nhật khi commit được tạo lại. Do đó, dù diff của `D` và `D'` trông giống nhau, hai commit vẫn có hash khác nhau.

Ví dụ:

```text
Commit cũ:  7ab31c2  parent = B
Commit mới: d92f840  parent = C
```

Các chuỗi hash trên chỉ là minh họa. Không nên suy luận hai commit giống hay khác nhau chỉ bằng cách nhìn vài ký tự đầu; hãy xem nội dung, parent và metadata của chúng.

### 3.1. Nội dung thay đổi có nhất thiết giống hệt không?

Không. Git cố gắng áp dụng thay đổi của commit cũ lên nền mới. Nếu nền mới có thay đổi liên quan, nội dung sau khi áp dụng có thể khác với file ở commit cũ. Khi có xung đột, bạn phải tự chọn kết quả kết hợp; commit được tạo sau đó sẽ ghi nhận nội dung đã giải quyết.

Nếu không có xung đột và thay đổi được áp dụng nguyên vẹn, tree của commit mới có thể giống với tree của commit cũ. Tuy vậy, parent hoặc metadata thay đổi vẫn đủ làm hash khác.

### 3.2. Author và committer có gì khác?

Author thường vẫn là người đã viết thay đổi ban đầu. Committer là người tạo commit mới trong lần rebase; thông tin committer và thời điểm commit thường phản ánh lần tạo lại. Vì vậy, khi xem chi tiết commit sau rebase, bạn có thể thấy tác giả cũ nhưng committer là người thực hiện rebase.

Có các tùy chọn nâng cao để điều chỉnh metadata ngày giờ, nhưng không cần thay đổi chúng trong quy trình rebase thông thường. Mục tiêu quan trọng là hiểu rằng mã commit đại diện cho toàn bộ đối tượng commit, chứ không chỉ phần diff.

## 4. Thực hiện rebase trên nhánh tính năng

Ví dụ bạn đang làm trên `feature/report`, còn nhánh nền là `main` ở remote `origin`.

Trước khi rebase, kiểm tra nhánh và working tree:

```bash
git status -sb
git branch -vv
```

Nếu có thay đổi chưa commit, hãy commit hoặc lưu chúng theo quy trình của bạn trước. Rebase yêu cầu working tree sạch trong phần lớn tình huống thông thường; không nên bắt đầu khi còn thay đổi chưa được quản lý.

Cập nhật thông tin từ remote và chuyển tới nhánh tính năng:

```bash
git fetch origin
git switch feature/report
```

Xem lịch sử trước khi thay đổi:

```bash
git log --oneline --graph --decorate --all
```

Sau khi xác nhận `origin/main` là nền mong muốn, thực hiện:

```bash
git rebase origin/main
```

Git sẽ phát lại các commit riêng của `feature/report` trên `origin/main`. Nếu thành công, nhánh `feature/report` trỏ tới commit cuối cùng được tạo lại. Nhánh `main` local và `origin/main` không bị di chuyển bởi thao tác rebase trên nhánh tính năng.

Nếu bạn muốn cập nhật nhánh local `main` trước rồi mới rebase, có thể làm theo cách khác:

```bash
git switch main
git pull --ff-only origin main
git switch feature/report
git rebase main
```

`--ff-only` yêu cầu nhánh `main` local chỉ tiến lên theo fast-forward; nếu lịch sử đã phân kỳ, Git dừng thay vì tự tạo một merge commit. Chọn một quy trình nhất quán với cách nhóm quản lý nhánh nền.

## 5. Quan sát commit cũ và commit mới

Để thấy commit nào đã được tạo lại, nên ghi nhận lịch sử trước rebase hoặc xem reflog sau đó.

Trước rebase, lưu lại commit tip cũ của nhánh:

```bash
git rev-parse feature/report
```

Giả sử kết quả là `OLD_TIP`. Sau rebase, xem tip mới:

```bash
git rev-parse feature/report
```

Hai mã có thể khác nhau vì chuỗi commit đã được tạo lại. Để xem lịch sử mới:

```bash
git log --oneline --graph --decorate feature/report
```

Để xem các lần di chuyển HEAD và nhánh gần đây:

```bash
git reflog show feature/report
git reflog
```

Reflog thường giúp tìm lại tip cũ sau rebase, ví dụ mục ghi nhận `rebase (finish)` hoặc trạng thái trước đó của nhánh. Reflog là nhật ký tham chiếu local có thời hạn lưu theo cấu hình; nó không phải bản sao lưu vĩnh viễn và không được chia sẻ lên remote.

Khi đã biết hash cũ và mới, có thể so sánh metadata:

```bash
git show --no-patch --format=fuller <old-commit>
git show --no-patch --format=fuller <new-commit>
```

Lệnh hiển thị Author, AuthorDate, Commit, CommitDate và thông tin commit. Để xem parent ID trực tiếp trong đối tượng commit:

```bash
git cat-file -p <commit-id>
```

Các dòng `parent` cho biết commit cha. Với commit mới sau rebase, parent thường là commit nền mới hoặc commit mới được tạo ngay trước nó.

## 6. Rebase không phải lúc nào cũng tạo lại mọi commit

Rebase chỉ cần phát lại những commit thuộc phạm vi được chọn và chưa có trong lịch sử đích. Một số trường hợp cần lưu ý:

- Nếu nhánh đã dựa trên nền mới và không còn commit cần phát lại, rebase có thể kết thúc mà không thay đổi lịch sử.
- Nếu một thay đổi tương đương đã có trong nhánh đích, Git có thể nhận diện commit đó đã được áp dụng và bỏ qua khi rebase.
- Nếu một commit sau khi áp dụng trở thành rỗng, Git có thể dừng để hỏi, bỏ qua hoặc xử lý theo tùy chọn rebase đang dùng.
- Nếu bạn giải quyết xung đột bằng cách loại bỏ toàn bộ thay đổi của một commit, commit đó có thể trở thành rỗng và không còn được tạo lại theo cách thông thường.

Vì vậy, không nên giả định số lượng commit trước và sau rebase luôn bằng nhau. Hãy xem log và kết quả thực tế.

## 7. Xử lý xung đột trong quá trình phát lại

Rebase áp dụng commit lần lượt. Nếu một commit không thể áp dụng tự động, Git tạm dừng tại commit đó và yêu cầu bạn giải quyết xung đột.

Kiểm tra trạng thái:

```bash
git status
```

Đọc nội dung các file xung đột, xác định thay đổi của commit đang được phát lại và thay đổi trên nền mới. Sau khi tạo kết quả đúng ý nghĩa, stage các file đã giải quyết:

```bash
git add path/to/resolved-file
git rebase --continue
```

Git tiếp tục phát lại commit kế tiếp. Có thể phải giải quyết nhiều lần nếu nhiều commit cùng chạm vào vùng nội dung đã thay đổi trên nền mới.

Các lựa chọn khi rebase đang dừng:

| Lệnh | Tác dụng |
|---|---|
| `git rebase --continue` | Tiếp tục sau khi đã giải quyết và stage xung đột |
| `git rebase --skip` | Bỏ qua commit hiện tại đang được phát lại |
| `git rebase --abort` | Hủy lần rebase và quay lại trạng thái trước khi bắt đầu |

Chỉ dùng `--skip` khi bạn đã xác nhận thay đổi của commit đó không còn cần thiết hoặc đã được tích hợp bằng cách khác. Lệnh này bỏ toàn bộ thay đổi của commit hiện tại trong lần rebase; nó không chỉ bỏ phần đang xung đột.

Nếu kết quả xử lý không rõ ràng hoặc muốn làm lại từ đầu, `git rebase --abort` thường là lựa chọn an toàn để dừng quy trình. Sau đó bạn có thể kiểm tra lại lịch sử, trao đổi với người liên quan và thực hiện lại theo kế hoạch mới.

## 8. So sánh chuỗi commit trước và sau rebase

Khi rebase nhiều commit, so sánh từng hash bằng mắt dễ gây nhầm. Có thể dùng:

```bash
git range-diff <old-base>..<old-tip> <new-base>..feature/report
```

`git range-diff` so sánh hai chuỗi commit để giúp nhận ra commit nào được giữ tương ứng, commit nào thay đổi nội dung, được thêm hoặc bị bỏ. Hãy thay các placeholder bằng hash nền và tip thực tế đã ghi nhận trước rebase cùng nhánh mới sau rebase.

Lệnh này đặc biệt hữu ích khi rebase một chuỗi dài hoặc khi phải giải quyết xung đột. Nó giúp review xem việc phát lại có vô tình làm mất một phần thay đổi hay không. Tuy nhiên, kết quả so sánh vẫn cần được đọc cùng với yêu cầu và test của dự án.

## 9. Ảnh hưởng của rebase tới lịch sử đã chia sẻ

Vì rebase tạo commit mới, nhánh remote có thể vẫn trỏ tới chuỗi commit cũ. Nếu bạn đã push nhánh trước đó rồi rebase local, lần push tiếp theo có thể bị từ chối non-fast-forward.

Trước khi rebase, hãy xác định commit của nhánh đã được người khác lấy về hoặc dùng làm nền cho nhánh khác chưa. Với nhánh cá nhân chưa chia sẻ, việc tạo lại commit thường dễ quản lý hơn. Với nhánh chung, rebase có thể khiến mọi người có lịch sử local dựa trên commit cũ và phải xử lý phân kỳ.

Nếu nhóm đã thống nhất viết lại lịch sử của nhánh remote, hãy fetch và kiểm tra kỹ trước khi cập nhật nhánh đó. `--force-with-lease` có thể giảm nguy cơ ghi đè commit mới mà bạn chưa biết:

```bash
git fetch origin
git log --oneline --graph --decorate HEAD origin/feature/report
git push --force-with-lease origin feature/report
```

Lệnh này vẫn là một thao tác ghi đè lịch sử khi điều kiện lease thỏa mãn. Nó không thay thế việc phối hợp với đồng đội, không vượt qua branch protection và không biến rebase nhánh dùng chung thành việc an toàn mặc định. Không dùng `git push --force` chỉ để vượt qua từ chối non-fast-forward.

## 10. Commit cũ có bị xóa ngay sau rebase không?

Không. Rebase tạo các đối tượng commit mới và cập nhật tham chiếu nhánh tới chuỗi mới. Những commit cũ không còn được nhánh hiện tại tham chiếu có thể vẫn tồn tại trong kho đối tượng Git một thời gian. Chúng có thể còn được tham chiếu bởi nhánh khác, tag, reflog hoặc đối tượng khác.

Nếu không còn tham chiếu nào giữ chúng, Git có thể dọn các đối tượng không còn được sử dụng sau thời gian lưu và quá trình garbage collection. Vì vậy, đừng dựa vào việc commit cũ sẽ tồn tại mãi mãi để làm phương án sao lưu.

Nếu phát hiện rebase làm mất commit cần thiết, kiểm tra reflog để tìm hash cũ. Sau khi xác định đúng commit, có thể tạo nhánh cứu hộ trỏ tới commit đó:

```bash
git branch rescue/report-before-rebase <old-commit>
```

Chỉ dùng hash đã xác minh từ reflog hoặc nguồn đáng tin cậy. Nhánh cứu hộ giữ commit cũ có thể truy cập được để bạn xem xét, cherry-pick hoặc khôi phục theo kế hoạch. Không reset nhánh đang làm việc một cách vội vàng.

## 11. Ghi nhớ

Rebase phát lại các thay đổi của commit riêng lên một nền mới và tạo chuỗi commit thay thế. Commit mới có parent mới nên mã định danh thay đổi, dù patch hoặc nội dung file có thể giống commit cũ. Hãy xem lịch sử trước và sau, dùng reflog hoặc range-diff để kiểm tra khi cần, xử lý xung đột theo từng commit và cân nhắc tác động tới đồng đội trước khi rebase hoặc cập nhật nhánh đã chia sẻ.
