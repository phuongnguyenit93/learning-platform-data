# Chiến lược hợp nhất và phân biệt ours với tùy chọn -X ours

Khi hợp nhất hai nhánh, Git phải tạo một snapshot kết hợp từ lịch sử và nội dung của các nhánh. Có những lần Git tự kết hợp được mọi thay đổi; cũng có lúc hai nhánh sửa cùng một vùng nội dung và cần quy tắc giải quyết xung đột. Git cung cấp nhiều merge strategy và strategy option để điều khiển quá trình này.

Một khác biệt rất quan trọng là giữa chiến lược -s ours và tùy chọn -X ours:

- -s ours chọn chiến lược hợp nhất mà kết quả tree luôn lấy từ nhánh hiện tại, bỏ qua toàn bộ nội dung tree của nhánh được merge.
- -X ours là tùy chọn của một chiến lược merge như ort; nó ưu tiên phiên bản phía hiện tại ở những phần xung đột, nhưng vẫn đưa các thay đổi không xung đột từ nhánh kia vào kết quả.

Hai lệnh có chữ ours nhưng mục đích hoàn toàn khác nhau. Dùng nhầm -s ours có thể khiến toàn bộ thay đổi từ nhánh kia không xuất hiện trong source tree dù lịch sử của nhánh đó được đánh dấu là đã merge.

## 1. Merge strategy quyết định cách Git kết hợp các tree

Khi merge một nhánh vào nhánh hiện tại, Git thường tìm merge base — commit tổ tiên chung gần nhất — rồi so sánh thay đổi từ base tới mỗi phía. Chiến lược merge xác định cách Git tạo tree kết quả từ các đầu vào này.

Ví dụ, hai nhánh cùng phát triển từ commit A:

~~~text
             B---C  feature
            /
A----------+
            \
             D---E  main (HEAD)
~~~

Khi đang ở main và chạy:

~~~bash
git merge feature
~~~

Git cần kết hợp thay đổi từ B, C với thay đổi từ D, E. Nếu không có xung đột và main có thể fast-forward, Git có thể chỉ di chuyển ref. Nếu hai nhánh đã phân kỳ, Git thường tạo merge commit sau khi kết hợp tree.

Merge strategy và cách tạo merge commit là hai khái niệm liên quan nhưng khác nhau. Strategy xử lý nội dung tree; các tùy chọn như --ff-only, --no-ff hoặc --squash điều khiển cách ghi nhận kết quả trong lịch sử.

## 2. Chiến lược mặc định ort

Với merge hai đầu nhánh, Git hiện đại sử dụng chiến lược ort làm mặc định. Tên ort viết tắt của "Ostensibly Recursive's Twin"; chiến lược này được thiết kế để thay thế recursive trong các phiên bản Git mới.

Có thể chỉ định rõ:

~~~bash
git merge -s ort feature
~~~

Trong phần lớn workflow thông thường, chỉ cần:

~~~bash
git merge feature
~~~

Git sẽ tự chọn chiến lược mặc định phù hợp.

ort xử lý các thay đổi ba chiều dựa trên merge base, nhận diện rename, kết hợp các thay đổi không xung đột và báo các vùng cần giải quyết thủ công. Nó không thể hiểu ý nghĩa nghiệp vụ của code. Kết quả merge không có conflict về mặt văn bản vẫn có thể sai logic hoặc không biên dịch được, vì vậy cần chạy test và review sau merge.

Một số chiến lược khác có mục đích chuyên biệt:

| Strategy | Mục đích chính | Khi cân nhắc |
|---|---|---|
| ort | Merge hai đầu nhánh theo cơ chế ba chiều hiện đại | Lựa chọn mặc định cho merge thông thường |
| ours | Giữ nguyên tree của nhánh hiện tại, bỏ tree của nhánh được merge | Ghi nhận lịch sử nhánh kia đã được tích hợp về mặt ancestry nhưng nội dung của nó bị thay thế |
| octopus | Kết hợp từ ba đầu nhánh trở lên trong một lần merge | Gom nhiều nhánh nhỏ, độc lập và không cần giải quyết conflict phức tạp |
| subtree | Điều chỉnh cấu trúc tree để merge một dự án con vào một thư mục của dự án cha | Tích hợp repository con theo mô hình subtree |
| resolve | Chiến lược cũ cho merge hai đầu nhánh, với khả năng xử lý hạn chế hơn | Chỉ gặp trong workflow hoặc repository cũ |

