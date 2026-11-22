# Hợp nhất hai lịch sử độc lập với --allow-unrelated-histories

## Khi nào hai lịch sử được xem là độc lập?

Thông thường, Git chỉ hợp nhất hai nhánh khi chúng có ít nhất một commit tổ tiên chung. Commit chung đó là merge base, làm cơ sở để Git xác định phần thay đổi của mỗi nhánh kể từ lần tách nhánh rồi kết hợp hai phía.

Có những tình huống hai repository được khởi tạo độc lập nhưng sau này cần đưa vào cùng một lịch sử:

- Một dự án được tạo bằng git init và đã có commit riêng, sau đó kết nối với repository mới trên GitHub hoặc GitLab vốn cũng đã có commit README hay LICENSE.
- Hai nhóm phát triển cùng một sản phẩm trong hai repository riêng rồi quyết định hợp nhất lịch sử.
- Một repository cũ cần được nhập vào repository mới mà vẫn giữ các commit gốc.
- Một bản mã nguồn được khởi tạo độc lập ở hai nơi và cần kết nối thành một repository chung.

Ví dụ, repository A có lịch sử:

~~~text
A1---A2---A3  main
~~~

Repository B có lịch sử riêng:

~~~text
B1---B2  main
~~~

Không có commit nào chung giữa hai đồ thị. Khi Git tìm merge base của hai đầu nhánh, nó không tìm thấy tổ tiên chung. Vì vậy, lệnh merge thông thường sẽ từ chối:

~~~bash
git merge imported/main
~~~

Thông báo thường gặp:

~~~text
fatal: refusing to merge unrelated histories
~~~

Tùy chọn `--allow-unrelated-histories` cho phép Git tiếp tục merge dù không có merge base chung:

~~~bash
git merge --allow-unrelated-histories imported/main
~~~

Tùy chọn này không tạo ra một tổ tiên chung giả và không viết lại hai lịch sử thành một chuỗi. Git tạo một merge commit có hai parent, nối hai đồ thị lịch sử độc lập vào cùng một lịch sử có thể truy cập.

## Hiểu merge commit khi không có tổ tiên chung

Khi hai nhánh có chung lịch sử, Git thường dùng commit tổ tiên chung làm merge base để tính toán thay đổi hai phía. Với hai lịch sử độc lập, không có commit như vậy. Khi cho phép merge, Git xử lý tình huống như kết hợp hai cây nội dung không có nền commit chung.

Giả sử nhánh hiện tại là main của repository A, còn imported/main là nhánh lấy từ repository B.

Trước khi merge:

~~~text
A1---A2---A3  main

B1---B2       imported/main
~~~

Sau khi merge thành công:

~~~text
A1---A2---A3------M  main
                  /
B1---------------B2  imported/main
~~~

Sơ đồ chỉ minh họa quan hệ parent. Merge commit M có hai parent: A3 và B2. Thứ tự parent phụ thuộc nhánh hiện tại và nhánh được merge:

- Parent thứ nhất là commit HEAD của nhánh hiện tại trước khi merge.
- Parent thứ hai là commit tip của nhánh được merge.

Có thể kiểm tra bằng:

~~~bash
git show --no-patch --pretty=raw HEAD
git rev-list --parents -n 1 HEAD
~~~

Nếu merge tạo ra commit M như ví dụ, M có hai mã parent riêng biệt. Các commit A1–A3 và B1–B2 vẫn giữ nguyên ID; Git không sửa commit gốc chỉ vì hai lịch sử được kết nối.

Merge commit tạo ra một điểm nối để từ đó các nhánh đều là tổ tiên của lịch sử hợp nhất. Sau này Git có thể tính merge base cho những thao tác tiếp theo dựa trên đồ thị đã được nối.

## Phân biệt lỗi unrelated histories với repository nông

Không phải mọi trường hợp Git không tìm thấy merge base đều có nghĩa hai repository thật sự độc lập.

Một nguyên nhân khác là **shallow clone**: bản clone chỉ tải một phần lịch sử, nên commit tổ tiên chung có thể chưa tồn tại trong object database cục bộ.

