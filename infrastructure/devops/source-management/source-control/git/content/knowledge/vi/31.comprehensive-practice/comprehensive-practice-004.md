# Tạo xung đột có chủ đích và kiểm chứng kết quả giải quyết

Merge conflict (xung đột hợp nhất) xảy ra khi Git không thể tự kết hợp các thay đổi từ những nhánh khác nhau. Để hiểu rõ cách xử lý, hãy tạo một tình huống có kiểm soát: hai nhánh cùng sửa một dòng trong cùng một tệp, mỗi nhánh đưa ra một nội dung khác nhau, rồi merge để Git báo xung đột.

Bài thực hành này đi qua toàn bộ quy trình: chuẩn bị repository sạch, tạo hai nhánh thay đổi độc lập, kích hoạt conflict, đọc trạng thái và các phiên bản trong index, chỉnh nội dung cuối cùng, stage kết quả, hoàn tất merge và kiểm chứng commit. Thực hiện trong thư mục lab riêng để các thao tác thử nghiệm không ảnh hưởng dự án đang làm.

## 1. Mục tiêu và điều kiện thực hành

Sau bài thực hành, bạn có thể:

- Tạo một conflict văn bản có thể tái hiện bằng hai nhánh cùng sửa một dòng.
- Xác định nhánh hiện tại và nhánh được merge vào.
- Đọc thông báo conflict, trạng thái unmerged và nội dung các stage trong index.
- Chọn hoặc kết hợp nội dung từ hai phía để tạo kết quả đúng yêu cầu.
- Đánh dấu từng tệp đã giải quyết bằng cách stage kết quả.
- Hoàn tất merge và xác minh nội dung, lịch sử hai parent cùng trạng thái working tree.

Các lệnh trong bài dùng Bash, Git Bash hoặc WSL. Nếu dùng PowerShell, bạn có thể tạo hoặc sửa tệp bằng editor, giữ nguyên nội dung minh họa rồi chạy các lệnh Git tương ứng. Trước khi bắt đầu, Git cần được cài đặt và identity commit phải được cấu hình.

## 2. Tạo repository lab và commit nền

Tạo một thư mục riêng và khởi tạo repository với nhánh chính là main:

```bash
mkdir git-conflict-lab
cd git-conflict-lab
git init --initial-branch=main

# Cấu hình identity riêng cho repository thực hành
git config user.name "Git Learner"
git config user.email "learner@example.test"
```

Tạo tệp settings.txt với hai dòng:

```bash
printf 'message=Hello\nformat=plain\n' > settings.txt
git add settings.txt
git commit -m "Add initial settings"
```

Kiểm tra trạng thái và commit nền:

```bash
git status --short
git log --oneline --decorate -1
cat settings.txt
```

Kết quả cần có:

```text
message=Hello
format=plain
```

Repository phải sạch trước khi tạo merge conflict. Kiểm tra bằng git status; nếu còn thay đổi chưa commit, hãy xử lý chúng trước. Working tree sạch giúp việc abort merge hoặc phân tích conflict dễ dự đoán hơn.

## 3. Tạo nhánh tính năng và sửa dòng thứ nhất

Tạo nhánh feature/greeting từ commit nền:

```bash
git switch -c feature/greeting
```

Trên nhánh này, đổi dòng message thành nội dung riêng:

```bash
printf 'message=Hello from feature\nformat=plain\n' > settings.txt
git add settings.txt
git commit -m "Customize greeting in feature branch"
```

Kiểm tra commit và nội dung:

```bash
git log --oneline --decorate -2
cat settings.txt
```

Nhánh feature/greeting hiện có một commit mới so với main. Commit nền vẫn là tổ tiên chung của hai nhánh.

## 4. Quay lại main và sửa cùng dòng theo cách khác

Chuyển về main:

```bash
git switch main
```

Trên main, thay chính dòng message bằng nội dung khác với nhánh feature:

```bash
printf 'message=Hello from main\nformat=plain\n' > settings.txt
git add settings.txt
git commit -m "Customize greeting in main branch"
```

