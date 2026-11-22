# Giải quyết xung đột và dùng --continue, --skip, --abort

## Vì sao rebase có thể dừng vì xung đột?

Rebase lấy các commit của một nhánh và lần lượt phát lại chúng trên một commit nền mới. Ví dụ, nhánh main đã nhận thêm thay đổi trong khi bạn phát triển trên feature/search. Khi chạy:

~~~bash
git fetch origin
git switch feature/search
git rebase origin/main
~~~

Git xác định các commit riêng của feature/search rồi áp dụng từng commit lên trên origin/main. Nếu một commit đang được phát lại sửa cùng vùng nội dung với thay đổi trên nhánh nền, Git có thể không tự kết hợp được. Rebase sẽ tạm dừng và yêu cầu giải quyết xung đột.

Trong thời gian đó, Git lưu trạng thái của tiến trình rebase và commit đang được xử lý. Bạn cần xác định commit hiện tại, xem các tệp xung đột, kết hợp nội dung đúng, đưa kết quả vào staging area rồi quyết định tiếp tục, bỏ qua commit hiện tại hay hủy toàn bộ rebase.

Ba lệnh điều khiển chính có ý nghĩa khác nhau:

| Lệnh | Tác dụng |
|---|---|
| git rebase --continue | Tiếp tục phát lại commit hiện tại sau khi đã giải quyết và stage xung đột |
| git rebase --skip | Bỏ qua commit đang được phát lại rồi chuyển sang commit tiếp theo |
| git rebase --abort | Hủy tiến trình rebase và đưa nhánh về trạng thái ban đầu trước khi rebase |

Chọn đúng lệnh dựa trên mục tiêu của thay đổi. --skip loại bỏ toàn bộ phần thay đổi của commit hiện tại khỏi kết quả rebase. --abort hủy cả tiến trình rebase đang thực hiện.

## Nhận biết rebase đang tạm dừng

Khi Git báo conflict, bắt đầu bằng:

~~~bash
git status
~~~

Git thường hiển thị thông báo tương tự:

~~~text
interactive rebase in progress; onto 9a8b7c6
Last command done (1 command done):
   pick 1a2b3c4 Add search filter
Next command to do (1 remaining command):
   pick 5d6e7f8 Add search tests
You are currently rebasing branch 'feature/search' on '9a8b7c6'.
  (fix conflicts and then run "git rebase --continue")
  (use "git rebase --skip" to skip this patch)
  (use "git rebase --abort" to check out the original branch)
~~~

Nội dung cụ thể thay đổi theo phiên bản Git và loại rebase. Hãy đọc thông báo để biết:

- Rebase đang diễn ra trên nhánh nào.
- Commit nào vừa được phát lại.
- Còn những commit nào trong hàng đợi.
- Những đường dẫn nào đang ở trạng thái unmerged.
- Git đang gợi ý lệnh tiếp theo nào.

Liệt kê riêng các đường dẫn còn xung đột:

~~~bash
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Nếu không có đường dẫn nào được liệt kê, index hiện không còn entry unmerged. Hãy kiểm tra thông tin trạng thái rebase và các thay đổi staged/unstaged trước khi tiếp tục.

### Xem commit đang được phát lại

Để xem patch của commit hiện tại:

~~~bash
git rebase --show-current-patch
~~~

Có thể xem commit và thông tin tóm tắt bằng:

~~~bash
git show --stat --oneline REBASE_HEAD
git show REBASE_HEAD
~~~

REBASE_HEAD là tham chiếu tới commit đang được Git phát lại. Đọc commit này giúp hiểu tác giả định thay đổi điều gì, vì sao tệp bị xung đột và phần nào cần được bảo toàn.

Xem nội dung của từng phiên bản trong index khi tệp còn unmerged:

~~~bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
~~~

Với xung đột nội dung thông thường, stage 1 là merge base, stage 2 là ours và stage 3 là theirs. Một số kiểu xung đột như add/add, modify/delete hoặc rename có thể không có đủ cả ba stage.

## Hiểu đúng ours và theirs trong rebase