Kiểm tra repository có phải shallow clone không:

~~~bash
git rev-parse --is-shallow-repository
~~~

Nếu kết quả là true, hãy lấy thêm lịch sử trước khi kết luận hai nhánh không liên quan. Với remote hỗ trợ, có thể lấy toàn bộ lịch sử:

~~~bash
git fetch --unshallow origin
~~~

Hoặc lấy sâu thêm một số commit:

~~~bash
git fetch --deepen=100 origin
~~~

Thay remote và độ sâu theo repository thực tế. Nếu hai nhánh thuộc hai remote khác nhau, cần lấy đủ lịch sử từ remote chứa nhánh tương ứng.

Sau đó kiểm tra lại:

~~~bash
git merge-base main imported/main
~~~

Nếu Git trả về một commit ID, hai nhánh có tổ tiên chung và có thể merge theo quy trình thông thường. Nếu không tìm thấy merge base sau khi đã xác nhận lịch sử đầy đủ, hai lịch sử có thể thật sự độc lập.

Không nên dùng `--allow-unrelated-histories` chỉ để che một vấn đề fetch thiếu lịch sử. Hãy xác minh nguyên nhân trước.

## Kiểm tra trước khi hợp nhất

Hợp nhất hai lịch sử độc lập có thể đưa vào repository hiện tại nhiều file, cấu hình và quy tắc từ một nguồn khác. Trước khi merge, cần xác nhận đúng repository, đúng nhánh và trạng thái working tree.

### Xác nhận repository và nhánh hiện tại

~~~bash
git rev-parse --show-toplevel
git branch --show-current
git status
git rev-parse HEAD
git log --oneline --decorate -n 10
~~~

Hãy ghi lại commit hiện tại của nhánh đích. Nếu có thay đổi chưa commit, hãy commit hoặc lưu chúng theo quy trình phù hợp trước khi merge. Merge khi working tree có thay đổi có thể bị Git từ chối hoặc làm việc đối chiếu trở nên khó khăn.

Đặc biệt, không bắt đầu một lần nhập lịch sử khi index còn unmerged từ một thao tác trước đó.

### Kiểm tra remote và nhánh nguồn

Xem các remote đã cấu hình:

~~~bash
git remote -v
~~~

Xem các nhánh local và remote-tracking:

~~~bash
git branch -avv
~~~

Nếu repository nguồn chưa được đăng ký làm remote, thêm nó bằng một tên dễ hiểu:

~~~bash
git remote add imported https://example.com/team/legacy-app.git
~~~

Tên imported chỉ là ví dụ. Nếu tên đã tồn tại, chọn tên remote khác hoặc kiểm tra remote hiện tại thay vì ghi đè cấu hình chưa rõ nguồn gốc.

Lấy ref và object từ remote:

~~~bash
git fetch imported
~~~

Kiểm tra nhánh nguồn vừa fetch:

~~~bash
git log --oneline --decorate imported/main
git show --stat --oneline imported/main
~~~

Xác nhận URL, tổ chức sở hữu repository và commit nguồn trước khi đưa lịch sử vào repository đích. Không merge một repository không đáng tin cậy chỉ vì nó có tên hoặc nội dung giống dự án.

### Xác nhận không có merge base chung

Chạy:

~~~bash
git merge-base main imported/main
~~~

Nếu có merge base, Git in ra mã commit chung. Nếu không có, lệnh trả mã thoát khác 0.

Có thể kiểm tra rõ hơn bằng:

~~~bash
git merge-base --is-ancestor main imported/main
git merge-base --is-ancestor imported/main main
~~~

Hai lệnh này kiểm tra quan hệ tổ tiên theo từng hướng. Nếu cả hai đều không đúng, điều đó vẫn chưa đủ để kết luận unrelated histories nếu clone còn nông hoặc thiếu object.

Xem các commit gốc của hai lịch sử:

~~~bash
git rev-list --max-parents=0 main
git rev-list --max-parents=0 imported/main
~~~

Nếu hai nhánh thực sự độc lập, chúng thường có các root commit khác nhau. Một repository có thể có nhiều root commit nếu lịch sử từng được ghép từ nhiều nguồn hoặc có các ref không liên quan khác; vì vậy hãy giới hạn truy vấn vào đúng hai nhánh cần hợp nhất.