Với nhiều nhánh được truyền vào cùng một lệnh merge, Git thường chọn octopus. Chiến lược này được thiết kế cho các nhánh có thể kết hợp gọn; nếu cần giải quyết conflict phức tạp, hãy merge từng nhánh riêng bằng ort để kiểm soát từng bước.

## 3. Chiến lược -s ours: giữ nguyên toàn bộ tree hiện tại

Cú pháp:

~~~bash
git merge --no-ff -s ours feature/legacy
~~~

Nên dùng --no-ff khi mục tiêu là ghi nhận một merge commit bằng strategy ours. Nếu fast-forward được phép, Git có thể chỉ di chuyển branch tới commit phía kia mà không chạy quá trình tạo merge result theo strategy; khi đó tree của nhánh kia sẽ xuất hiện.

Khi dùng strategy ours:

- Tree của kết quả merge giống hệt tree của HEAD trước merge.
- Các thay đổi file từ feature/legacy không được đưa vào tree kết quả.
- Khi merge không fast-forward (hoặc có --no-ff), Git tạo merge commit có parent là HEAD hiện tại và tip của feature/legacy.
- Lịch sử của nhánh feature/legacy được nối vào đồ thị commit và được xem là đã được merge về mặt ancestry.

Ví dụ:

~~~text
Trước merge:

main:       A---B  (HEAD)
                 \
feature:          C---D

Sau git merge --no-ff -s ours feature:

main:       A---B---------M  (HEAD)
                 \       /
feature:          C---D

Tree của M giống tree của B.
~~~

Dùng chiến lược này khi bạn có chủ đích giữ lịch sử nhánh cũ nhưng không muốn lấy nội dung của nhánh đó vào tree hiện tại. Một tình huống có thể gặp là nhánh legacy đã được thay thế hoàn toàn bởi một triển khai mới, nhưng nhóm muốn ghi nhận quan hệ lịch sử để Git biết nhánh cũ đã được xử lý.

Ví dụ:

~~~bash
git switch main
git merge --no-ff -s ours legacy/old-implementation \
  -m "merge: mark old implementation as superseded"
~~~

Sau merge, kiểm tra:

~~~bash
git show --no-patch --pretty=raw HEAD
git diff HEAD^1 HEAD
git merge-base --is-ancestor legacy/old-implementation HEAD
~~~

Nếu merge thành công, commit mới có hai parent; diff giữa parent thứ nhất và merge commit không có thay đổi tree vì strategy ours giữ nguyên tree phía hiện tại. Lệnh kiểm tra ancestry trả mã thoát 0 nếu tip nhánh legacy là tổ tiên của merge commit.

**Cảnh báo:** strategy ours không phải cách nhanh để bỏ qua conflict. Nó bỏ toàn bộ nội dung tree từ nhánh được merge. Vì Git đã ghi nhận nhánh đó là tổ tiên của merge commit, những lần merge sau từ cùng lịch sử có thể không đưa lại các thay đổi đã bị bỏ qua. Chỉ sử dụng khi quyết định bỏ nội dung là có chủ đích và đã được review.

## 4. Tùy chọn -X ours: chỉ ưu tiên phía hiện tại ở vùng xung đột

Cú pháp:

~~~bash
git merge -X ours feature/search
~~~

Ở đây Git vẫn dùng merge strategy, thông thường là ort. Tùy chọn -X ours yêu cầu chiến lược ưu tiên nội dung phía hiện tại ở những phần xảy ra conflict.

Điểm quan trọng:

- Thay đổi không xung đột từ feature/search vẫn được đưa vào kết quả.
- Với các hunk văn bản xung đột, Git chọn nội dung phía hiện tại.
- Với file nhị phân, việc chọn phía có thể áp dụng cho toàn bộ nội dung file vì Git không thể hợp nhất từng dòng nhị phân.
- Git vẫn tạo kết quả merge theo strategy đã chọn; đây không phải strategy độc lập.