Đây là điểm dễ gây nhầm lẫn khi xử lý conflict trong rebase.

Trong một lần merge thông thường, ours thường là nhánh đang đứng và theirs là nhánh được merge vào. Khi rebase, Git phát lại commit của nhánh công việc lên nhánh nền. Trong ngữ cảnh đó:

- **ours (stage 2):** nội dung của nhánh nền và các commit đã được phát lại thành công trước đó.
- **theirs (stage 3):** nội dung từ commit của nhánh công việc đang được phát lại.

Ví dụ, bạn đang rebase feature/search lên origin/main. Nếu commit hiện tại sửa một phương thức, Git có thể đặt nội dung từ origin/main ở phía ours và phần sửa trong commit feature/search ở phía theirs.

Vì vậy, đừng chọn ours chỉ vì tên đó nghe giống “nhánh của tôi”. Trong rebase, điều này có thể khiến bạn giữ phần của nhánh nền và bỏ phần thay đổi đang được phát lại.

Có thể xem riêng từng phía khi file còn unmerged:

~~~bash
git show :2:src/SearchService.java
git show :3:src/SearchService.java
~~~

Nếu muốn tạm lấy nguyên một phía để tiếp tục chỉnh sửa, có thể dùng:

~~~bash
# Lấy phiên bản stage 2 (ours) vào working tree
git restore --ours --worktree -- src/SearchService.java

# Hoặc lấy phiên bản stage 3 (theirs) vào working tree
git restore --theirs --worktree -- src/SearchService.java
~~~

Hai lệnh trên thay nội dung working tree của tệp bằng một phía. Sau đó vẫn phải đọc lại, kết hợp logic cần thiết và stage kết quả. Chọn toàn bộ một phía có thể làm mất thay đổi của phía còn lại.

## Quy trình giải quyết xung đột trong rebase

Một vòng xử lý conflict thường gồm các bước sau:

1. Xem trạng thái rebase và commit đang được phát lại.
2. Xem nội dung xung đột cùng phiên bản của hai phía.
3. Chỉnh sửa tệp để tạo kết quả cuối cùng.
4. Kiểm tra marker, nội dung và khoảng trắng.
5. Stage các tệp đã giải quyết.
6. Chạy kiểm tra phù hợp rồi tiếp tục rebase.
7. Lặp lại nếu commit tiếp theo cũng xung đột.

### Bước 1: Xác định các tệp xung đột

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Đọc cả thông báo rebase để xác định thao tác đang chạy. Nếu có nhiều tệp, xử lý từng tệp theo mục tiêu thay đổi của commit hiện tại.

### Bước 2: Đọc phần khác biệt

~~~bash
git diff
git diff --cc
git rebase --show-current-patch
~~~

git diff --cc hiển thị combined diff cho những tệp đang xung đột. Kết hợp thông tin này với patch của REBASE_HEAD và lịch sử nhánh để hiểu ngữ cảnh.

Đối với mỗi tệp, xác định:

- Nhánh nền đã thay đổi phần nào?
- Commit đang phát lại muốn thay đổi điều gì?
- Hai thay đổi có phụ thuộc lẫn nhau không?
- Có thể kết hợp cả hai hành vi không?
- Có API, cấu hình, schema hoặc kiểm thử nào cần cập nhật cùng lúc không?

### Bước 3: Chỉnh sửa nội dung cuối cùng

Giả sử nhánh nền bổ sung kiểm tra quyền xuất báo cáo, còn commit của nhánh công việc thêm bộ lọc ngày. Hai thay đổi cùng sửa phương thức:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    // Git không thể tự kết hợp hai thay đổi
}
~~~

Kết quả cần giữ cả việc kiểm tra quyền và bộ lọc:

~~~java
public Report exportReport(User user, ReportFilter filter) {
    permissionService.requireCanExport(user);

    return reportService.createReport(filter);
}
~~~

Ví dụ chỉ minh họa cách kết hợp hai yêu cầu. Trong dự án thực tế, hãy giữ đúng hợp đồng API, quy tắc phân quyền, xử lý lỗi và các trường hợp biên hiện có.

