# Kiểm tra trạng thái sạch, nội dung đã đẩy và mốc tag trước khi bàn giao

Trước khi bàn giao một nhánh hoặc phát hành phiên bản, cần chứng minh ba điều: working tree và index không còn thay đổi ngoài dự kiến; commit cần bàn giao đã có trên remote; tag release tồn tại ở remote và trỏ đúng commit. Chỉ nhìn thấy thông báo push thành công là chưa đủ nếu chưa kiểm tra ref đích, branch upstream và commit mà tag đang đánh dấu.

Bài thực hành này dùng một repository Git đã có remote tên origin và branch phát hành release/1.4. Bạn sẽ kiểm tra trạng thái local, đồng bộ thông tin remote, đẩy branch, tạo annotated tag v1.4.0, xác minh cả hai ref từ remote rồi lập bằng chứng bàn giao. Hãy thay tên branch, remote, tag và lệnh test theo dự án thực tế.

## 1. Mục tiêu và điều kiện đầu vào

Kết quả cần đạt:

- Xác định đúng repository root, branch hiện tại và remote.
- Phân biệt thay đổi staged, unstaged, untracked và ignored.
- Xác nhận các commit local đã dựa trên trạng thái remote mới nhất.
- Đẩy đúng branch lên remote và kiểm tra remote branch trỏ tới commit mong muốn.
- Tạo annotated tag cho commit phát hành đã xác minh.
- Đẩy tag cụ thể và xác minh tag object cùng commit đích trên remote.
- Đảm bảo không có thay đổi chưa commit ngoài dự kiến khi bàn giao.
- Ghi lại branch, commit hash, tag, kết quả kiểm thử và trạng thái remote.

Giả định của bài:

| Thành phần | Giá trị ví dụ |
|---|---|
| Remote | origin |
| Branch bàn giao | release/1.4 |
| Tag phát hành | v1.4.0 |
| Commit cần bàn giao | HEAD của release/1.4 |
| Nhánh remote tương ứng | origin/release/1.4 |

Không chạy lệnh push lên branch được bảo vệ nếu quy trình nhóm yêu cầu pull request hoặc release pipeline. Trong trường hợp đó, thực hiện phần kiểm tra local và tạo branch/tag theo chính sách, rồi bàn giao qua quy trình review được quy định.

## 2. Xác nhận bạn đang ở đúng repository và branch

Bắt đầu từ thư mục dự án:

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git status --short --branch
~~~

Kết quả cần xác nhận:

- Repository root đúng với dự án cần bàn giao.
- Branch hiện tại là release/1.4.
- Không vô tình làm việc trong clone, worktree hoặc repository khác.
- Trạng thái branch cho biết upstream nếu đã được cấu hình.

Xem các branch local và upstream:

~~~bash
git branch -vv
~~~

Một dòng ví dụ có thể trông như sau:

~~~text
* release/1.4  a1b2c3d [origin/release/1.4: ahead 2] Prepare release
~~~

Dòng này cho biết branch local đang ahead hai commit so với remote-tracking branch được ghi nhận lần fetch gần nhất. Nó chưa chứng minh remote hiện tại vẫn ở đúng commit đó; bạn cần fetch trước khi kết luận.

Xem remote:

~~~bash
git remote -v
~~~

Xác nhận origin trỏ tới repository đích mong muốn. Một số URL có thể chứa thông tin xác thực; không sao chép nguyên URL có token hoặc credential vào báo cáo hay kênh trao đổi công khai.

Nếu remote chưa được cấu hình, xác minh URL từ người duy trì dự án rồi mới thêm:

~~~bash
git remote add origin https://git.example.com/team/inventory.git
~~~

Không tự đoán URL hoặc thay remote hiện có khi chưa xác nhận repository đích.

## 3. Kiểm tra toàn bộ thay đổi local

Lệnh trạng thái ngắn:

~~~bash
git status --short --branch
~~~