### Kiểm tra các đường dẫn trùng nhau

Xem danh sách file của hai đầu nhánh:

~~~bash
git ls-tree -r --name-only main
git ls-tree -r --name-only imported/main
~~~

Nếu cả hai lịch sử đều có README.md, LICENSE, .gitignore hoặc cùng một thư mục source, Git có thể báo conflict khi merge. Điều đó không có nghĩa merge thất bại hoàn toàn; bạn cần quyết định nội dung cuối cùng của từng đường dẫn.

Kiểm tra thêm những file có ảnh hưởng tới quá trình build hoặc thực thi:

- File build như pom.xml, build.gradle, package.json hoặc lockfile.
- File cấu hình triển khai và CI.
- Workflow tự động trong .github/workflows hoặc thư mục tương đương.
- Script cài đặt, build và release.
- File chứa credential hoặc cấu hình môi trường.
- License, NOTICE và tài liệu nguồn.

Hai repository độc lập có thể dùng cùng tên file nhưng nội dung và mục đích khác nhau. Không tự động chọn toàn bộ nội dung từ một phía mà chưa review.

## Tạo điểm phục hồi trước khi merge

Trước khi thực hiện merge, lưu lại commit hiện tại bằng một nhánh backup. Ví dụ:

~~~bash
git branch backup/main-before-unrelated-merge main
~~~

Nhánh backup giữ một ref tới commit trước khi hợp nhất. Nếu thao tác sau đó có vấn đề, bạn vẫn có thể tham chiếu lại trạng thái ban đầu.

Tạo nhánh tích hợp riêng:

~~~bash
git switch -c integrate/legacy-history main
~~~

Làm việc trên nhánh này giúp review kết quả trước khi đưa vào main. Nếu nhóm đã có quy ước đặt tên nhánh tích hợp, hãy sử dụng tên theo quy ước đó.

Xác nhận lại trạng thái:

~~~bash
git status
git rev-parse HEAD
git branch --show-current
~~~

Điểm bắt đầu của nhánh tích hợp phải đúng commit main đã ghi nhận trước đó.

## Thực hiện merge với --allow-unrelated-histories

Khi đã xác nhận hai lịch sử thực sự không có tổ tiên chung và trạng thái local sẵn sàng, chạy:

~~~bash
git merge --no-commit --no-ff --allow-unrelated-histories imported/main
~~~

Ý nghĩa các tùy chọn:

- `--allow-unrelated-histories`: cho phép merge hai lịch sử không có merge base chung.
- `--no-commit`: dừng trước khi tạo merge commit để bạn review kết quả và giải quyết các vấn đề còn lại.
- `--no-ff`: yêu cầu tạo merge commit thay vì fast-forward nếu tình huống cho phép fast-forward.

Với hai lịch sử độc lập, không có quan hệ fast-forward thông thường. `--no-ff` được ghi rõ ở đây để thể hiện ý định giữ một merge commit làm điểm nối lịch sử.

Nếu muốn Git tự tạo merge commit ngay khi không có conflict, có thể bỏ `--no-commit`. Tuy nhiên, với lần nhập repository độc lập, dừng lại để review thường giúp phát hiện file trùng, cấu hình lạ và thay đổi không mong muốn.

### Kiểm tra trạng thái sau khi chạy merge

~~~bash
git status
git diff --name-only --diff-filter=U
git ls-files -u
~~~

Nếu không có conflict, index đã chứa kết quả merge và Git đang chờ bạn hoàn tất commit do đã dùng `--no-commit`.

Nếu có conflict, git status sẽ liệt kê các đường dẫn cần giải quyết. Với hai lịch sử độc lập, những đường dẫn cùng được thêm ở cả hai phía thường là nhóm cần chú ý đầu tiên.

## Giải quyết conflict khi hai repository có file trùng tên

Ví dụ cả hai repository đều có README.md:

- Repository hiện tại có hướng dẫn build và cấu trúc dự án A.
- Repository được nhập có hướng dẫn chạy và cấu trúc dự án B.