Ví dụ hai nhánh cùng sửa file settings.conf.

Phiên bản chung:

~~~ini
timeout=30
format=json
~~~

Nhánh main sửa:

~~~ini
timeout=45
format=json
metrics=true
~~~

Nhánh feature/retry sửa:

~~~ini
timeout=60
format=json
retries=3
~~~

Dòng timeout bị sửa khác nhau ở hai phía nên xung đột. Hai dòng metrics và retries là thay đổi không xung đột, vì vậy Git có thể giữ cả hai.

Khi đang ở main:

~~~bash
git merge -X ours feature/retry
~~~

Tree kết quả dự kiến:

~~~ini
timeout=45
format=json
metrics=true
retries=3
~~~

Dòng timeout lấy từ main; retries từ feature vẫn được giữ. Đây là khác biệt cốt lõi so với -s ours, vốn sẽ giữ nguyên toàn bộ tree của main và không đưa retries vào.

## 5. Tùy chọn -X theirs: ưu tiên phía được merge

Cú pháp:

~~~bash
git merge -X theirs feature/retry
~~~

Trong một lệnh merge thông thường:

- Ours là nhánh hiện tại, tức nhánh mà HEAD đang đứng.
- Theirs là nhánh được đưa vào lệnh merge.
- -X theirs chọn phía được merge ở những phần xung đột.
- Các thay đổi không xung đột từ cả hai phía vẫn được kết hợp.

Với ví dụ settings.conf, nếu chạy từ main và dùng -X theirs, kết quả dự kiến là:

~~~ini
timeout=60
format=json
metrics=true
retries=3
~~~

Dòng timeout lấy từ feature/retry, còn các thay đổi không xung đột từ main và feature vẫn được giữ.

Không có built-in merge strategy chuẩn tên theirs tương ứng với strategy ours. Cú pháp -s theirs không phải cách thay thế hợp lệ cho -X theirs trong Git thông thường. Hãy phân biệt strategy với strategy option.

## 6. So sánh trực tiếp -s ours và -X ours

| Tiêu chí | -s ours | -X ours |
|---|---|---|
| Loại tùy chọn | Chọn merge strategy | Chọn strategy option |
| Phạm vi ưu tiên ours | Toàn bộ tree kết quả | Các phần xung đột |
| Thay đổi không xung đột từ nhánh kia | Bị bỏ qua | Được giữ trong kết quả |
| Tree kết quả | Giống tree của HEAD trước merge | Là kết quả kết hợp sau khi ưu tiên phía ours ở conflict |
| Merge ancestry | Vẫn tạo quan hệ parent với nhánh kia | Vẫn tạo quan hệ parent với nhánh kia |
| Mục đích | Đánh dấu lịch sử nhánh kia đã được xử lý nhưng không lấy nội dung của nó | Giải quyết tự động conflict theo hướng ưu tiên nội dung hiện tại |
| Rủi ro chính | Bỏ toàn bộ nội dung nhánh kia nhưng vẫn ghi nhận ancestry | Có thể chọn nội dung sai ở vùng conflict nếu không review |

Cách ghi nhớ:

~~~text
-s ours
  = dùng nguyên tree phía hiện tại cho merge result

-X ours
  = merge bình thường, nhưng ưu tiên phía hiện tại ở phần xung đột
~~~

Nếu mục tiêu là "giữ các thay đổi không xung đột từ cả hai nhánh, chỉ chọn phiên bản của mình tại dòng bị conflict", hãy cân nhắc -X ours hoặc giải quyết conflict thủ công. Nếu mục tiêu là "đánh dấu nhánh kia đã được thay thế và không lấy bất kỳ nội dung nào của nó", mới cân nhắc -s ours.

## 7. Ours và theirs phụ thuộc vào hướng merge

Giả sử bạn đang đứng trên main và chạy:

~~~bash
git merge feature/login
~~~

Khi đó:

- Ours = main, branch hiện tại.
- Theirs = feature/login, branch được merge vào.