Để xem mọi file untracked thay vì gom theo thư mục:

~~~bash
git status --short --untracked-files=all
~~~

Đọc riêng thay đổi trong working tree:

~~~bash
git diff
~~~

Đọc riêng nội dung đã stage:

~~~bash
git diff --cached
~~~

Kiểm tra whitespace error:

~~~bash
git diff --check
git diff --cached --check
~~~

Các trạng thái cần hiểu:

| Trạng thái | Ý nghĩa | Câu hỏi trước khi bàn giao |
|---|---|---|
| Staged | Nội dung trong index sẽ được commit tiếp theo | Có file hoặc hunk nào stage nhầm không? |
| Unstaged | File tracked đã sửa nhưng chưa đưa vào index | Đây là thay đổi cần commit hay công việc còn dở? |
| Untracked | File mới chưa được Git theo dõi | Có phải source/tài liệu cần commit, hay là output tạm? |
| Ignored | File chưa tracked được quy tắc ignore loại khỏi trạng thái thông thường | Có dữ liệu local hoặc secret cần giữ an toàn không? |

Để xem cả file ignored:

~~~bash
git status --short --ignored
~~~

Ignored file không được đưa vào commit theo thao tác add thông thường, nhưng có thể vẫn tồn tại trên máy và chứa dữ liệu quan trọng. Không xóa chúng chỉ để làm trạng thái trông sạch.

Xác định file nào đang được Git theo dõi:

~~~bash
git ls-files
~~~

Tìm file đã tracked nhưng hiện khớp quy tắc ignore:

~~~bash
git ls-files -ci --exclude-standard
~~~

Nếu lệnh cuối liệt kê file, hãy kiểm tra vì file đã tracked vẫn được Git quản lý dù sau này pattern ignore khớp với nó.

## 4. Quyết định cách xử lý khi working tree chưa sạch

Không tiếp tục push release khi còn thay đổi chưa được phân loại.

### 4.1. Thay đổi thuộc phạm vi release

Nếu thay đổi đã hoàn chỉnh và cần có trong release:

~~~bash
git add path/to/file
git diff --cached --check
git diff --cached
~~~

Chỉ stage những đường dẫn có chủ đích. Sau khi review nội dung staged, tạo commit với thông điệp mô tả thay đổi:

~~~bash
git commit -m "fix: validate inventory quantity"
~~~

Nếu có nhiều thay đổi độc lập, chia thành các commit riêng. Sau commit, kiểm tra lại status và lịch sử.

### 4.2. Thay đổi chưa hoàn chỉnh cần giữ lại

Nếu cần giữ công việc đang dở nhưng không đưa vào release, có thể stash:

~~~bash
git stash push -u -m "WIP before release handoff"
~~~

Tùy chọn -u bao gồm file untracked nhưng không bao gồm file ignored. Stash không phải nơi lưu trữ dài hạn; hãy ghi nhớ stash nào chứa công việc và khôi phục sau khi bàn giao.

Không dùng stash nếu chính sách dự án yêu cầu mọi công việc phải được commit trên branch riêng hoặc nếu việc stash sẽ làm mất ngữ cảnh cần review.

### 4.3. Thay đổi không cần giữ

Nếu đã xác định một thay đổi tracked là không cần thiết, xem diff rồi khôi phục đúng file từ nguồn phù hợp. Ví dụ bỏ thay đổi unstaged của một file:

~~~bash
git restore --worktree -- path/to/file
~~~

Unstage một file nhưng giữ nội dung trên ổ đĩa:

~~~bash
git restore --staged -- path/to/file
~~~

Không chạy restore trên pathspec rộng như dấu chấm khi chưa đọc toàn bộ diff. Với file untracked, restore không phải công cụ dọn file; hãy xác minh file có thể xóa hay cần giữ.

## 5. Kiểm tra commit hiện tại và lịch sử cần bàn giao