Git không thể tự quyết định nội dung nào nên được giữ. Hãy mở file conflict, xem cả hai phiên bản và chỉnh thành nội dung thống nhất theo mục tiêu repository mới.

Kiểm tra trạng thái conflict:

~~~bash
git status
git diff -- README.md
git ls-files -u -- README.md
~~~

Sau khi sửa nội dung:

~~~bash
git add README.md
~~~

Lặp lại với từng đường dẫn. Không dùng lệnh chọn toàn bộ --ours hoặc --theirs cho cả repository nếu chưa hiểu hậu quả; thao tác đó có thể loại bỏ tài liệu hoặc cấu hình cần giữ từ một phía.

Xác nhận không còn đường dẫn unmerged:

~~~bash
git diff --name-only --diff-filter=U
git status
~~~

Nếu danh sách unmerged rỗng, kiểm tra nội dung đã stage:

~~~bash
git diff --cached --stat
git diff --cached
~~~

`git diff --cached` lúc này giúp review snapshot dự kiến của merge commit, bao gồm cả những file được nhập từ lịch sử nguồn.

### Phân biệt giữ cả hai file với hợp nhất nội dung

Nếu hai file cùng tên nhưng có mục đích khác nhau, có thể đổi tên một file để giữ cả hai phiên bản, ví dụ:

~~~text
README.md
docs/legacy-project-README.md
~~~

Sau đó cập nhật các liên kết và tài liệu tham chiếu. Đối với cấu hình như build file, không nên giữ cả hai chỉ bằng cách đổi tên nếu công cụ build chỉ đọc một file chuẩn; cần quyết định cách hợp nhất dependency, plugin và task.

Với file LICENSE hoặc NOTICE, cần kiểm tra nghĩa vụ giấy phép của cả hai nguồn trước khi chọn nội dung cuối. Việc merge kỹ thuật không thay thế việc đánh giá quyền sử dụng mã nguồn.

## Hoàn tất merge commit

Khi mọi conflict đã được giải quyết và diff staged đã được review, tạo merge commit:

~~~bash
git commit
~~~

Git thường mở editor với thông điệp merge mặc định. Hãy giữ thông điệp thể hiện rõ nguồn lịch sử được nhập, ví dụ:

~~~text
Merge legacy-app history into inventory-app
~~~

Kiểm tra commit vừa tạo:

~~~bash
git show --no-patch --pretty=raw HEAD
git rev-list --parents -n 1 HEAD
~~~

Merge commit phải có hai parent: commit của nhánh hiện tại trước merge và commit của nhánh imported/main.

Xem đồ thị lịch sử:

~~~bash
git log --oneline --graph --decorate --all
~~~

Xác nhận cả hai đầu lịch sử đều là tổ tiên của merge commit:

~~~bash
git merge-base --is-ancestor main HEAD
git merge-base --is-ancestor imported/main HEAD
~~~

Nếu hai lệnh trả mã thoát 0, các commit đầu nhánh tương ứng đều nằm trong lịch sử tổ tiên của HEAD. Đây là một cách kiểm tra rằng merge commit đã kết nối cả hai lịch sử.

## Nếu merge không thành công hoặc cần hủy

Nếu merge đang dang dở và bạn muốn quay lại trạng thái trước khi bắt đầu, có thể dùng:

~~~bash
git merge --abort
~~~

Lệnh này hủy merge đang diễn ra. Nó không thay thế việc bảo vệ các thay đổi cục bộ đã tồn tại trước merge; đó là lý do cần bắt đầu từ working tree sạch và có ref backup.

Sau khi abort, kiểm tra:

~~~bash
git status
git rev-parse HEAD
git log -1 --oneline --decorate
~~~

HEAD cần trở về commit trước merge và không còn trạng thái merge đang diễn ra.

Nếu merge đã hoàn tất và merge commit đã được tạo, `git merge --abort` không còn phù hợp. Khi commit đã được tạo nhưng chưa chia sẻ, có thể chuyển về nhánh backup hoặc tạo nhánh mới từ commit backup sau khi đánh giá trạng thái. Nếu đã push merge commit lên remote hoặc người khác đã dựa vào nó, hãy phối hợp với nhóm và ưu tiên một commit revert có chủ đích thay vì viết lại lịch sử đã chia sẻ.