Nếu đổi hướng thao tác, ý nghĩa cũng đổi. Đứng trên feature/login và merge main thì ours là feature/login, theirs là main.

Không nên hiểu ours là "nhánh chính" hoặc theirs là "nhánh phụ". Đây là khái niệm tương đối theo thao tác đang thực hiện.

Kiểm tra branch hiện tại trước merge:

~~~bash
git branch --show-current
git status -sb
git log -1 --oneline --decorate
~~~

Điều này đặc biệt quan trọng khi chạy script merge tự động hoặc khi nhiều branch có tên tương tự.

## 8. Ours và theirs trong rebase có thể đảo với trực giác

Khi rebase, Git phát lại từng commit của branch công việc lên một base mới. Trong quá trình giải quyết conflict, cách Git gọi ours và theirs khác với suy nghĩ "nhánh tôi đang làm là ours".

Ví dụ:

~~~bash
git switch feature/login
git rebase main
~~~

Khi một commit của feature/login đang được phát lại lên main:

- Ours thường là nhánh đích mà các commit đang được phát lại lên, tức main cộng với những commit đã replay thành công.
- Theirs là commit từ branch công việc hiện đang được replay.
- Vì vậy, --ours trong conflict của rebase có thể lấy phiên bản từ main, còn --theirs lấy phiên bản từ commit feature đang được áp dụng.

Quy tắc này dễ gây nhầm lẫn khi chuyển từ merge sang rebase. Hãy đọc thông báo rebase, xem stage trong index và kiểm tra nội dung thực tế trước khi chọn.

Nếu muốn xem các phiên bản đang conflict:

~~~bash
git status
git ls-files -u
~~~

Với một file cụ thể, có thể xem các stage nếu tồn tại:

~~~bash
git show :1:path/to/file
git show :2:path/to/file
git show :3:path/to/file
~~~

Stage 1 thường là base chung, stage 2 là ours theo ngữ cảnh merge/rebase hiện tại, stage 3 là theirs. Không phải mọi loại conflict đều có đủ cả ba stage; ví dụ add/add có thể không có stage 1.

## 9. Dùng -s và -X đúng vị trí

Cú pháp tổng quát:

~~~bash
git merge -s <strategy> -X <strategy-option> <branch>
~~~

Ví dụ dùng ort và ưu tiên ours:

~~~bash
git merge -s ort -X ours feature/search
~~~

Vì ort là mặc định cho merge hai đầu nhánh, có thể rút gọn:

~~~bash
git merge -X ours feature/search
~~~

Ví dụ dùng chiến lược ours:

~~~bash
git merge --no-ff -s ours feature/obsolete
~~~

Không nhầm các tùy chọn sau:

| Cú pháp | Vai trò |
|---|---|
| -s ort | Chọn chiến lược ort |
| -s ours | Chọn chiến lược giữ toàn bộ tree hiện tại |
| -X ours | Tùy chọn ưu tiên phía hiện tại ở vùng conflict |
| -X theirs | Tùy chọn ưu tiên phía được merge ở vùng conflict |
| --no-ff | Không cho fast-forward; buộc tạo merge commit nếu merge thành công |
| --ff-only | Chỉ chấp nhận fast-forward |
| --squash | Chuẩn bị kết quả tree/index như merge nhưng không tạo merge commit và không ghi nhận ancestry bằng merge commit |
| --no-commit | Dừng trước khi tạo merge commit để review kết quả; kết hợp --no-ff nếu muốn chắc chắn không fast-forward |

--no-ff, --ff-only, --squash và --no-commit không phải merge strategy. Chúng điều khiển cách ghi nhận hoặc dừng quá trình merge.

## 10. Một số strategy option hữu ích của ort

Tùy chọn -X không chỉ có ours và theirs. Một số option khác có thể giúp xử lý khác biệt cụ thể:

| Option | Tác dụng |
|---|---|
| -X patience | Dùng thuật toán diff patience để tìm cách ghép thay đổi |
| -X diff-algorithm=histogram | Chọn histogram diff algorithm |
| -X ignore-space-change | Bỏ qua khác biệt về lượng whitespace khi so sánh |
| -X ignore-all-space | Bỏ qua mọi khác biệt whitespace trong quá trình phát hiện conflict |
| -X ignore-space-at-eol | Bỏ qua whitespace ở cuối dòng |
| -X renormalize | Chạy clean filter ảo trên ba phiên bản file trước khi merge, hữu ích khi thay đổi quy tắc chuẩn hóa |
| -X find-renames | Bật phát hiện rename |
| -X find-renames=80% | Đặt ngưỡng tương đồng cho phát hiện rename |
| -X no-renames | Tắt phát hiện rename |
| -X subtree hoặc -X subtree=path | Điều chỉnh tree level khi tích hợp nội dung theo mô hình subtree |

Các option được hỗ trợ có thể phụ thuộc strategy và phiên bản Git. Nếu Git báo option không hợp lệ, kiểm tra tài liệu của phiên bản đang dùng và chiến lược đã chọn.

Không dùng ignore-space option để che giấu thay đổi có ý nghĩa. Ví dụ, khoảng trắng trong chuỗi, YAML, Python hoặc Makefile có thể làm thay đổi hành vi. Hãy xem diff và chạy test sau merge.

## 11. Khi nào nên dùng tự động ưu tiên ours/theirs?

Tự động ưu tiên có thể hữu ích khi nhóm có quy ước rõ ràng cho một vùng nội dung và hiểu chính xác các xung đột dự kiến. Ví dụ:

- Một file sinh tự động có quy trình tái tạo rõ và nhóm thống nhất nguồn nào là chuẩn.
- Một nhánh cấu hình được duy trì có chủ đích ở một phía, còn các thay đổi không xung đột vẫn cần tích hợp.
- Một lần merge có nhiều conflict lặp lại và nhóm đã xác định cách chọn nhất quán.

Không nên dùng -X ours chỉ để làm merge "xanh" hoặc tránh đọc conflict. Nếu hai phía sửa cùng logic nghiệp vụ, chọn một bên tự động có thể làm mất yêu cầu của bên kia.

Với file cấu hình, hãy xem từng khóa và ý nghĩa của nó. Với code, hãy kiểm tra cả hành vi, test và API. Với file nhị phân, cần hiểu rằng Git thường không thể kết hợp nội dung từng phần như file text; ưu tiên một phía có thể thay toàn bộ file.

## 12. Giải quyết conflict thủ công khi cần kiểm soát chính xác

Nếu không muốn áp dụng chính sách tự động, merge theo cách bình thường:

~~~bash
git merge feature/search
~~~

Khi có conflict, Git dừng merge và đánh dấu file chưa được giải quyết. Kiểm tra:

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Mở từng file, đọc các marker:

~~~text
<<<<<<< HEAD
Nội dung phía branch hiện tại
=======
Nội dung phía branch được merge
>>>>>>> feature/search
~~~

Kết hợp nội dung đúng, xóa marker rồi stage file:

~~~bash
git add path/to/file
~~~

Nếu cần chọn toàn bộ phiên bản ours hoặc theirs cho một file, có thể dùng:

~~~bash
git restore --ours --worktree -- path/to/file
git add path/to/file
~~~

Hoặc:

~~~bash
git restore --theirs --worktree -- path/to/file
git add path/to/file
~~~

Đây là cách chọn một phía cho file đang unmerged; nó không giống -X ours áp dụng trong lúc strategy tự động xử lý merge. Sau khi stage, kiểm tra:

~~~bash
git status
git diff --cached
~~~

Khi mọi conflict đã được giải quyết, hoàn tất merge:

~~~bash
git merge --continue
~~~

Hoặc tạo merge commit bằng git commit nếu workflow yêu cầu. Nếu muốn hủy merge đang dừng:

~~~bash
git merge --abort
~~~

Chỉ abort sau khi đã cân nhắc thay đổi local trước merge; Git cố gắng khôi phục trạng thái trước khi merge bắt đầu.

## 13. Xem trước merge result trước khi commit

Nếu muốn kiểm tra tree kết quả trước khi tạo merge commit, dùng:

~~~bash
git merge --no-ff --no-commit feature/search
~~~