Xem commit gần nhất:

~~~bash
git log -5 --oneline --decorate
git show --stat --oneline HEAD
git show --no-patch --format=fuller HEAD
~~~

Kiểm tra branch đang có bao nhiêu commit local chưa xuất hiện trong remote-tracking branch, sau khi đã cập nhật thông tin remote ở bước tiếp theo.

Trước khi fetch, không nên dựa vào số ahead/behind cũ trong git status. Remote-tracking branch chỉ phản ánh lần fetch gần nhất.

## 6. Fetch để cập nhật trạng thái remote

Lấy thông tin mới từ origin:

~~~bash
git fetch --prune origin
~~~

Fetch cập nhật object và remote-tracking refs, không tự merge hoặc rebase vào branch đang làm việc. Tùy chọn --prune loại remote-tracking ref đã bị xóa ở remote.

Kiểm tra lại branch:

~~~bash
git status -sb
git branch -vv
~~~

Nếu branch chưa có upstream, xem remote branch có tồn tại không:

~~~bash
git ls-remote --heads origin refs/heads/release/1.4
~~~

Nếu branch remote đã tồn tại, có thể đặt upstream:

~~~bash
git branch --set-upstream-to=origin/release/1.4 release/1.4
~~~

Nếu branch remote chưa tồn tại, bạn sẽ thiết lập upstream khi push lần đầu bằng tùy chọn -u.

## 7. Đếm commit ahead và behind

Sau fetch, so sánh branch local với remote-tracking branch:

~~~bash
git rev-list --left-right --count HEAD...origin/release/1.4
~~~

Kết quả có hai số, cách nhau bởi tab:

~~~text
2    1
~~~

Số thứ nhất là số commit chỉ có ở HEAD (local ahead). Số thứ hai là số commit chỉ có ở origin/release/1.4 (local behind).

| Kết quả | Diễn giải | Việc cần làm |
|---|---|---|
| 0 0 | Hai branch cùng tip | Không có commit nào cần push hoặc pull |
| 2 0 | Local ahead hai commit | Review hai commit rồi push |
| 0 1 | Local behind một commit | Tích hợp thay đổi remote theo chính sách nhóm |
| 2 1 | Hai phía đã phân kỳ | Review cả hai phía, tích hợp rồi kiểm tra lại |

Xem commit chỉ có local:

~~~bash
git log --oneline origin/release/1.4..HEAD
~~~

Xem commit chỉ có remote:

~~~bash
git log --oneline HEAD..origin/release/1.4
~~~

Nếu local behind hoặc hai phía phân kỳ, không push ngay. Đọc commit remote-only, trao đổi với nhóm nếu cần và tích hợp theo chính sách merge hoặc rebase của repository. Sau khi tích hợp, chạy lại test và fetch/so sánh trước khi push.

Kiểm tra quan hệ tổ tiên:

~~~bash
git merge-base --is-ancestor origin/release/1.4 HEAD
~~~

Nếu mã thoát là 0, tip remote-tracking là tổ tiên của HEAD; local đã bao gồm lịch sử remote tại thời điểm fetch. Nếu lệnh thất bại, local chưa chứa tip đó hoặc hai lịch sử không liên quan. Không dùng force push để che một trạng thái chưa hiểu rõ.

## 8. Chạy kiểm thử và kiểm tra nội dung release

Chạy bộ kiểm thử được dự án quy định. Ví dụ:

~~~bash
./mvnw test
~~~

Hoặc với Gradle:

~~~bash
./gradlew test
~~~

Hoặc với dự án Node:

~~~bash
npm test
~~~

Chỉ chạy lệnh phù hợp với repository hiện tại. Ghi nhận kết quả, phiên bản runtime và môi trường nếu chúng ảnh hưởng tới khả năng tái lập.

Review phạm vi thay đổi so với branch remote:

~~~bash
git diff --stat origin/release/1.4...HEAD
git diff --name-status origin/release/1.4...HEAD
~~~

