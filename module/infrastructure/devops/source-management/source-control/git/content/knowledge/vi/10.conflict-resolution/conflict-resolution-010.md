# Khôi phục dấu xung đột để xem xét lại quyết định

Khi merge hoặc rebase, Git có thể dừng lại vì hai phía cùng sửa một vùng nội dung. Bạn thường mở file, đọc các dấu `<<<<<<<`, `=======`, `>>>>>>>`, rồi tự kết hợp phần thay đổi. Đôi khi sau khi chỉnh sửa, bạn nhận ra mình đã chọn vội hoặc muốn xem lại nội dung của cả hai phía trước khi xác nhận kết quả.

Nếu file vẫn đang ở trạng thái xung đột trong index, Git có thể tạo lại các dấu xung đột trong working tree. Lệnh chính là `git restore --merge`. Thao tác này giúp bạn quay lại trạng thái có thể xem xét từng phần xung đột, nhưng vẫn giữ dữ liệu các phía mà Git đang lưu trong index.

## 1. Git lưu trạng thái xung đột ở đâu?

Khi một file bị xung đột, Git giữ nhiều phiên bản của file đó trong **index** (staging area). Thay vì một mục đã giải quyết ở stage 0, file xung đột có thể có các mục sau:

| Stage | Nội dung | Ý nghĩa thường gặp |
|---|---|---|
| 1 | Base | Phiên bản tổ tiên chung trước khi hai phía tách ra |
| 2 | Ours | Phiên bản từ phía hiện tại của thao tác tích hợp |
| 3 | Theirs | Phiên bản từ phía còn lại đang được tích hợp |

Không phải mọi loại xung đột đều có đủ cả ba stage. Chẳng hạn, khi hai nhánh cùng tạo một file mới với cùng đường dẫn, có thể không có stage 1 vì file đó chưa tồn tại trong tổ tiên chung.

Kiểm tra trạng thái repository và các mục chưa hợp nhất:

```bash
git status
git ls-files -u -- src/config.yml
```

Kết quả `git ls-files -u` có dạng gồm mode, mã blob, số stage và đường dẫn. Ví dụ minh họa:

```text
100644 <blob-base> 1 src/config.yml
100644 <blob-ours> 2 src/config.yml
100644 <blob-theirs> 3 src/config.yml
```

Bạn có thể đọc từng phiên bản đang được giữ trong index mà không ghi đè file trong working tree:

```bash
git show :1:src/config.yml
git show :2:src/config.yml
git show :3:src/config.yml
```

Lệnh `git show :1:path`, `:2:path` và `:3:path` lần lượt đọc nội dung ở stage 1, 2 và 3. Nếu một stage không tồn tại, Git sẽ báo không tìm thấy đối tượng tương ứng.

## 2. Tạo lại dấu xung đột trong working tree

Giả sử `src/config.yml` từng có dấu xung đột, bạn đã sửa thành một nội dung thống nhất nhưng chưa chạy `git add`. Index vẫn còn các stage chưa hợp nhất. Chạy:

```bash
git restore --merge --worktree -- src/config.yml
```

Git dựng lại nội dung xung đột cho file trong working tree từ các phiên bản đang có trong index. File sẽ xuất hiện lại các dấu xung đột để bạn đọc và quyết định cách kết hợp. Index vẫn giữ trạng thái chưa hợp nhất, vì vậy `git status` tiếp tục báo file đang có conflict.

Lệnh trên thay thế nội dung hiện tại của file trong working tree. Nếu bạn còn phần chỉnh sửa cần giữ, hãy sao lưu file ra một vị trí an toàn trước khi chạy.

### Chọn kiểu hiển thị dấu xung đột

Git hỗ trợ các kiểu hiển thị khác nhau. Bạn có thể yêu cầu kiểu ngay trong lệnh:

```bash
git restore --merge --worktree --conflict=merge -- src/config.yml
git restore --merge --worktree --conflict=diff3 -- src/config.yml
git restore --merge --worktree --conflict=zdiff3 -- src/config.yml
```

- `merge`: hiển thị hai phía đang xung đột; đây là kiểu truyền thống.
- `diff3`: thêm nội dung base để bạn thấy phiên bản ban đầu trước khi hai phía chỉnh sửa.
- `zdiff3`: cũng hiển thị base, đồng thời rút gọn một số dòng chung quanh vùng xung đột để phần khác biệt dễ đọc hơn.

Bạn cũng có thể đặt kiểu mặc định cho repository:

```bash
git config merge.conflictStyle diff3
```