Lúc này, hai nhánh đều bắt đầu từ cùng một commit nhưng đã sửa cùng một dòng theo hai hướng khác nhau. Xác nhận lịch sử:

```bash
git log --oneline --graph --decorate --all
git status --short
```

Đồ thị trước merge có dạng khái niệm:

```text
          feature commit
         /
base ----
         \
          main commit
```

Hai commit mới là hai đầu nhánh độc lập. Vì cả hai cùng sửa dòng đầu tiên trong settings.txt, Git không thể tự quyết định nội dung nào nên được giữ.

## 5. Kích hoạt conflict bằng merge

Đang ở nhánh main, merge nhánh feature/greeting:

```bash
git merge feature/greeting
```

Git sẽ báo conflict và dừng trước khi tạo merge commit. Lệnh có thể trả mã thoát khác 0; trong bài lab, đây là kết quả mong đợi. Kiểm tra trạng thái:

```bash
git status
git diff --name-only --diff-filter=U
git diff --cc -- settings.txt
```

Bạn thường thấy settings.txt được liệt kê trong phần unmerged paths với trạng thái both modified. Git đã nhận diện được tệp xung đột nhưng chưa có kết quả cuối cùng để ghi vào index.

Nội dung working tree có thể chứa conflict markers:

```text
<<<<<<< HEAD
message=Hello from main
=======
message=Hello from feature
>>>>>>> feature/greeting
format=plain
```

Ý nghĩa các dấu phân cách trong merge conflict:

- Dòng bắt đầu bằng <<<<<<< HEAD mở phần nội dung từ nhánh hiện tại, tức main trong ví dụ này.
- Dòng ======= ngăn cách hai phía.
- Dòng bắt đầu bằng >>>>>>> feature/greeting đóng phần nội dung từ nhánh đang được merge vào.
- Nội dung nằm ngoài vùng marker, như format=plain, không xung đột và được giữ lại.

Tên hiển thị ở marker phụ thuộc thao tác và cấu hình. Khi merge, HEAD thường đại diện cho nhánh hiện tại; phía còn lại là nhánh được merge vào.

## 6. Đọc ba phiên bản của tệp trong index

Trong lúc conflict chưa được giải quyết, index có thể giữ ba phiên bản cho cùng một đường dẫn:

| Stage | Tên thường gọi | Nội dung |
|---|---|---|
| 1 | Base | Phiên bản ở tổ tiên chung, trước khi hai nhánh tách ra |
| 2 | Ours | Phiên bản từ nhánh hiện tại, ở đây là main |
| 3 | Theirs | Phiên bản từ nhánh được merge vào, ở đây là feature/greeting |

Xem các mục chưa hợp nhất:

```bash
git ls-files -u -- settings.txt
```

Kết quả minh họa:

```text
100644 <base-blob-oid>   1 settings.txt
100644 <ours-blob-oid>   2 settings.txt
100644 <theirs-blob-oid> 3 settings.txt
```

Các OID trong ví dụ là giá trị thực tế do repository tạo ra. Đọc riêng từng phiên bản:

```bash
# Phiên bản ở tổ tiên chung
git show :1:settings.txt

# Phiên bản từ nhánh hiện tại (main)
git show :2:settings.txt

# Phiên bản từ nhánh được merge vào (feature/greeting)
git show :3:settings.txt
```

Các lệnh trên giúp xem nội dung từng phía ngay cả khi working tree đang chứa conflict markers. Không phải mọi loại conflict đều có đủ ba stage. Ví dụ, add/add hoặc modify/delete có cấu trúc stage khác; hãy dùng git ls-files -u để xem chính xác index của từng đường dẫn.

## 7. Chọn cách giải quyết conflict

Không có quy tắc rằng luôn phải chọn ours hoặc theirs. Hãy dựa vào yêu cầu chức năng và hiểu nội dung của cả hai phía.

Với bài lab này, giả sử yêu cầu cuối cùng là thông điệp thể hiện cả hai nhánh đã đóng góp. Mở settings.txt, xóa toàn bộ marker và thay dòng message bằng nội dung kết hợp:

```text
message=Hello from main and feature
format=plain
```

Kiểm tra lại tệp bằng editor hoặc:

```bash
cat settings.txt
```

Nếu quyết định giữ nguyên một phía, bạn cũng có thể lấy phiên bản tương ứng:

```bash
# Lấy nội dung từ nhánh hiện tại trong một merge
git restore --ours -- settings.txt

# Hoặc lấy nội dung từ nhánh được merge vào
git restore --theirs -- settings.txt
```

Sau lệnh restore, vẫn phải kiểm tra nội dung và stage tệp. Ours/theirs chỉ chọn một phiên bản cho đường dẫn đó; nó không tự giải quyết các conflict khác hoặc xác nhận kết quả đáp ứng yêu cầu nghiệp vụ.

Khi giải quyết nhiều tệp, hãy xử lý từng tệp theo ngữ cảnh. Conflict có thể là:

- **Content conflict:** hai phía sửa cùng vùng văn bản; thường có conflict markers.
- **Add/add:** hai nhánh cùng thêm một đường dẫn mới với nội dung khác nhau.
- **Modify/delete:** một phía sửa tệp, phía kia xóa tệp.
- **Rename-related:** hai phía đổi tên hoặc sửa tệp theo cách Git không thể ghép tự động.
- **Binary conflict:** tệp nhị phân không thể được kết hợp bằng cách chèn marker văn bản.

Các loại conflict không phải lúc nào cũng hiển thị marker. Hãy dùng git status và git ls-files -u để phân loại thay vì chỉ tìm các dòng <<<<<<< trong tệp.

## 8. Stage kết quả để đánh dấu đã giải quyết

Sau khi nội dung cuối cùng đã đúng, đưa tệp vào index:

```bash
git add settings.txt
```

Stage kết quả có ý nghĩa rằng bạn đã chọn nội dung cuối cùng cho đường dẫn. Kiểm tra trạng thái unmerged:

```bash
git ls-files -u
git status
```

Nếu settings.txt đã được giải quyết và không còn đường dẫn conflict khác, git ls-files -u sẽ không in ra mục nào. Trong index, đường dẫn đã stage trở thành stage 0 thay cho các stage 1, 2, 3.

Kiểm tra nội dung được stage:

```bash
git ls-files --stage -- settings.txt
git diff --cached -- settings.txt
git diff --cached --check
```

Kết quả mong đợi của git ls-files --stage là một mục stage 0 cho settings.txt. git diff --cached cho biết nội dung đã stage; git diff --cached --check kiểm tra lỗi whitespace trong thay đổi đã stage.

Trước khi hoàn tất merge, xem toàn bộ trạng thái và bảo đảm không còn đường dẫn unmerged:

```bash
git status
git diff --name-only --diff-filter=U
git diff --cached --stat
```

Nếu còn tệp unmerged, tiếp tục giải quyết và stage từng tệp. Không dùng git add . một cách máy móc khi chưa xem danh sách; lệnh đó có thể stage cả thay đổi khác không thuộc merge.

## 9. Hoàn tất merge commit

Khi tất cả conflict đã được giải quyết và stage, hoàn tất merge:

```bash
git merge --continue
```

Git có thể mở editor để xác nhận merge commit message. Giữ hoặc chỉnh thông điệp phù hợp, lưu và đóng editor. Bạn cũng có thể dùng git commit để hoàn tất merge sau khi đã stage đầy đủ; trong quy trình đang có merge state, git commit tạo merge commit.

Sau khi hoàn tất, kiểm tra:

```bash
git status
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw HEAD
```

Merge commit thường có hai dòng parent: parent thứ nhất là tip của nhánh hiện tại trước merge (main), parent thứ hai là tip của nhánh được merge vào (feature/greeting). Đây là bằng chứng lịch sử đã ghi nhận cả hai phía.

## 10. Kiểm chứng kết quả sau merge

Không dừng ở việc Git báo merge thành công. Cần xác minh nội dung, trạng thái và cấu trúc lịch sử.