Kiểm tra các nội dung dễ bị bỏ sót:

- File cấu hình mẫu có được cập nhật cùng code không?
- Lockfile hoặc dependency manifest có khớp thay đổi không?
- File build, cache, log, credential hoặc dữ liệu local có lọt vào commit không?
- README, changelog và ghi chú phát hành có mô tả đúng phiên bản không?
- Các commit có thông điệp rõ ràng và không chứa nội dung ngoài phạm vi release không?

Có thể tìm file lớn hoặc file bất thường trong danh sách thay đổi bằng cách review từng đường dẫn. Không chỉ dựa vào tổng số file hoặc tổng dung lượng diff.

## 9. Đẩy đúng branch lên remote

Trước khi push, xác nhận:

- Branch hiện tại đúng là release/1.4.
- Working tree và index sạch hoặc đã được phân loại.
- Commit local đã được review.
- Không còn commit remote-only chưa tích hợp.
- Test cần thiết đã đạt.

Có thể xem trước thao tác push:

~~~bash
git push --dry-run origin release/1.4
~~~

Dry-run giúp kiểm tra refspec và khả năng push ở thời điểm chạy, nhưng không thay thế lần push thật và không chứng minh dữ liệu đã được ghi trên remote.

Nếu đây là lần đầu push branch và cần thiết lập upstream:

~~~bash
git push -u origin release/1.4
~~~

Nếu upstream đã có:

~~~bash
git push origin release/1.4
~~~

Lệnh chỉ định branch cụ thể giúp tránh vô tình đẩy các branch khác. Không dùng git push --all hoặc git push --tags trong bước bàn giao nếu chưa review toàn bộ refs sẽ được gửi.

Nếu remote từ chối push vì branch đã thay đổi, fetch lại và kiểm tra ahead/behind. Tích hợp commit mới theo chính sách rồi thử lại. Không tự dùng --force hoặc --force-with-lease để vượt qua từ chối nếu chưa có kế hoạch được nhóm chấp thuận.

## 10. Xác minh branch thực sự đã có trên remote

Sau khi push, fetch lại:

~~~bash
git fetch origin
~~~

So sánh object ID của local và remote-tracking branch:

~~~bash
git rev-parse HEAD
git rev-parse origin/release/1.4
~~~

Hai giá trị cần giống nhau nếu mục tiêu là đẩy chính xác HEAD hiện tại lên branch remote và không có commit mới nào được cập nhật thêm sau đó.

Kiểm tra trực tiếp ref trên máy chủ:

~~~bash
git ls-remote --heads origin refs/heads/release/1.4
~~~

Kết quả chứa object ID và tên ref. Object ID cần trùng với giá trị HEAD đã ghi nhận.

Nếu có người khác push commit mới ngay sau lần push của bạn, remote có thể tiến lên trước HEAD. Khi đó hãy fetch và kiểm tra trạng thái mới; đừng kết luận push thất bại chỉ vì remote đã thay đổi tiếp. Cần phân biệt commit của bạn đã được nhận hay branch đã có commit tiếp theo.

## 11. Kiểm tra tag release trước khi tạo

Tag là ref đặt tên cho một object, thường là commit. Trước khi tạo tag, xác nhận tag dự kiến chưa tồn tại ở local và remote:

~~~bash
git tag --list v1.4.0
git ls-remote --tags origin refs/tags/v1.4.0
~~~

Đọc riêng kết quả local và remote. Nếu cả hai lệnh không cho thấy tag, tên tag đang trống ở cả hai nơi và có thể tạo mới. Nếu tag chỉ tồn tại ở local, kiểm tra nó trước; nếu đã là annotated tag đúng commit và đúng thông điệp, có thể dùng tag đó rồi chuyển tới bước push. Nếu tag tồn tại ở remote nhưng chưa có local, fetch tag về trước khi đọc:

~~~bash
git fetch origin tag v1.4.0
~~~

Sau khi tag đã có trong local, kiểm tra object đích:

~~~bash
git show --no-patch --decorate v1.4.0
git rev-parse 'v1.4.0^{}'
~~~

Đối chiếu với commit release đã được phê duyệt. Nếu tag local là lightweight trong khi chính sách yêu cầu annotated, hoặc metadata/đích tag không đúng, dừng để xử lý theo quy trình nhóm; không ghi đè tag cũ một cách âm thầm. Tag release đã công bố thường nên bất biến.

Kiểm tra commit sẽ được đánh dấu:

~~~bash
git rev-parse HEAD
git show --no-patch --oneline HEAD
~~~

Đảm bảo HEAD chính là commit cần phát hành và branch release đã được push, xác minh ở bước trước.

## 12. Tạo annotated tag

Tạo annotated tag với thông điệp release:

~~~bash
git tag -a v1.4.0 -m "Release v1.4.0"
~~~

Annotated tag tạo một tag object riêng, chứa tên tag, tagger, thời gian, thông điệp và object đích. Nó phù hợp với release vì lưu metadata mô tả mốc phát hành.

Nếu tổ chức yêu cầu tag ký số và bạn đã cấu hình signing key:

~~~bash
git tag -s v1.4.0 -m "Release v1.4.0"
~~~

Chỉ dùng một trong hai lệnh tạo tag cho cùng tên và chỉ khi tên tag chưa tồn tại ở local. Nếu đã xác minh tag local hiện hữu đúng mục tiêu, bỏ qua bước tạo mới và tiếp tục tới bước push. Không tạo tag lần thứ hai hoặc di chuyển tag đã tồn tại.

Xác minh loại object:

~~~bash
git cat-file -t v1.4.0
~~~

Với annotated tag, kết quả cần là tag. Lightweight tag thường trả về commit vì ref trỏ trực tiếp tới commit object.

Xem metadata tag:

~~~bash
git show --no-patch --format=fuller v1.4.0
git cat-file -p v1.4.0
~~~

Xác nhận tag bóc ra đúng commit:

~~~bash
git rev-parse 'v1.4.0^{}'
git rev-parse HEAD
~~~

Hai object ID cần giống nhau nếu tag phải đánh dấu chính xác HEAD hiện tại.

Nếu dùng tag ký số, xác minh chữ ký:

~~~bash
git verify-tag v1.4.0
~~~

Chữ ký hợp lệ chỉ chứng minh tag object khớp với chữ ký và khóa được kiểm tra. Nhóm vẫn cần xác minh khóa thuộc đúng người phát hành qua kênh tin cậy.

## 13. Đẩy tag cụ thể lên remote

Đẩy đúng tag vừa tạo:

~~~bash
git push origin v1.4.0
~~~

Lệnh này gửi tag có tên được chỉ định. Không dùng --tags một cách máy móc vì tùy chọn đó có thể đẩy nhiều tag local khác chưa nằm trong phạm vi release hiện tại.

Nếu remote báo tag đã tồn tại, dừng và kiểm tra object đích trên remote. Không xóa hoặc force-update tag phát hành đã công bố nếu chưa có quyết định rõ ràng của người chịu trách nhiệm release.

## 14. Xác minh tag từ remote

Lấy thông tin tag trực tiếp từ máy chủ:

~~~bash
git ls-remote --tags origin refs/tags/v1.4.0 'refs/tags/v1.4.0^{}'
~~~

Với annotated tag, output thường có hai dòng:

- Dòng refs/tags/v1.4.0 trỏ tới tag object.
- Dòng refs/tags/v1.4.0^{} trỏ tới object đích sau khi bóc tag, thường là commit.

Dòng peeled ref có thể dùng để so sánh với commit release đã ghi nhận. Với lightweight tag, remote thường chỉ hiển thị một dòng trỏ thẳng tới commit.