Nếu conflict nằm trong tệp cấu hình, hãy kiểm tra khóa, kiểu dữ liệu, profile và giá trị mặc định. Nếu nằm trong dependency manifest hoặc lockfile, cần xác nhận phiên bản thư viện tương thích và lockfile được sinh nhất quán. Với conflict rename hoặc delete, xác định rõ đường dẫn và nội dung nào cần tồn tại sau khi rebase.

### Bước 4: Kiểm tra marker và diff

Tìm marker xung đột trong các tệp đã sửa:

~~~bash
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/SearchService.java config/application.yml
~~~

Nếu không có kết quả và lệnh trả mã thoát 1, không tìm thấy dòng khớp. Nếu công cụ báo lỗi đọc tệp hoặc đường dẫn, cần xử lý lỗi đó trước khi kết luận. Các chuỗi marker có thể xuất hiện hợp lệ trong tài liệu hoặc fixture kiểm thử; hãy đánh giá theo ngữ cảnh.

Đọc lại nội dung chưa stage và kiểm tra whitespace:

~~~bash
git diff
git diff --check
~~~

Không chỉ xóa marker rồi tiếp tục. Hãy xác nhận logic cuối cùng đáp ứng mục tiêu của cả nhánh nền và commit đang được phát lại.

### Bước 5: Stage kết quả

Sau khi nội dung đã đúng, stage từng tệp:

~~~bash
git add -- src/SearchService.java config/application.yml
~~~

Nếu quyết định xóa tệp:

~~~bash
git rm -- path/to/obsolete-file
~~~

Kiểm tra lại index và phần thay đổi đã stage:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
git diff --cached
git diff --cached --check
~~~

Không còn đường dẫn unmerged là điều kiện cần để tiếp tục. Đọc staged diff để chắc chắn Git sẽ ghi nhận đúng kết quả đã giải quyết.

### Bước 6: Kiểm tra hành vi rồi tiếp tục

Chạy kiểm tra phù hợp với khu vực vừa thay đổi, ví dụ unit test, kiểm tra cú pháp cấu hình hoặc build module. Nếu conflict liên quan tới phân quyền, API, truy vấn hay dữ liệu, kiểm tra các trường hợp nghiệp vụ tương ứng.

Khi đã stage đầy đủ và sẵn sàng áp dụng commit hiện tại:

~~~bash
git rebase --continue
~~~

Git sẽ tiếp tục phát lại commit. Nếu commit kế tiếp không có xung đột, quá trình tiếp tục tự động. Nếu commit kế tiếp cũng xung đột, Git lại dừng và bạn lặp lại quy trình trên.

Một lần rebase có thể có nhiều vòng conflict. Sau mỗi lần --continue, hãy đọc lại git status để biết Git đã hoàn tất hay đang xử lý commit khác.

## Khi nào dùng git rebase --continue?

Dùng --continue khi bạn muốn giữ thay đổi của commit hiện tại sau khi đã giải quyết xung đột.

Điều kiện trước khi chạy:

- Đã đọc và chỉnh sửa tất cả tệp xung đột.
- Các tệp cần giữ đã được stage bằng git add hoặc git rm.
- Không còn đường dẫn unmerged.
- Staged diff phản ánh đúng nội dung cần commit.
- Các kiểm tra phù hợp đã được thực hiện.

Ví dụ:

~~~bash
git status
git diff --name-only --diff-filter=U
git diff --cached
git rebase --continue
~~~

Git có thể mở trình soạn thảo để xác nhận thông điệp commit. Sau đó, Git phát lại commit tiếp theo nếu còn.

Nếu rebase dừng lại ở một conflict khác, xử lý và tiếp tục lần nữa. Không giả định một lần chạy --continue là đủ cho toàn bộ rebase.

### Khi commit hiện tại trở thành empty

Đôi khi thay đổi trong commit đang phát lại đã có sẵn trên nhánh nền hoặc được tích hợp bởi một commit khác. Sau khi giải quyết, Git có thể thông báo commit hiện tại không còn thay đổi để áp dụng.