Không chạy `git reset --hard` như phản xạ để sửa một merge lỗi. Hãy xác định merge đã commit hay chưa, commit nào cần giữ và những thay đổi cục bộ nào có thể bị mất.

## Kiểm tra kết quả sau khi hợp nhất

Merge thành công về mặt Git chỉ chứng minh hai snapshot đã được kết hợp thành commit. Bạn vẫn cần xác minh nội dung và khả năng build của repository mới.

### Kiểm tra lịch sử

~~~bash
git log --graph --oneline --decorate --all
git show --no-patch --pretty=raw HEAD
git rev-list --parents -n 1 HEAD
~~~

Xác nhận:

- Merge commit có hai parent như mong đợi.
- Các commit nguồn vẫn xuất hiện trong lịch sử.
- Nhánh backup vẫn trỏ tới commit trước merge.
- Nhánh tích hợp đang ở commit mới.
- Không có ref nào bị di chuyển ngoài ý định.

### Kiểm tra nội dung và cấu hình

~~~bash
git status
git diff HEAD^1 HEAD --stat
git diff HEAD^2 HEAD --stat
~~~

Hai lệnh diff so sánh snapshot merge commit với từng parent, giúp xem phần nội dung khác nhau giữa kết quả hợp nhất và mỗi phía.

Review các vùng dễ xung đột:

- README và tài liệu hướng dẫn.
- File cấu hình build và dependency.
- CI workflow và script tự động.
- .gitignore và .gitattributes.
- License và NOTICE.
- Submodule/gitlink nếu có.
- File cấu hình triển khai và môi trường.

Nếu hai repository có submodule, sau khi merge cần kiểm tra .gitmodules và gitlink, rồi khởi tạo theo hướng dẫn dự án:

~~~bash
git submodule sync --recursive
git submodule update --init --recursive
git submodule status --recursive
~~~

Đừng giả định submodule từ cả hai phía tự động được cấu hình đúng chỉ vì superproject merge không conflict.

### Chạy kiểm tra dự án

Chạy các lệnh phù hợp với repository sau khi nhập:

- Build module hoặc toàn bộ dự án.
- Unit test và integration test.
- Lint và format check.
- Kiểm tra dependency và lockfile.
- Kiểm tra script CI.
- Kiểm tra cấu hình triển khai.
- Kiểm tra các luồng chính từ cả hai nguồn.

Không giả định một lệnh build duy nhất phù hợp cho hai dự án vừa hợp nhất. Có thể cần thống nhất cấu trúc thư mục, công cụ build hoặc cách khởi chạy trước khi chạy test toàn diện.

## Chia sẻ kết quả hợp nhất lên remote

Khi merge commit đã được review và kiểm thử, push nhánh tích hợp lên remote:

~~~bash
git push -u origin integrate/legacy-history
~~~

Nếu main được bảo vệ, tạo Pull Request hoặc Merge Request từ nhánh tích hợp vào main. Máy chủ vẫn áp dụng quyền truy cập, review và status check như các thay đổi khác.

Không push trực tiếp vào nhánh được bảo vệ chỉ vì merge commit đã được tạo cục bộ. Việc tạo commit local không cấp quyền cập nhật remote.

Sau khi được phê duyệt và merge vào main, xác nhận trạng thái remote:

~~~bash
git fetch origin
git log --graph --oneline --decorate origin/main -n 30
~~~

Giữ remote imported nếu nhóm còn cần đối chiếu hoặc cập nhật nguồn cũ. Nếu không còn cần, có thể xóa cấu hình remote local sau khi đã lưu thông tin nguồn gốc ở nơi phù hợp:

~~~bash
git remote remove imported
~~~

Lệnh này xóa cấu hình remote cùng các remote-tracking ref thuộc remote đó trong clone hiện tại; nó không xóa repository nguồn. Các commit đã được merge vẫn được giữ vì còn reachable từ merge commit. Nếu có nhánh hoặc tag nguồn chưa được tích hợp và chỉ còn được tham chiếu bởi ref của remote imported, hãy lưu hoặc chuyển các ref cần thiết trước khi remove remote.