Có thể fetch tag về local rồi kiểm tra:

~~~bash
git fetch origin tag v1.4.0
git cat-file -t v1.4.0
git rev-parse 'v1.4.0^{}'
~~~

Đối chiếu object ID với HEAD đã bàn giao. Nếu tag trên remote trỏ tới commit khác, chưa thể coi release đã hoàn tất; hãy dừng và điều tra.

## 15. Xác nhận trạng thái sạch sau khi push và tag

Kiểm tra lại:

~~~bash
git status --short --branch
git diff
git diff --cached
git status --short --untracked-files=all
~~~

Nếu không còn thay đổi tracked, staged hoặc untracked ngoài dự kiến, output ngắn sẽ không liệt kê chúng. File ignored có thể vẫn tồn tại; xem riêng:

~~~bash
git status --short --ignored
~~~

Đối với file ignored, xác nhận đó là cache, output build hoặc cấu hình local có chủ đích. Không xóa file chỉ để có output trống. Nếu phát hiện file chứa secret, giữ nó ngoài Git và xử lý credential theo quy trình bảo mật.

Kiểm tra các ref cuối cùng:

~~~bash
git branch -vv
git tag --list v1.4.0
git rev-parse HEAD
git rev-parse origin/release/1.4
git rev-parse 'v1.4.0^{}'
~~~

Trong trường hợp không có commit mới trên remote sau push, ba object ID của HEAD, remote-tracking branch và peeled tag cần giống nhau. Nếu nhóm cho phép branch tiếp tục tiến lên sau release, hãy ghi rõ commit tag và tip branch có thể khác nhau; tag vẫn phải trỏ đúng commit release đã phê duyệt.

## 16. Bảng bằng chứng bàn giao

Trước khi thông báo hoàn tất, ghi lại các thông tin có thể kiểm chứng:

| Mục | Bằng chứng cần ghi |
|---|---|
| Repository | Đường dẫn root hoặc tên dự án |
| Branch | release/1.4 |
| Remote | origin và repository đích đã xác minh |
| Commit | Full hash của commit release |
| Push branch | Ref refs/heads/release/1.4 trên remote |
| Tag | v1.4.0 |
| Tag type | Annotated hoặc signed annotated |
| Tag target | Commit hash sau khi bóc tag |
| Kiểm thử | Lệnh chạy và kết quả đạt/không đạt |
| Working tree | Không còn staged, unstaged hoặc untracked ngoài dự kiến |
| Người bàn giao | Người chịu trách nhiệm và thời điểm theo quy trình nhóm |

Ví dụ ghi nhận:

~~~text
Repository: inventory
Branch: release/1.4
Remote: origin
Commit: <full-commit-id>
Remote branch verified: refs/heads/release/1.4
Tag: v1.4.0 (annotated)
Tag target: <same-full-commit-id>
Tests: PASS
Working tree: clean
Ignored local files: reviewed
~~~

Không đưa token, private key, credential hoặc URL có thông tin xác thực vào báo cáo bàn giao.

## 17. Tình huống lỗi thường gặp

### Push thành công nhưng branch local vẫn báo ahead

Fetch lại và so sánh object ID:

~~~bash
git fetch origin
git rev-parse HEAD
git rev-parse origin/release/1.4
~~~

Có thể upstream chưa được cấu hình, remote-tracking ref chưa cập nhật hoặc push đã đẩy tới một ref khác. Kiểm tra refspec và remote URL trước khi push lại.

### Push bị từ chối vì non-fast-forward

Remote có commit mới mà local chưa tích hợp. Fetch, đọc commit remote-only, rồi merge hoặc rebase theo chính sách nhóm. Chạy test và push lại sau khi xác nhận lịch sử.

### Tag local tồn tại nhưng remote không có

Kiểm tra tên tag, remote URL và lệnh push. Đẩy tag cụ thể bằng git push origin v1.4.0 rồi xác minh bằng git ls-remote.