Giá trị cấu hình có thể là `merge`, `diff3` hoặc `zdiff3` tùy phiên bản Git đang dùng. Tùy chọn `--conflict` trong lệnh `restore` cho phép chọn kiểu riêng cho lần khôi phục đó.

Trên phiên bản Git cũ chưa có `git restore`, có thể dùng cú pháp `checkout` tương đương:

```bash
git checkout -m -- src/config.yml
git checkout --conflict=diff3 -- src/config.yml
```

Các lệnh này cũng dựng lại xung đột trong working tree từ những mục chưa hợp nhất của index. Khi có thể, hãy ưu tiên `git restore` vì nó diễn đạt rõ việc khôi phục file.

## 3. Đọc lại nội dung xung đột

Với kiểu `merge`, một vùng xung đột thường có dạng:

```text
<<<<<<< HEAD
timeout: 20
=======
timeout: 45
>>>>>>> feature/longer-timeout
```

- Phần sau `<<<<<<<` là nội dung từ phía ours.
- Phần giữa `=======` và `>>>>>>>` là nội dung từ phía theirs.
- Dòng `=======` phân cách hai lựa chọn.
- Các nhãn sau `<<<<<<<` và `>>>>>>>` giúp nhận biết phía liên quan; chúng có thể là tên nhánh, `HEAD` hoặc mã commit tùy thao tác.

Với kiểu `diff3`, Git thêm vùng base ở giữa ours và theirs:

```text
<<<<<<< HEAD
timeout: 20
||||||| 9ac12ef
timeout: 30
=======
timeout: 45
>>>>>>> feature/longer-timeout
```

Trong ví dụ này, giá trị ban đầu là `30`, nhánh hiện tại đổi thành `20`, còn nhánh đang tích hợp đổi thành `45`. Biết được giá trị base giúp bạn hiểu ý định của từng phía và quyết định giá trị cuối cùng dựa trên yêu cầu thực tế.

Một điểm dễ gây nhầm lẫn là ý nghĩa của ours và theirs khi rebase. Trong merge thông thường, ours là nhánh hiện tại và theirs là nhánh được merge vào. Trong lúc rebase, Git thường coi nhánh đích cùng các commit đã được phát lại là ours, còn commit đang được phát lại là theirs. Vì vậy, hãy đọc nhãn và ngữ cảnh của thao tác thay vì mặc định theirs luôn là nhánh remote.

## 4. Quy trình xem xét và giải quyết lại

Bạn có thể dùng quy trình sau khi nghi ngờ một quyết định giải quyết conflict:

1. **Xác nhận file vẫn chưa hợp nhất.** Chạy `git status` và `git ls-files -u -- <file>` để kiểm tra index còn các stage xung đột.
2. **Giữ lại phần chỉnh sửa cần thiết.** Nếu working tree có nội dung bạn muốn tham khảo, sao lưu file trước khi khôi phục dấu xung đột.
3. **Tạo lại dấu xung đột.** Chạy `git restore --merge --worktree --conflict=diff3 -- <file>` để nhìn thấy cả hai phía và base.
4. **Đánh giá từng vùng.** So sánh ý định của hai phía với base; xem lại yêu cầu nghiệp vụ, cấu hình và các trường hợp sử dụng liên quan.
5. **Tự chỉnh thành một kết quả hoàn chỉnh.** Xóa toàn bộ dấu `<<<<<<<`, `|||||||`, `=======`, `>>>>>>>` và giữ lại nội dung hợp lệ.
6. **Kiểm tra rồi mới đánh dấu đã giải quyết.** Chạy kiểm thử phù hợp, xem lại file và dùng `git add <file>` khi kết quả đã đúng.

Ví dụ với file cấu hình:

```bash
git status
git ls-files -u -- src/config.yml
git restore --merge --worktree --conflict=diff3 -- src/config.yml
```

Sau khi chỉnh sửa xong:

```bash
git diff -- src/config.yml
git diff --check
git add src/config.yml
git status
```

`git diff --check` giúp phát hiện một số lỗi khoảng trắng và dấu conflict còn sót. Hãy kiểm tra nội dung thực tế và chạy test của dự án; lệnh này không thay thế việc xác nhận logic. Sau khi đã giải quyết tất cả file, tiếp tục thao tác đang dở:

```bash
git merge --continue
```

Hoặc nếu đang rebase:

```bash
git rebase --continue
```

Chỉ dùng lệnh tiếp tục tương ứng với thao tác đang diễn ra. Nếu vẫn còn file chưa giải quyết, Git sẽ yêu cầu bạn xử lý trước.