### Kiểm tra nội dung cuối cùng

```bash
cat settings.txt
git show HEAD:settings.txt
```

Hai kết quả phải phản ánh nội dung đã chọn:

```text
message=Hello from main and feature
format=plain
```

### Kiểm tra không còn conflict

```bash
git status --short
git ls-files -u
git diff --check
git diff --cached --check
```

Sau merge commit, working tree và index nên sạch. git ls-files -u không nên còn mục nào. Hai lệnh diff --check không nên báo lỗi whitespace trong các thay đổi được kiểm tra.

### Kiểm tra hai parent của merge commit

```bash
git rev-list --parents -n 1 HEAD
git show --no-patch --format=fuller HEAD
git log --graph --oneline --decorate --all
```

git rev-list --parents in ra OID của merge commit, theo sau là các parent OID. Với merge hai nhánh thông thường, dòng đó có ba OID: commit merge và hai parent. git log --graph giúp nhìn thấy hai nhánh hội tụ ở merge commit.

### So sánh nội dung merge với từng parent

```bash
# Thay đổi mà merge commit đưa vào so với parent thứ nhất
git diff HEAD^1 HEAD -- settings.txt

# Thay đổi mà merge commit đưa vào so với parent thứ hai
git diff HEAD^2 HEAD -- settings.txt
```

Hai phép so sánh này giúp kiểm tra kết quả cuối cùng so với từng phía. Nếu dự án có test hoặc kiểm tra build liên quan, hãy chạy chúng sau khi merge để xác nhận kết quả giải quyết vẫn đúng chức năng.

## 11. Nếu muốn hủy merge khi chưa hoàn tất

Nếu nhận ra đã bắt đầu merge nhầm hoặc không muốn tiếp tục, có thể hủy merge đang diễn ra:

```bash
git merge --abort
```

Lệnh này yêu cầu Git quay lại trạng thái trước khi bắt đầu merge trong phạm vi Git có thể khôi phục. Kết quả dễ dự đoán nhất khi working tree sạch trước merge. Nếu có thay đổi chưa commit trước khi merge, Git có thể không khôi phục hoàn toàn như mong muốn; vì vậy hãy commit hoặc stash công việc trước khi bắt đầu merge.

Sau khi abort, kiểm tra:

```bash
git status
git log --oneline --decorate -3
cat settings.txt
```

Không dùng git reset --hard chỉ để thoát conflict nếu chưa xác định rõ những thay đổi cần giữ. Trong bài lab, bạn có thể thử abort trước khi giải quyết, rồi thực hiện lại merge để luyện toàn bộ quy trình.

## 12. Phân biệt conflict với lỗi khác trong merge

Không phải mọi lần merge dừng lại đều là content conflict:

| Tình huống | Dấu hiệu | Hướng xử lý |
|---|---|---|
| Content conflict | Git báo CONFLICT và có đường dẫn unmerged | Giải quyết nội dung, stage và tiếp tục merge |
| Local changes would be overwritten | Working tree có thay đổi chưa commit sẽ bị ghi đè | Commit hoặc stash thay đổi trước khi merge |
| Already up to date | Nhánh hiện tại đã chứa commit của nhánh kia | Không có merge cần thực hiện |
| Fast-forward | Nhánh hiện tại có thể tiến thẳng đến tip nhánh kia | Git cập nhật ref mà không cần merge commit |
| Refusing to merge unrelated histories | Hai lịch sử không có tổ tiên chung | Xác minh đúng repository và ý định trước khi cân nhắc tùy chọn cho phép |

Khi Git báo conflict, đọc thông báo và trạng thái trước khi chạy lệnh tiếp theo. Không nên mặc định rằng mọi lỗi merge đều được giải quyết bằng cách sửa conflict markers.

## 13. Những lỗi thường gặp khi giải quyết conflict