Git thực hiện merge và cập nhật index/working tree nhưng dừng trước khi tạo commit. Khi đã xem xét:

~~~bash
git status
git diff
git diff --cached
~~~

Chạy test phù hợp. Nếu kết quả đúng, tiếp tục:

~~~bash
git merge --continue
~~~

Nếu không muốn kết quả đó, hủy:

~~~bash
git merge --abort
~~~

Với -X ours, cách này hữu ích để review những hunk đã được tự động chọn. Với -s ours, tree kết quả vốn được giữ nguyên như HEAD; hãy xác nhận rằng bỏ toàn bộ nội dung nhánh kia thực sự là mục đích.

## 14. Thực hành A: quan sát -X ours giữ thay đổi không xung đột

Thực hiện trong repository thử nghiệm, không dùng branch release đang chia sẻ.

Tạo repository và file ban đầu:

~~~bash
mkdir merge-strategy-lab
cd merge-strategy-lab
git init -b main
git config user.name "Git Learner"
git config user.email "learner@example.test"
printf "timeout=30\nformat=json\n" > settings.conf
git add settings.conf
git commit -m "chore: add initial settings"
~~~

Tạo nhánh feature và sửa timeout, đồng thời thêm retries:

~~~bash
git switch -c feature/retry
printf "timeout=60\nformat=json\nretries=3\n" > settings.conf
git add settings.conf
git commit -m "feat: add retry configuration"
~~~

Quay lại main và sửa cùng dòng timeout, đồng thời thêm metrics:

~~~bash
git switch main
printf "timeout=45\nformat=json\nmetrics=true\n" > settings.conf
git add settings.conf
git commit -m "feat: add metrics configuration"
git branch manual-merge-base main
~~~

Kiểm tra lịch sử:

~~~bash
git log --oneline --graph --all
~~~

Merge feature với ưu tiên ours nhưng dừng trước commit:

~~~bash
git merge --no-ff --no-commit -X ours feature/retry
~~~

Đọc kết quả:

~~~bash
git status
git diff --cached -- settings.conf
~~~

Nội dung dự kiến có timeout=45, metrics=true và retries=3. Nếu kết quả đúng, hoàn tất:

~~~bash
git merge --continue
~~~

Xác minh merge commit có hai parent:

~~~bash
git show --no-patch --pretty=raw HEAD
~~~

Điểm cần quan sát: -X ours đã chọn timeout phía main ở vùng xung đột, nhưng vẫn đưa retries từ feature vào kết quả.

## 15. Thực hành B: chứng minh -s ours bỏ toàn bộ tree nhánh được merge

Tiếp tục trong repository thử nghiệm. Tạo branch chứa file riêng:

~~~bash
git switch -c legacy/old-settings
printf "legacy=true\n" > legacy-only.conf
git add legacy-only.conf
git commit -m "feat: add legacy settings"
~~~

Quay lại main:

~~~bash
git switch main
~~~

Ghi nhận lịch sử nhánh legacy nhưng giữ nguyên tree của main:

~~~bash
git merge --no-ff -s ours legacy/old-settings \
  -m "merge: mark legacy settings as superseded"
~~~

Kiểm tra:

~~~bash
git show --no-patch --pretty=raw HEAD
git ls-tree HEAD -- legacy-only.conf
git merge-base --is-ancestor legacy/old-settings HEAD
~~~

Kết quả cần hiểu:

- Merge commit có parent thứ hai là tip legacy/old-settings.
- git ls-tree không liệt kê legacy-only.conf trong tree của main sau merge.
- Lệnh kiểm tra ancestry trả mã thoát 0.
- Lịch sử legacy được kết nối, nhưng nội dung file legacy không được đưa vào tree kết quả.

Đây là hành vi chủ đích của strategy ours. Nếu bạn muốn giữ file legacy-only.conf hoặc các thay đổi khác, không dùng cách này.

## 16. Thực hành C: so sánh kết quả với merge thủ công

Tạo một nhánh từ điểm main trước merge A. Branch manual-merge-base đã được tạo ở bước thực hành A, nên có thể dùng lại để tạo một tình huống conflict độc lập:

~~~bash
git switch -c manual-merge-lab manual-merge-base
git merge feature/retry
~~~

Nếu có conflict, Git đánh dấu file unmerged. Quan sát các phiên bản trong index:

~~~bash
git ls-files -u
git show :1:settings.conf
git show :2:settings.conf
git show :3:settings.conf
~~~

Giải quyết bằng cách viết nội dung mong muốn, stage và hoàn tất merge. So sánh kết quả với merge dùng -X ours để thấy rằng lựa chọn tự động có thể tương đương với một quyết định thủ công cụ thể, nhưng không thay thế việc hiểu ý nghĩa các thay đổi.

## 17. Kiểm tra kết quả merge bằng đồ thị và tree

Sau khi merge, dùng các lệnh:

~~~bash
git log --oneline --graph --decorate --all
git show --no-patch --pretty=raw HEAD
git diff HEAD^1 HEAD
git diff HEAD^2 HEAD
git merge-base --is-ancestor feature/retry HEAD
~~~

Ý nghĩa:

- git log cho thấy hình dạng đồ thị và điểm kết nối.
- git show --pretty=raw cho biết các parent của merge commit.
- git diff HEAD^1 HEAD cho biết tree merge khác parent thứ nhất như thế nào.
- git diff HEAD^2 HEAD cho biết tree merge khác parent thứ hai như thế nào.
- git merge-base --is-ancestor kiểm tra nhánh nguồn đã trở thành tổ tiên của merge commit hay chưa.

Với strategy -s ours, diff từ parent thứ nhất tới merge commit thường rỗng vì tree kết quả giống phía hiện tại. Diff với parent thứ hai có thể lớn vì toàn bộ nội dung nhánh kia không được giữ.

Với -X ours, diff với cả hai parent có thể cho thấy các thay đổi được kết hợp và các vùng conflict đã ưu tiên một phía. Không chỉ dựa vào số dòng diff để đánh giá đúng sai; hãy review nội dung và chạy test.

## 18. Các tùy chọn lịch sử không phải merge strategy

Một số lựa chọn dễ bị nhầm với strategy:

### Fast-forward

~~~bash
git merge --ff-only feature
~~~

Chỉ cho phép di chuyển branch hiện tại tiến lên nếu không cần merge commit. Nếu hai nhánh đã phân kỳ, lệnh từ chối.

### Buộc tạo merge commit

~~~bash
git merge --no-ff feature
~~~

Tạo merge commit ngay cả khi có thể fast-forward. Đây là cách giữ điểm tích hợp rõ ràng trong lịch sử.

### Squash

~~~bash
git merge --squash feature
~~~

Chuẩn bị thay đổi kết hợp trong index và working tree nhưng không tạo merge commit và không ghi nhận quan hệ ancestry bằng merge commit. Sau đó bạn tạo một commit bình thường.

### Dừng trước commit

~~~bash
git merge --no-commit --no-ff feature
~~~

Cho phép review tree/index trước khi tạo merge commit. --no-ff ngăn Git hoàn tất bằng fast-forward trước khi có cơ hội dừng.

Các tùy chọn này có thể kết hợp với chiến lược hoặc option phù hợp, nhưng cần hiểu từng tác động riêng. Ví dụ, -X ours quyết định nội dung vùng conflict; --no-ff quyết định hình dạng lịch sử.

## 19. Những lỗi thường gặp

- **Dùng -s ours để giữ phần lớn thay đổi của mình:** lệnh này bỏ toàn bộ tree của nhánh được merge, kể cả thay đổi không xung đột.
- **Nghĩ -X ours sẽ bỏ toàn bộ nhánh kia:** option này chỉ ưu tiên phía hiện tại ở phần conflict; thay đổi không xung đột vẫn được kết hợp.
- **Dùng -s theirs:** Git thông thường không cung cấp built-in strategy theirs; dùng -X theirs nếu muốn ưu tiên phía được merge tại vùng conflict.
- **Cho rằng ours luôn là main:** ours là branch hiện tại của thao tác merge; đổi hướng merge thì vai trò đổi.
- **Áp dụng trực giác merge vào rebase:** cách gọi ours/theirs trong conflict rebase có thể đảo với suy nghĩ về branch tính năng.
- **Dùng -X ours để né review:** nội dung được chọn tự động vẫn có thể sai logic hoặc làm hỏng tương thích.
- **Nhầm --no-ff là strategy:** đây là tùy chọn điều khiển fast-forward và merge commit.
- **Không kiểm tra tree sau strategy ours:** merge commit có thể tồn tại trong khi file từ branch nguồn hoàn toàn không có trong snapshot.
- **Không chạy test sau merge:** Git chỉ kết hợp nội dung, không chứng minh chương trình hoạt động đúng.