## 5. Nếu file đã được đưa vào staging thì sao?

Đây là giới hạn quan trọng của việc khôi phục dấu xung đột. Khi bạn chạy:

```bash
git add src/config.yml
```

Git ghi kết quả đã giải quyết vào stage 0 và loại bỏ các mục xung đột stage 1, 2, 3 của file đó. Nếu sau đó bạn đổi ý, `git restore --merge` không còn dữ liệu unmerged trong index để dựng lại dấu xung đột ban đầu.

`git restore --staged` cũng không tái tạo các stage xung đột. Lệnh đó chỉ khôi phục nội dung index theo nguồn được chỉ định; nó không khôi phục quyết định merge cũ.

Nếu merge hoặc rebase vẫn đang diễn ra và bạn cần tạo lại toàn bộ xung đột, có thể hủy thao tác rồi thực hiện lại:

```bash
git merge --abort
git merge <ten-nhanh>
```

Hoặc với rebase:

```bash
git rebase --abort
git rebase <nhanh-dich>
```

Các lệnh `--abort` cố gắng đưa repository trở về trạng thái trước thao tác merge hoặc rebase đang dở. Chúng có thể loại bỏ các thay đổi được tạo trong quá trình đó; đặc biệt, nếu bạn bắt đầu merge khi đã có nhiều thay đổi chưa commit, Git có thể không khôi phục đầy đủ trạng thái ban đầu. Hãy lưu riêng mọi công việc cần giữ trước khi hủy. Nếu merge đã được commit, hãy xem xét lịch sử và tạo một commit sửa đổi hoặc dùng quy trình revert phù hợp; `git restore --merge` không thể dựng lại conflict đã kết thúc.

## 6. Những nhầm lẫn thường gặp

| Thao tác | Kết quả | Có tạo lại dấu xung đột không? |
|---|---|---|
| `git restore --merge --worktree -- file` | Dựng lại nội dung conflict từ các stage chưa hợp nhất trong index | Có, nếu index vẫn còn dữ liệu xung đột phù hợp |
| `git restore --ours --worktree -- file` | Lấy nguyên phiên bản ours trong index | Không; chọn một phía |
| `git restore --theirs --worktree -- file` | Lấy nguyên phiên bản theirs trong index | Không; chọn một phía |
| `git show :2:path` hoặc `git show :3:path` | Đọc riêng một phía đang lưu trong index | Không; chỉ hiển thị nội dung |
| `git add file` | Đánh dấu kết quả hiện tại là đã giải quyết | Không; loại bỏ các stage xung đột của file khỏi index |

Một số conflict không thể biểu diễn bằng dấu trong file văn bản, ví dụ xung đột file nhị phân hoặc một số trường hợp đổi tên/xóa file. Khi đó, hãy xem `git status` để biết loại xung đột và xử lý theo trạng thái của từng đường dẫn; không phải lúc nào `git restore --merge` cũng có thể tạo ra một khối marker có ý nghĩa.

Đừng nhầm việc tạo lại dấu xung đột với `git rerere`. `rerere` ghi nhớ và có thể áp dụng lại một cách giải quyết conflict đã gặp trước đó; `git restore --merge` dựng lại nội dung conflict từ các phiên bản còn lưu trong index để bạn xem xét thủ công.

## 7. Bài tập thực hành

Giả sử trong lúc merge nhánh `feature/longer-timeout`, file `src/config.yml` xung đột ở thuộc tính `timeout`. Bạn đã sửa thành `timeout: 40`, nhưng muốn xem lại vì chưa chắc lựa chọn này phù hợp.

1. Chạy `git status` và `git ls-files -u -- src/config.yml`. Xác định file còn các stage 1, 2, 3 hay không.
2. Dùng `git show :1:src/config.yml`, `git show :2:src/config.yml` và `git show :3:src/config.yml` để xem base và hai phía.
3. Chạy `git restore --merge --worktree --conflict=diff3 -- src/config.yml` để tạo lại dấu xung đột có cả base.
4. Giải thích vì sao hai nhánh chọn các giá trị khác nhau, rồi chỉnh file thành một giá trị phù hợp với yêu cầu của ứng dụng.
5. Kiểm tra file, chạy test liên quan, dùng `git add src/config.yml` và xác nhận trạng thái bằng `git status`.

Bạn hoàn thành bài tập khi giải thích được dữ liệu nào trong index cho phép Git dựng lại conflict, sự khác nhau giữa `--merge` và `--ours`/`--theirs`, và vì sao việc staging kết quả làm mất các stage xung đột của file đó.