Hãy kiểm tra patch và nội dung hiện tại trước khi quyết định. Nếu commit không còn tạo ra thay đổi cần thiết, có thể dùng:

~~~bash
git rebase --skip
~~~

Nếu commit rỗng có ý nghĩa đặc biệt theo quy trình của nhóm, chẳng hạn dùng để ghi nhận mốc hoặc phục vụ automation, hãy xem xét chính sách giữ commit rỗng và tùy chọn rebase phù hợp. Không bỏ qua commit chỉ để làm cho tiến trình chạy tiếp.

## Khi nào dùng git rebase --skip?

--skip yêu cầu Git bỏ qua commit đang được phát lại và tiếp tục với commit tiếp theo trong hàng đợi rebase.

Lệnh này phù hợp khi đã xác nhận phần thay đổi của commit hiện tại không cần xuất hiện trong kết quả cuối. Các trường hợp thường gặp:

- Thay đổi của commit đã được đưa vào nhánh nền bằng một commit khác.
- Commit trở thành rỗng vì kết quả mong muốn đã có sẵn.
- Thay đổi của commit đã lỗi thời và nhóm quyết định không giữ nó.
- Sau khi xem xét, commit hiện tại không còn thuộc mục tiêu của nhánh.

Ví dụ:

~~~bash
git status
git rebase --show-current-patch
git show REBASE_HEAD
~~~

Sau khi xác nhận không cần giữ thay đổi của commit hiện tại:

~~~bash
git rebase --skip
~~~

Git bỏ qua patch của commit đó và tiếp tục rebase. Nếu commit tiếp theo xung đột, Git sẽ dừng lại để bạn xử lý.

### Hậu quả của việc skip

Giả sử nhánh feature có ba commit:

~~~text
A -- B -- C
     ^
     commit B đang gây conflict
~~~

Nếu dùng --skip tại B, Git không đưa thay đổi của B vào kết quả rebase. Commit C vẫn có thể được phát lại, nhưng nếu C phụ thuộc vào thay đổi của B, nó có thể tiếp tục xung đột hoặc không còn hoạt động đúng.

Do đó, trước khi skip, hãy tự hỏi:

- Nội dung của commit đã có trong nhánh nền chưa?
- Có commit nào sau đó phụ thuộc vào thay đổi này không?
- Bỏ commit có làm mất kiểm thử, tài liệu hoặc sửa lỗi cần thiết không?
- Nhánh sau khi bỏ commit còn đáp ứng mục tiêu ban đầu không?

Nếu cần giữ một phần thay đổi, hãy giải quyết conflict và dùng --continue. Nếu muốn bỏ toàn bộ công việc rebase và quay lại trạng thái trước đó, dùng --abort.

## Khi nào dùng git rebase --abort?

--abort hủy toàn bộ tiến trình rebase hiện tại và đưa HEAD về nhánh hoặc trạng thái ban đầu khi bắt đầu rebase.

Dùng lệnh này khi:

- Chọn nhầm nhánh nền hoặc nhánh đích.
- Rebase đang tạo ra quá nhiều xung đột và cần đánh giá lại cách tích hợp.
- Phát hiện các commit không phù hợp để phát lại.
- Muốn dừng để trao đổi với nhóm hoặc chuẩn bị lại nhánh.
- Không thể xác định kết quả giải quyết an toàn ở thời điểm hiện tại.

Ví dụ:

~~~bash
git status
git rebase --abort
git status
git branch --show-current
~~~

Sau khi abort, kiểm tra lại nhánh, lịch sử và working tree. Các thay đổi đã có trước khi bắt đầu rebase được xử lý theo trạng thái mà Git khôi phục; nếu đã dùng --autostash, Git sẽ áp dụng lại stash được tạo tự động và có thể phát sinh xung đột khi áp dụng stash.

--abort không xóa commit đã tồn tại trước khi rebase. Nó hủy quá trình phát lại đang dang dở và đưa nhánh về trạng thái ban đầu của thao tác.

### Phân biệt --abort và --quit