## 20. Quy trình chọn chiến lược

Trước khi merge, trả lời lần lượt:

1. Bạn đang đứng trên branch nào và sẽ merge branch nào vào?
2. Có cần giữ mọi thay đổi không xung đột từ cả hai phía không?
3. Khi có conflict, nhóm có quy tắc rõ ràng để ưu tiên một phía không?
4. Có chủ đích bỏ toàn bộ nội dung tree từ nhánh được merge không?
5. Có cần một merge commit thể hiện điểm tích hợp hay muốn squash?
6. Kết quả có thể được kiểm tra trước commit không?

Chọn hướng xử lý:

| Ý định | Cách làm phù hợp |
|---|---|
| Merge thông thường và giải quyết conflict thủ công | git merge feature |
| Merge thông thường, ưu tiên ours ở conflict | git merge -X ours feature |
| Merge thông thường, ưu tiên theirs ở conflict | git merge -X theirs feature |
| Giữ nguyên tree hiện tại nhưng ghi nhận ancestry nhánh kia | git merge --no-ff -s ours feature |
| Chỉ cho phép fast-forward | git merge --ff-only feature |
| Luôn tạo merge commit | git merge --no-ff feature |
| Lấy kết quả kết hợp nhưng không tạo merge commit | git merge --squash feature |
| Kết hợp nhiều nhánh độc lập trong một lần | git merge branch-a branch-b branch-c, thường dùng octopus nếu không cần xử lý conflict phức tạp |

Nếu chưa chắc, dùng ort mặc định, review conflict thủ công và kiểm tra kết quả. Chỉ chọn -X ours/theirs hoặc -s ours khi mục tiêu đã rõ.

## 21. Checklist trước và sau merge

Trước merge:

- [ ] Working tree và index đã được kiểm tra.
- [ ] Branch hiện tại và branch nguồn được xác nhận.
- [ ] Đã fetch remote nếu branch nguồn đến từ remote.
- [ ] Đã xem merge base và các commit hai phía.
- [ ] Đã chọn đúng strategy hoặc strategy option theo mục đích.
- [ ] Có backup hoặc cách khôi phục phù hợp nếu thao tác có phạm vi lớn.

Sau merge:

- [ ] Không còn file unmerged.
- [ ] Tree kết quả giữ đúng thay đổi cần thiết từ cả hai phía.
- [ ] Nếu dùng -s ours, việc bỏ toàn bộ tree nhánh nguồn là có chủ đích.
- [ ] Parent của merge commit đúng như mong đợi.
- [ ] Đã review diff với cả hai parent khi cần.
- [ ] Test, build và kiểm tra tích hợp đã đạt.
- [ ] Branch và lịch sử đã được chia sẻ theo quy trình nhóm.

## 22. Ghi nhớ

-s ours và -X ours khác nhau ở phạm vi tác động. Strategy -s ours giữ nguyên toàn bộ tree của branch hiện tại nhưng vẫn nối lịch sử nhánh được merge bằng merge commit. Strategy option -X ours dùng trong một chiến lược như ort để ưu tiên nội dung phía hiện tại tại vùng conflict, đồng thời giữ các thay đổi không xung đột từ nhánh kia. Ours và theirs được xác định theo hướng merge; trong rebase, cách gọi có thể khác trực giác. Hãy chọn chiến lược theo mục tiêu lịch sử và nội dung, review tree sau merge, rồi chạy test trước khi chia sẻ kết quả.