## Những gì không tự động được nhập khi merge lịch sử

`--allow-unrelated-histories` kết hợp hai lịch sử commit và snapshot của chúng. Nó không tự di chuyển mọi dữ liệu hoặc thiết lập từ nền tảng lưu trữ.

Những thứ thường cần xử lý riêng:

- Issues, Pull Requests/Merge Requests và thảo luận review.
- Quyền thành viên, team, token và deploy key.
- Branch protection, ruleset và CI secrets.
- Webhook, runner và cấu hình triển khai.
- Wiki hoặc tài liệu lưu ngoài repository.
- Release metadata và artifact.
- Tag hoặc branch không nằm trong lịch sử của hai đầu nhánh được merge.

Nếu cần di chuyển tag, hãy liệt kê và review riêng trước khi push:

~~~bash
git tag --list
git show-ref --tags
~~~

Không push toàn bộ tag từ nguồn khác mà chưa kiểm tra tên trùng, commit đích và ý nghĩa phiên bản. Hai repository độc lập có thể đã dùng cùng tên tag cho hai commit khác nhau.

Tương tự, cần chuyển branch riêng theo kế hoạch. Merge hai đầu nhánh không tự tạo mọi branch remote của repository nguồn trong repository đích.

## Khi nào nên dùng cách khác thay vì --allow-unrelated-histories?

Không phải mọi yêu cầu nhập repository đều cần ghép hai lịch sử độc lập bằng merge commit.

| Mục tiêu | Cách thường phù hợp |
|---|---|
| Kết nối hai lịch sử và giữ nguyên cả hai đồ thị commit | `git merge --allow-unrelated-histories` |
| Chỉ lấy một số commit từ repository nguồn | `git cherry-pick` |
| Nhập một thư mục dự án và giữ lịch sử theo đường dẫn | Công cụ lọc lịch sử như git filter-repo, sau đó merge |
| Đưa một dự án vào thư mục con nhưng tiếp tục đồng bộ nguồn riêng | Git subtree hoặc submodule, tùy mô hình |
| Chỉ lấy snapshot hiện tại, không cần lịch sử nguồn | Copy nội dung có kiểm soát rồi commit trong repository đích |
| Di chuyển repository cùng nhánh và lịch sử nguyên vẹn | Clone/mirror hoặc quy trình migration của nền tảng |

Nếu chỉ cần nhập một thư mục của repository cũ vào monorepo, merge nguyên hai root có thể làm cây thư mục bị trộn và lịch sử khó đọc. Khi đó, lọc lịch sử để đặt toàn bộ đường dẫn dưới một thư mục con trước khi merge có thể phù hợp hơn.

Nếu muốn hai dự án tiếp tục phát triển độc lập, submodule hoặc subtree có thể diễn đạt mối quan hệ rõ hơn việc nhập toàn bộ lịch sử vào một nhánh.

## Những lỗi thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| refusing to merge unrelated histories | Không tìm thấy merge base chung | Xác minh lịch sử đầy đủ, sau đó dùng `--allow-unrelated-histories` nếu thật sự cần |
| Merge base không tìm thấy trong shallow clone | Clone thiếu các commit tổ tiên | Dùng fetch --unshallow hoặc --deepen rồi kiểm tra lại |
| Nhiều conflict ở README và file cấu hình | Hai root commit cùng thêm đường dẫn | Review và hợp nhất từng file, không chọn hàng loạt một phía |
| Submodule không checkout được sau merge | .gitmodules, URL hoặc gitlink không thống nhất | Kiểm tra, sync và update submodule |
| Merge commit chỉ có một parent | Không phải merge commit hai lịch sử như mong đợi hoặc đã dùng cách khác | Xem `git rev-list --parents -n 1 HEAD` |
| Push nhánh tích hợp bị từ chối | Thiếu quyền, nhánh bảo vệ hoặc remote có lịch sử mới | Kiểm tra chính sách và mở Pull Request/Merge Request |
| Tag cùng tên trỏ tới commit khác | Hai repository có namespace tag độc lập | Review và quyết định cách đổi tên hoặc giữ tag |
| Build thất bại sau merge | Cấu hình hoặc dependency của hai dự án xung đột | Thống nhất build, lockfile và cấu hình rồi chạy lại test |