Git còn có lệnh:

~~~bash
git rebase --quit
~~~

--quit dừng theo dõi tiến trình rebase nhưng giữ HEAD, index và working tree ở trạng thái hiện tại. Lệnh này không đưa nhánh trở lại vị trí ban đầu như --abort. Nếu dùng autostash, stash tự động được giữ trong stash list.

Chỉ dùng --quit khi bạn chủ động muốn giữ trạng thái hiện tại và tự xử lý tiếp. Khi mục tiêu là hủy rebase và quay lại trạng thái trước lúc bắt đầu, dùng --abort.

## So sánh ba lựa chọn điều khiển rebase

| Tiêu chí | --continue | --skip | --abort |
|---|---|---|---|
| Mục đích | Giữ và áp dụng commit hiện tại | Bỏ commit hiện tại | Hủy toàn bộ rebase |
| Yêu cầu giải quyết conflict | Có, rồi stage kết quả | Không cần giữ patch hiện tại; phải xác nhận có thể bỏ | Không cần giải quyết để tiếp tục |
| Commit hiện tại | Được phát lại thành commit mới | Bị bỏ qua | Nhánh được khôi phục về lịch sử trước rebase, nơi commit gốc vẫn còn |
| Commit tiếp theo | Tiếp tục xử lý | Tiếp tục xử lý | Không phát lại |
| Trạng thái cuối | Rebase tiếp tục hoặc hoàn tất | Rebase tiếp tục hoặc hoàn tất | Trở về trạng thái trước rebase |

Một cách ghi nhớ:

- Muốn giữ commit sau khi sửa xung đột: --continue.
- Muốn bỏ commit đang được phát lại: --skip.
- Muốn dừng toàn bộ và quay lại ban đầu: --abort.

## Ví dụ quy trình hoàn chỉnh

Giả sử bạn đang cập nhật nhánh feature/search trên nền origin/main và commit đầu tiên gặp conflict:

~~~bash
# Cập nhật thông tin remote
git fetch origin

# Bắt đầu rebase
git switch feature/search
git rebase origin/main

# Git dừng vì xung đột: xem trạng thái và commit hiện tại
git status
git rebase --show-current-patch
git diff --name-only --diff-filter=U

# Chỉnh sửa các tệp bị xung đột trong editor
# Sau đó đọc lại nội dung và kiểm tra marker
rg -n '^(<<<<<<<|=======|>>>>>>>|\|\|\|\|\|\|\|)' -- src/SearchService.java

# Kiểm tra diff và stage kết quả
git diff
git diff --check
git add -- src/SearchService.java
git status
git diff --cached

# Giữ commit sau khi đã giải quyết
git rebase --continue

# Nếu commit tiếp theo cũng conflict, lặp lại các bước xử lý
git status

# Sau khi rebase hoàn tất, xác nhận kết quả
git status
git log --oneline --graph --decorate -n 12
git diff --stat origin/main...HEAD
~~~

Trong ví dụ, nếu sau khi xem patch nhận thấy commit đang xử lý đã được áp dụng trên origin/main và không còn nội dung cần giữ, có thể chọn --skip thay cho --continue. Nếu nhận thấy đã bắt đầu rebase sai hướng hoặc cần dừng toàn bộ, dùng --abort.

Không chạy cả ba lệnh liên tiếp. Chúng là ba quyết định thay thế nhau dựa trên trạng thái và mục tiêu của bạn.

## Xác minh sau khi rebase hoàn tất

Khi Git báo rebase thành công, kiểm tra trạng thái:

~~~bash
git status
git branch --show-current
git log --oneline --graph --decorate -n 15
~~~

Xác nhận:

- Không còn thông báo rebase đang diễn ra.
- Nhánh hiện tại là nhánh công việc mong muốn.
- Các commit cần giữ có trong lịch sử.
- Commit đã skip không còn thay đổi cần thiết bị mất.
- Diff so với nhánh nền chỉ chứa thay đổi thuộc mục tiêu.
- Các test và build liên quan đã đạt.

Xem phần thay đổi của nhánh so với nhánh nền:

~~~bash
git diff --stat origin/main...HEAD
git diff origin/main...HEAD
~~~

Chạy lại các kiểm thử cần thiết. Rebase thay đổi mã commit, vì vậy test trước rebase chưa đủ để xác nhận kết quả sau rebase.

### Nếu nhánh đã được push trước khi rebase

Rebase tạo commit mới với mã định danh khác. Nếu nhánh đã được push và người khác đang dựa vào lịch sử cũ, hãy trao đổi với nhóm trước khi cập nhật remote.

Khi nhóm đồng ý cập nhật lịch sử đã viết lại, thường dùng:

~~~bash
git fetch origin
git push --force-with-lease origin feature/search
~~~

--force-with-lease kiểm tra remote ref còn ở trạng thái mà local mong đợi trước khi cập nhật cưỡng bức. Lệnh này giúp tránh ghi đè thay đổi mới mà bạn chưa fetch, nhưng vẫn có thể thay thế lịch sử remote. Chỉ sử dụng khi có quyền và đã phối hợp với người cùng làm trên nhánh.

Nếu nhánh chỉ tồn tại cục bộ, không cần push cưỡng bức.

## Lỗi thường gặp

| Tình huống | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Chạy --continue nhưng Git vẫn dừng | Còn tệp unmerged hoặc chưa stage | Kiểm tra git status, git ls-files -u và stage các tệp đã giải quyết |
| Conflict lặp lại ở nhiều commit | Mỗi commit được phát lại có thể chạm cùng vùng mã | Xử lý từng vòng và đọc patch của REBASE_HEAD |
| Dùng --skip làm mất tính năng | Đã bỏ qua commit chứa thay đổi cần thiết | Xem lại commit, cân nhắc abort rồi thực hiện lại rebase với cách giải quyết đúng |
| Dùng --abort khi chỉ muốn bỏ một commit | Nhầm ý nghĩa abort và skip | Xác nhận mục tiêu trước khi chọn lệnh |
| Chọn nhầm ours hoặc theirs | Áp dụng trực giác của merge vào rebase | Nhớ stage 2 là nền và stage 3 là commit đang phát lại trong rebase |
| Rebase hoàn tất nhưng test lỗi | Kết quả kết hợp có thể sai logic hoặc thiếu thay đổi phụ thuộc | Đọc diff, lịch sử và chạy lại test theo hành vi bị ảnh hưởng |
| Push bị từ chối sau rebase | Commit hash đã thay đổi | Đồng bộ và phối hợp; chỉ dùng force-with-lease khi được phép |

## Thói quen an toàn khi xử lý rebase conflict

- Fetch nhánh nền và xác nhận đúng nhánh trước khi bắt đầu.
- Kiểm tra working tree sạch hoặc cô lập rõ các thay đổi đang làm.
- Đọc commit hiện tại bằng git rebase --show-current-patch trước khi sửa.
- Hiểu đúng ours/theirs trong bối cảnh rebase.
- Stage từng tệp đã giải quyết và đọc staged diff trước khi continue.
- Chỉ skip khi đã xác nhận toàn bộ patch của commit không cần được giữ.
- Dùng abort khi muốn hủy toàn bộ tiến trình và trở về trạng thái ban đầu.
- Chạy lại test sau khi rebase hoàn tất.
- Phối hợp với nhóm trước khi push lịch sử đã được viết lại.

## Ghi nhớ

Rebase có thể dừng ở bất kỳ commit nào khi Git không thể tự kết hợp thay đổi. Hãy xem git status và patch của REBASE_HEAD để hiểu commit đang được phát lại, giải quyết từng tệp, stage kết quả và kiểm tra hành vi. Dùng git rebase --continue để giữ commit đã sửa, --skip để bỏ commit hiện tại sau khi xác nhận thay đổi không cần thiết, hoặc --abort để hủy toàn bộ rebase và quay lại trạng thái ban đầu. Sau khi hoàn tất, đọc lại lịch sử, diff và chạy kiểm thử trước khi chia sẻ nhánh.