| Lỗi | Hậu quả | Cách tránh |
|---|---|---|
| Xóa marker nhưng quên giữ nội dung cần thiết | Tệp có thể mất logic từ một hoặc cả hai phía | Đọc cả base, ours và theirs trước khi chỉnh |
| Chọn ours/theirs cho mọi tệp mà không review | Có thể làm mất thay đổi hợp lệ của phía còn lại | Quyết định theo từng tệp và yêu cầu chức năng |
| Quên stage tệp đã giải quyết | Git vẫn xem đường dẫn là unmerged và không cho hoàn tất merge | Dùng git add cho từng kết quả đã kiểm tra |
| Chỉ kiểm tra working tree | Nội dung index có thể khác nội dung trên đĩa | Kiểm tra cả git diff và git diff --cached |
| Còn đường dẫn unmerged nhưng vẫn cố commit | Git từ chối tạo merge commit | Kiểm tra git ls-files -u trước khi tiếp tục |
| Dùng git add . khi có thay đổi không liên quan | Có thể stage cả tệp ngoài phạm vi merge | Stage chính xác đường dẫn đã giải quyết |
| Không chạy test sau khi merge | Conflict có thể hết về mặt văn bản nhưng sai logic | Chạy test và kiểm tra hành vi sau merge |
| Dùng reset --hard để thoát conflict | Có thể mất thay đổi local | Dùng git merge --abort khi muốn hủy merge và hiểu trạng thái trước merge |

## 14. Checklist kiểm chứng trước khi kết thúc

Trước khi coi một conflict đã được giải quyết, hãy tự kiểm tra:

- [ ] Đã xác định đúng nhánh hiện tại và nhánh được merge vào.
- [ ] Đã đọc nội dung từ cả hai phía và base khi cần.
- [ ] Đã xóa toàn bộ conflict marker còn sót trong tệp văn bản.
- [ ] Đã xử lý mọi đường dẫn unmerged, kể cả add/add, modify/delete hoặc binary.
- [ ] Đã stage kết quả cuối cùng cho từng đường dẫn.
- [ ] git ls-files -u không còn mục nào.
- [ ] git diff --cached thể hiện đúng nội dung chuẩn bị commit.
- [ ] Merge commit có đủ parent như mong đợi.
- [ ] Working tree sạch và test liên quan đã đạt.

## 15. Tự kiểm tra

1. **Vì sao hai nhánh cùng sửa một dòng theo hai nội dung khác nhau có thể tạo conflict?**
   - Vì Git không thể tự xác định nội dung nào là lựa chọn đúng khi ghép hai thay đổi trên cùng vùng.
2. **Trong một merge từ feature vào main, stage 2 thường đại diện cho phía nào?**
   - Ours, tức nhánh hiện tại main.
3. **Stage 1 trong index chứa gì?**
   - Phiên bản base tại tổ tiên chung của hai nhánh.
4. **Lệnh nào liệt kê các đường dẫn đang unmerged?**
   - git ls-files -u hoặc git diff --name-only --diff-filter=U.
5. **Vì sao phải chạy git add sau khi sửa conflict?**
   - Để thay các stage conflict bằng kết quả đã giải quyết ở stage 0 và đánh dấu đường dẫn hoàn tất.
6. **Làm sao xác nhận merge commit có hai parent?**
   - Dùng git rev-list --parents -n 1 HEAD hoặc git show --no-patch --pretty=raw HEAD.
7. **Lệnh nào hủy một merge đang diễn ra trước khi commit?**
   - git merge --abort.

## Kết luận

Tạo conflict có chủ đích bằng cách cho hai nhánh sửa cùng một dòng giúp bạn quan sát rõ cách Git lưu base, ours và theirs trong index. Để giải quyết, hãy đọc trạng thái, hiểu nội dung của cả hai phía, chỉnh thành kết quả đúng yêu cầu, stage từng tệp và xác nhận không còn đường dẫn unmerged. Sau đó hoàn tất merge và kiểm chứng nội dung, hai parent của merge commit, working tree sạch cùng test liên quan. Quy trình này biến việc xử lý conflict thành các bước có thể kiểm tra thay vì chọn một phía theo cảm tính.