## Quy trình mẫu từ đầu đến cuối

Giả sử repository hiện tại là inventory-app và cần nhập lịch sử từ legacy-app.

~~~bash
# 1. Xác nhận trạng thái repository hiện tại
git status
git rev-parse HEAD
git branch --show-current

# 2. Lưu điểm phục hồi
git branch backup/main-before-import main

# 3. Thêm và fetch repository nguồn
git remote add imported https://example.com/team/legacy-app.git
git fetch imported

# 4. Kiểm tra lịch sử và xác nhận không có merge base
git merge-base main imported/main
git rev-list --max-parents=0 main
git rev-list --max-parents=0 imported/main

# 5. Tạo nhánh tích hợp riêng
git switch -c integrate/legacy-history main

# 6. Merge hai lịch sử, dừng lại để review
git merge --no-commit --no-ff --allow-unrelated-histories imported/main

# 7. Xem conflict và kết quả staged
git status
git diff --name-only --diff-filter=U
git diff --cached --stat

# 8. Sửa từng conflict, rồi stage kết quả
git add <resolved-path>

# 9. Xác nhận không còn conflict và review
git diff --name-only --diff-filter=U
git diff --cached

# 10. Tạo merge commit
git commit

# 11. Xác nhận merge có hai parent và giữ cả hai lịch sử
git rev-list --parents -n 1 HEAD
git log --graph --oneline --decorate --all

# 12. Kiểm tra build/test rồi push nhánh tích hợp
git push -u origin integrate/legacy-history
~~~

Các placeholder như URL, tên nhánh và đường dẫn cần thay theo repository thực tế. Nếu `git merge-base` tìm thấy tổ tiên chung, hãy dùng quy trình merge thông thường thay vì bật tùy chọn unrelated histories.

## Checklist trước và sau khi dùng --allow-unrelated-histories

- [ ] Đã xác nhận đúng repository đích và nguồn.
- [ ] Working tree và index sạch trước khi bắt đầu.
- [ ] Đã ghi lại commit hiện tại và tạo ref backup.
- [ ] Đã fetch đầy đủ lịch sử từ remote nguồn.
- [ ] Đã kiểm tra shallow clone và loại trừ trường hợp thiếu lịch sử.
- [ ] Đã xác nhận hai nhánh thực sự không có merge base chung.
- [ ] Đã kiểm tra root commit và các đường dẫn trùng nhau.
- [ ] Đã review file build, cấu hình, workflow, script và license.
- [ ] Đã merge trên nhánh tích hợp riêng.
- [ ] Đã giải quyết từng conflict và kiểm tra staged diff.
- [ ] Merge commit có hai parent đúng như dự kiến.
- [ ] Cả hai lịch sử nguồn đều là tổ tiên của merge commit.
- [ ] Đã kiểm tra submodule, tag và các ref cần di chuyển riêng.
- [ ] Đã chạy build/test phù hợp.
- [ ] Đã push qua quy trình review và bảo vệ nhánh của nhóm.

## Ghi nhớ

`--allow-unrelated-histories` cho phép Git nối hai lịch sử không có commit tổ tiên chung bằng một merge commit có hai parent. Trước khi dùng, hãy chắc chắn bạn đang xử lý hai repository độc lập thật sự, không phải shallow clone thiếu lịch sử. Tạo ref backup, fetch và kiểm tra nguồn, merge trên nhánh riêng, review các file trùng và xử lý conflict từng bước. Sau khi hoàn tất, xác minh hai parent, giữ nguyên các commit nguồn, chạy build/test và chia sẻ qua quy trình review của nhóm. Tùy chọn này giúp bảo toàn cả hai đồ thị commit; nó không tự di chuyển issue, quyền truy cập, CI secrets, tag hoặc thiết lập nền tảng.