### Tag remote đã tồn tại nhưng trỏ tới commit khác

Dừng quy trình phát hành. Kiểm tra tag object, commit đích và lịch sử thông báo release. Không tự xóa, di chuyển hoặc force-update tag đã công bố.

### Working tree sạch nhưng có file ignored quan trọng

Git không hiển thị file ignored trong status thông thường. Xem git status --ignored và xác định file đó là output có thể tạo lại hay dữ liệu local cần bảo vệ. Working tree sạch không có nghĩa mọi file trên ổ đĩa đều đã được Git lưu.

### Commit đã push nhưng phát hiện lỗi sau bàn giao

Nếu branch đã chia sẻ, cân nhắc tạo commit sửa lỗi hoặc revert commit lỗi theo quy trình nhóm. Với tag release đã công bố, tuân theo chính sách phát hành để tạo tag phiên bản mới hoặc xử lý ngoại lệ có kiểm soát; không âm thầm di chuyển tag cũ.

## 18. Quy trình bàn giao rút gọn

Có thể dùng chuỗi kiểm tra sau khi đã hiểu trạng thái repository và xác nhận không có thay đổi chưa phân loại:

~~~bash
git status --short --branch
git fetch --prune origin
git rev-list --left-right --count HEAD...origin/release/1.4
git log --oneline origin/release/1.4..HEAD
git diff --check
git diff --cached --check
git push --dry-run origin release/1.4
git push origin release/1.4
git fetch origin
git rev-parse HEAD
git rev-parse origin/release/1.4
git tag -a v1.4.0 -m "Release v1.4.0"
git rev-parse 'v1.4.0^{}'
git push origin v1.4.0
git ls-remote --tags origin refs/tags/v1.4.0 'refs/tags/v1.4.0^{}'
git status --short --branch
~~~

Đây là trình tự minh họa, không phải script để chạy mù quáng. Nếu lệnh đếm ahead/behind cho thấy branch đã phân kỳ, test chưa đạt, tag đã tồn tại hoặc remote từ chối push, hãy dừng và xử lý tình huống đó trước khi tiếp tục các bước sau.

## 19. Checklist hoàn thành

- [ ] Repository root và branch local đã được xác nhận.
- [ ] Remote URL trỏ đúng repository đích.
- [ ] Staged, unstaged, untracked và ignored files đã được phân loại.
- [ ] Không có secret hoặc file sinh ra bị đưa vào commit ngoài ý muốn.
- [ ] Đã fetch remote trước khi so sánh.
- [ ] Ahead/behind và commit local-only/remote-only đã được kiểm tra.
- [ ] Các thay đổi remote đã được tích hợp theo chính sách nhóm.
- [ ] Bộ test cần thiết đã chạy và kết quả được ghi lại.
- [ ] Branch release đã được push lên đúng remote.
- [ ] Remote branch đã được xác minh bằng fetch, object ID hoặc ls-remote.
- [ ] Annotated tag được tạo trên đúng commit release.
- [ ] Tag đã được push và xác minh từ remote.
- [ ] Working tree và index sạch; file ignored đã được xem xét.
- [ ] Bằng chứng bàn giao có branch, commit, tag và kết quả test.

## 20. Ghi nhớ

Một lần bàn giao đáng tin cậy cần bằng chứng ở cả local và remote. Trước tiên phân loại mọi thay đổi trong working tree, index, untracked và ignored; sau đó fetch để so sánh ahead/behind và tích hợp commit remote theo chính sách. Push branch cụ thể, fetch lại và so sánh object ID để xác nhận nội dung đã đến đúng ref. Tạo annotated tag trên commit release đã xác minh, push tag cụ thể và kiểm tra peeled target từ remote. Cuối cùng ghi lại commit, branch, tag, kết quả test và trạng thái sạch để người tiếp nhận có thể xác minh độc lập.
