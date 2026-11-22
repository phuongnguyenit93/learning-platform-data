# Nhận diện kho mã lồng nhau ngoài ý muốn và ranh giới submodule

Một thư mục dự án có thể chứa nhiều thư mục con, nhưng không phải thư mục con nào cũng thuộc cùng một Git repository. Nếu bạn chạy <code>git init</code> hoặc clone một repository vào bên trong repository đang làm việc, Git sẽ nhận diện một kho mã lồng nhau. Từ thời điểm đó, các lệnh chạy bên trong thư mục con có thể thao tác trên repository khác với repository cha.

Kho mã lồng nhau đôi khi là chủ ý, chẳng hạn một submodule hoặc một linked worktree. Nhưng nếu xuất hiện ngoài ý muốn, nó có thể khiến Git bỏ qua nội dung thư mục con, stage một gitlink thay vì các file, hoặc làm đồng đội clone về một đường dẫn trống.

Bài này hướng dẫn cách xác định repository root, phân biệt repository độc lập, submodule và worktree, hiểu ranh giới mà Git tạo ra, rồi chọn cách xử lý an toàn.

## 1. Repository lồng nhau là gì?

Một repository lồng nhau (nested repository) xuất hiện khi bên trong working tree của repository cha có một thư mục chứa metadata Git riêng.

Ví dụ:

~~~text
workspace/
├── .git/
├── README.md
├── src/
└── tools/
    └── converter/
        ├── .git/
        ├── README.md
        └── src/
~~~

Ở đây:

- <code>workspace</code> là repository cha.
- <code>tools/converter</code> là repository con.
- Mỗi repository có lịch sử, refs, index và cấu hình riêng.
- Git chạy bên trong <code>tools/converter</code> thường chọn repository con gần nhất.
- Git chạy từ root <code>workspace</code> coi thư mục con là một ranh giới repository.

Repository lồng nhau có thể được tạo do:

- Chạy <code>git init</code> nhầm trong thư mục con.
- Clone một dự án khác vào thư mục thuộc repository hiện tại.
- Giải nén source code đã chứa thư mục <code>.git</code>.
- Thêm một dự án độc lập vào monorepo mà không xác định cách quản lý.
- Tạo worktree hoặc submodule nhưng không nhận ra chúng dùng metadata riêng.

Không phải mọi thư mục con có tên <code>.git</code> đều là repository độc lập hoàn toàn. Trong submodule và linked worktree, <code>.git</code> thường là một file trỏ tới metadata được lưu ở nơi khác. Cần kiểm tra trước khi di chuyển hoặc xóa.

## 2. Vì sao Git tạo ranh giới giữa các repository?

Khi Git tìm repository từ thư mục hiện tại, nó dò metadata Git ở thư mục đó và các thư mục cha. Khi gặp repository gần nhất, Git sử dụng repository đó cho các lệnh tiếp theo.

Giả sử cấu trúc:

~~~text
project/
├── .git/
└── vendor/
    └── library/
        └── .git/
~~~

Nếu terminal đang ở <code>project/vendor/library</code>, Git tìm thấy repository con trước và dùng nó. Nếu terminal ở <code>project</code>, Git dùng repository cha.

Điều này giải thích vì sao hai lệnh có thể trả về hai root khác nhau:

~~~bash
git -C . rev-parse --show-toplevel
git -C vendor/library rev-parse --show-toplevel
~~~

Lệnh đầu trả về root của repository cha. Lệnh thứ hai trả về root của repository con nếu thư mục đó thực sự là một repository riêng.

Git không tự hợp nhất hai lịch sử. Repository cha không tự động theo dõi mọi file bên trong repository con như file thông thường.

## 3. Tìm root của repository hiện tại

Lệnh cơ bản nhất:

~~~bash
git rev-parse --show-toplevel
~~~

Lệnh in đường dẫn tuyệt đối tới working tree root của repository mà Git đang sử dụng. Chạy từ một thư mục sâu bên trong dự án vẫn cho biết root tương ứng.

Một số lệnh hữu ích khác:

~~~bash
git rev-parse --show-prefix
git rev-parse --show-cdup
git rev-parse --git-dir
git rev-parse --git-common-dir
~~~

| Lệnh | Ý nghĩa |
|---|---|
| <code>--show-toplevel</code> | Đường dẫn root của working tree |
| <code>--show-prefix</code> | Đường dẫn tương đối từ root tới thư mục hiện tại |
| <code>--show-cdup</code> | Đường dẫn tương đối cần đi lên để tới root |
| <code>--git-dir</code> | Đường dẫn metadata Git đang dùng |
| <code>--git-common-dir</code> | Đường dẫn metadata chung, hữu ích với worktree và một số cấu trúc repository liên kết |

Nếu <code>--show-prefix</code> trả về chuỗi rỗng, terminal đang ở root của repository đó. Nếu <code>--show-cdup</code> trả về <code>../../</code>, bạn đang ở sâu hai cấp so với root.

Lưu ý: các lệnh này mô tả repository mà Git đã chọn từ vị trí hiện tại. Chúng không tự cho biết repository đó là repository cha, submodule hay worktree. Cần kết hợp thêm các phép kiểm tra ở phần sau.

## 4. So sánh root của thư mục cha và thư mục con

Khi nghi ngờ có repository lồng nhau, hãy hỏi Git về từng đường dẫn cụ thể:

~~~bash
git -C . rev-parse --show-toplevel
git -C tools/converter rev-parse --show-toplevel
git -C tools/converter rev-parse --git-dir
git -C tools/converter rev-parse --git-common-dir
~~~

Nếu hai lệnh <code>--show-toplevel</code> trả về hai đường dẫn khác nhau, thư mục con đang thuộc một working tree khác.

Có thể kiểm tra thêm trạng thái:

~~~bash
git status --short
git -C tools/converter status --short
git -C tools/converter remote -v
~~~

Repository cha và con có thể có branch, remote và thay đổi chưa commit hoàn toàn khác nhau. Đừng chạy lệnh sửa lịch sử hoặc xóa metadata cho tới khi biết rõ terminal đang thao tác trên repository nào.

## 5. Phát hiện thư mục .git bên trong working tree

Một repository thông thường thường có thư mục <code>.git</code> ở root. Bên trong working tree có thể có thêm thư mục hoặc file tên <code>.git</code> của submodule, worktree hoặc repository độc lập.

Trên Linux/macOS/Git Bash, có thể liệt kê các mục tên .git bên dưới thư mục hiện tại:

~~~bash
find . -path './.git' -prune -o -mindepth 2 -name .git -print -prune
~~~

Lệnh bỏ qua <code>./.git</code> ở root và dừng đi sâu khi đã gặp một mục tên <code>.git</code>. Nếu dự án rất lớn hoặc có thư mục generated, hãy giới hạn phạm vi tìm kiếm để tránh duyệt quá nhiều dữ liệu.

Có thể kiểm tra một đường dẫn cụ thể:

~~~bash
ls -ld tools/converter/.git
file tools/converter/.git
~~~

Kết quả cho biết <code>.git</code> là directory hay file trên các hệ thống Unix-like. Trên Windows, dùng PowerShell:

~~~powershell
Get-Item -Force .\tools\converter\.git | Format-List FullName,Attributes,LinkType,Target
~~~

Nếu <code>.git</code> là file, hãy đọc nội dung file để xem nó trỏ tới Git directory nào. Đừng xóa file này trước khi xác định nó thuộc submodule, worktree hay cấu hình separate git dir.

## 6. Phân biệt repository độc lập, submodule và linked worktree

Ba cấu trúc này đều có thể xuất hiện như một thư mục con có metadata Git, nhưng ý nghĩa khác nhau.

| Loại | Metadata thường thấy | Quan hệ với repository cha |
|---|---|---|
| Repository độc lập lồng nhau | Thường có thư mục <code>.git</code> riêng | Không có liên kết quản lý chính thức với cha |
| Submodule | Thường có file <code>.git</code> trỏ vào metadata submodule trong repository cha | Repository cha ghi một gitlink và cấu hình trong <code>.gitmodules</code> |
| Linked worktree | Có file <code>.git</code> trỏ tới metadata riêng của worktree | Chia sẻ object database và metadata chung với repository gốc |

Một thư mục <code>.git</code> là directory không chứng minh nó là repository độc lập ngoài mọi trường hợp. Một file <code>.git</code> cũng không đủ để kết luận đó là submodule. Hãy dùng lệnh Git để xác định quan hệ.

### Kiểm tra submodule

Chạy bên trong thư mục nghi ngờ:

~~~bash
git rev-parse --show-superproject-working-tree
~~~

Nếu lệnh in ra đường dẫn repository cha, thư mục hiện tại đang nằm trong một submodule của superproject đó. Nếu kết quả rỗng, nó không được Git nhận diện là submodule của một superproject tại thời điểm kiểm tra.

Từ repository cha, xem danh sách:

~~~bash
git submodule status --recursive
~~~

### Kiểm tra worktree

Từ repository gốc hoặc một linked worktree thuộc cùng repository:

~~~bash
git worktree list --porcelain
~~~

Danh sách cho biết các working tree đang liên kết với repository chung. Đối chiếu đường dẫn để biết thư mục con có phải một worktree đã được tạo bằng <code>git worktree add</code> hay không.

### Kiểm tra repository độc lập

Nếu không phải submodule hoặc worktree, xem root và remote:

~~~bash
git -C tools/converter rev-parse --show-toplevel
git -C tools/converter remote -v
git -C tools/converter branch --show-current
~~~

Một repository độc lập thường có remote, branch và lịch sử riêng. Tuy nhiên, remote có thể chưa được cấu hình nên không dùng riêng kết quả <code>remote -v</code> để kết luận.

## 7. Git nhìn repository lồng nhau trong status như thế nào?

Giả sử <code>tools/converter</code> là repository con mới được clone vào repository cha nhưng chưa được thêm vào index. Repository cha có thể hiển thị:

~~~bash
git status --short
~~~

Kết quả minh họa:

~~~text
?? tools/converter/
~~~

Git thường không liệt kê mọi file bên trong repository con như file chưa theo dõi riêng lẻ. Thư mục con là một ranh giới repository.

Nếu chạy:

~~~bash
git add tools/converter
~~~

Git có thể cảnh báo rằng bạn đang thêm một embedded Git repository. Thay vì thêm toàn bộ source code, Git thường stage một gitlink trỏ tới commit hiện tại của repository con.

Đây là hành vi dễ gây nhầm lẫn: lệnh <code>git add</code> thành công không có nghĩa mọi file con đã được đưa vào repository cha.

## 8. Gitlink mode 160000 là gì?

Git biểu diễn một submodule trong tree của repository cha bằng một mục đặc biệt gọi là **gitlink**, có mode <code>160000</code>.

Ví dụ index:

~~~bash
git ls-files --stage -- tools/converter
~~~

Kết quả minh họa:

~~~text
160000 7c4a... 0 tools/converter
~~~

Hoặc sau khi commit:

~~~bash
git ls-tree HEAD -- tools/converter
~~~

Kết quả:

~~~text
160000 commit 7c4a...    tools/converter
~~~

Mode <code>160000</code> có nghĩa repository cha lưu OID của commit mà repository con đang trỏ tới. Nó không lưu toàn bộ file bên trong repository con như các blob thông thường.

OID này phải tương ứng với một commit trong repository con. Repository cha không tự chứa lịch sử và object database đầy đủ của submodule. Khi clone superproject, Git cần biết URL để tải repository con.

## 9. Embedded repository chưa chắc là submodule được cấu hình đầy đủ

Nếu chỉ chạy <code>git add</code> trên một repository con, Git có thể tạo gitlink nhưng chưa có cấu hình submodule chuẩn.

Một submodule chính thức thường có hai thành phần:

1. Gitlink mode <code>160000</code> trong tree/index của superproject.
2. File <code>.gitmodules</code> ghi path và URL để Git biết cách khởi tạo submodule.

Ví dụ .gitmodules:

~~~ini
[submodule "tools/converter"]
    path = tools/converter
    url = https://example.com/team/converter.git
~~~

File này là cấu hình được commit trong repository cha. Nó không chứa source code của submodule. Gitlink ghi commit cụ thể mà superproject muốn sử dụng.

Nếu thiếu <code>.gitmodules</code>, người clone repository cha có thể thấy một gitlink nhưng không biết URL chuẩn để tải nội dung con. Git sẽ cảnh báo khi thêm embedded repository để bạn quyết định có thực sự muốn dùng submodule hay không.

## 10. Submodule là ranh giới quản lý có chủ ý

Submodule phù hợp khi một dự án cần tham chiếu một repository khác như dependency được quản lý độc lập.

Ví dụ:

~~~text
game/
├── .git/
├── .gitmodules
├── src/
└── vendor/
    └── physics/
        └── .git
~~~

Repository cha quản lý:

- Đường dẫn submodule.
- URL để clone submodule.
- Commit cụ thể của submodule mà phiên bản dự án đang sử dụng.

Repository con quản lý:

- Source code và lịch sử riêng.
- Branch, tag, remote riêng.
- Commit được superproject tham chiếu.

Submodule không tự động theo dõi branch mới nhất. Superproject thường pin vào một commit cụ thể, giúp mọi người clone cùng một phiên bản dependency.

## 11. Thêm submodule đúng cách

Dùng lệnh <code>git submodule add</code> để đăng ký repository con:

~~~bash
git submodule add https://example.com/team/converter.git tools/converter
~~~

Lệnh này clone repository con vào thư mục đích, cập nhật file .gitmodules và stage gitlink trong repository cha. Nếu đường dẫn đã tồn tại và chứa dữ liệu hoặc metadata Git, hãy kiểm tra trạng thái trước; không xóa hay ghi đè thư mục đó để làm cho lệnh chạy được.

Kiểm tra:

~~~bash
git status
git diff -- .gitmodules
git ls-files --stage -- tools/converter
~~~

Sau đó commit cấu hình và gitlink:

~~~bash
git add .gitmodules tools/converter
git commit -m "Add converter as a submodule"
~~~

Khi thêm submodule, cần xác nhận URL có thể truy cập từ máy của đồng đội và CI. Nếu repository con là private, người clone superproject cũng cần quyền đọc repository con.

Không dùng <code>git add</code> đơn thuần như cách thay thế cho <code>git submodule add</code> nếu mục tiêu là tạo submodule có cấu hình chia sẻ rõ ràng.

## 12. Clone repository có submodule

Một lệnh clone thông thường có thể lấy superproject nhưng chưa khởi tạo nội dung submodule.

Để clone và lấy toàn bộ submodule ngay từ đầu:

~~~bash
git clone --recurse-submodules https://example.com/team/game.git
~~~

Nếu đã clone trước đó:

~~~bash
git submodule update --init --recursive
~~~

Ý nghĩa:

- <code>--init</code>: khởi tạo cấu hình local cho submodule.
- <code>--recursive</code>: áp dụng tiếp cho submodule lồng bên trong submodule.
- <code>update</code>: checkout commit được superproject ghi trong gitlink.

Nếu submodule chưa được khởi tạo, thư mục có thể trống hoặc chưa có nội dung như mong đợi. Điều này không nhất thiết là repository bị hỏng; có thể chỉ là submodule chưa được fetch và checkout.

## 13. Submodule thường checkout ở detached HEAD

Khi chạy:

~~~bash
git submodule update --init --recursive
~~~

Git checkout commit cụ thể mà superproject tham chiếu. Submodule thường ở trạng thái detached HEAD vì superproject lưu OID commit, không lưu tên branch.

Kiểm tra:

~~~bash
git -C tools/converter status
git -C tools/converter log -1 --oneline
git -C tools/converter branch --show-current
~~~

Nếu muốn phát triển bên trong submodule, chuyển sang branch phù hợp:

~~~bash
git -C tools/converter switch main
~~~

Sau đó chỉnh sửa, commit và push trong repository con theo quy trình riêng. Khi commit con đã có trên remote, quay lại superproject và stage thay đổi gitlink:

~~~bash
git add tools/converter
git commit -m "Update converter submodule revision"
~~~

Commit của superproject chỉ cập nhật commit mà nó tham chiếu. Nó không tự push commit mới trong submodule.

## 14. Cập nhật submodule theo commit được superproject ghi nhận

Để checkout lại đúng commit đã được commit trong superproject:

~~~bash
git submodule update --init --recursive
~~~

Đây là cách phù hợp khi muốn môi trường làm việc khớp với phiên bản dependency đã được nhóm chốt.

Nếu muốn cập nhật theo branch remote đã cấu hình cho submodule, có thể dùng:

~~~bash
git submodule update --remote --recursive
~~~

Lệnh <code>--remote</code> lấy phiên bản mới theo remote-tracking branch được cấu hình hoặc mặc định. Sau khi cập nhật, superproject có thể hiển thị submodule ở commit khác với gitlink đã commit. Bạn cần kiểm tra, stage gitlink và commit thay đổi trong superproject nếu muốn chia sẻ phiên bản mới.

Không dùng <code>--remote</code> một cách vô thức trong build tái lập được, vì branch remote có thể di chuyển theo thời gian. Với build cần kết quả ổn định, dùng commit đã pin trong superproject.

## 15. Kiểm tra trạng thái submodule

Từ repository cha:

~~~bash
git submodule status --recursive
git status --short
~~~

Ký hiệu đầu dòng trong kết quả <code>git submodule status</code> thường có ý nghĩa:

| Ký hiệu | Ý nghĩa |
|---|---|
| Dấu cách | Submodule đang ở commit được superproject ghi nhận |
| <code>-</code> | Submodule chưa được khởi tạo |
| <code>+</code> | Submodule đang checkout commit khác với gitlink |
| <code>U</code> | Gitlink đang có xung đột merge |

Kiểm tra thay đổi bên trong submodule:

~~~bash
git -C tools/converter status --short
~~~

Trạng thái của superproject và submodule là hai lớp khác nhau. Superproject có thể báo submodule có nội dung thay đổi hoặc commit mới, nhưng để biết file nào được sửa, hãy chạy <code>git status</code> bên trong submodule.

## 16. Phân biệt submodule với thư mục source được vendor trực tiếp

Không phải dependency nào cũng cần submodule.

| Cách quản lý | Repository cha lưu gì? | Phù hợp khi |
|---|---|---|
| Copy/vendor source | File và thư mục thông thường | Dự án muốn quản lý source như một phần của chính nó |
| Submodule | Gitlink tới commit và URL trong <code>.gitmodules</code> | Dependency có lịch sử và vòng đời độc lập |
| Linked worktree | Working tree liên kết cùng repository | Cần nhiều checkout/branch làm việc đồng thời |
| Repository độc lập lồng nhau | Thư mục con có Git metadata riêng nhưng không được đăng ký chính thức | Chỉ phù hợp khi chủ ý quản lý độc lập và hiểu giới hạn |

Nếu copy source từ một dự án khác vào monorepo, hãy chắc chắn đã loại metadata Git không mong muốn. Nếu muốn giữ lịch sử của dependency, cân nhắc submodule hoặc một phương pháp tích hợp lịch sử như subtree. Đừng để repository con tồn tại ngẫu nhiên rồi kỳ vọng Git cha sẽ quản lý mọi file.

## 17. Linked worktree không phải submodule

Linked worktree tạo thêm một working tree cho cùng một repository, thường dùng để làm việc trên nhiều branch cùng lúc.

Ví dụ:

~~~bash
git worktree add ../project-hotfix hotfix/login
git worktree list
~~~

Hai working tree dùng chung object database và metadata chung, nhưng có index và HEAD riêng cho từng worktree. Thư mục worktree phụ thường có file .git trỏ tới metadata dành riêng cho worktree đó.

Khác biệt với submodule:

- Worktree là một checkout khác của cùng repository.
- Submodule là repository khác được superproject tham chiếu qua gitlink.
- Submodule có URL và commit riêng được ghi trong .gitmodules/gitlink.
- Worktree được quản lý bởi <code>git worktree list</code>, <code>add</code>, <code>remove</code> và <code>prune</code>.

Nếu một worktree được đặt bên trong working tree của repository khác, repository cha có thể nhìn thấy nó như một repository lồng nhau. Không xóa file .git của worktree để “gộp” nó vào repository cha; hãy dùng lệnh worktree tương ứng.

## 18. Xử lý khi vô tình clone repository vào bên trong repository cha

Giả sử bạn chạy nhầm:

~~~bash
git clone https://example.com/team/converter.git tools/converter
~~~

trong khi <code>tools</code> đang thuộc repository cha.

Trước khi sửa, xác định mục tiêu:

- Muốn thư mục converter là source code bình thường của repository cha?
- Muốn nó là submodule có chủ đích?
- Muốn nó là repository độc lập và không được repository cha theo dõi?
- Hay clone nhầm vị trí và nên di chuyển nó ra ngoài working tree?

Nếu không chắc, dừng lại và kiểm tra các commit, remote và thay đổi local của repository con. Đừng xóa metadata chỉ để làm biến mất cảnh báo của Git.

### Trường hợp A — Repository con phải nằm ngoài repository cha

Di chuyển thư mục con ra một vị trí sibling nằm ngoài root của repository cha. Kiểm tra đường dẫn đích trước khi di chuyển và bảo đảm không ghi đè thư mục có sẵn.

Sau đó kiểm tra:

~~~bash
git status --short
git -C ../converter rev-parse --show-toplevel
~~~

Repository cha sẽ không còn nhìn thấy thư mục đó trong working tree của mình.

### Trường hợp B — Repository con là dependency độc lập, không muốn theo dõi trong cha

Nếu thư mục cần ở nguyên vị trí nhưng không thuộc dự án cha, thêm đường dẫn vào .gitignore của repository cha:

~~~gitignore
/tools/converter/
~~~

Kiểm tra rule:

~~~bash
git check-ignore -v tools/converter/
~~~

Nếu đường dẫn đã được stage như gitlink hoặc đã được track trong index, .gitignore không tự gỡ nó khỏi index. Hãy kiểm tra <code>git ls-files --stage -- tools/converter</code> và xử lý mục đã stage theo đúng trạng thái trước khi commit.

### Trường hợp C — Muốn thư mục trở thành submodule chính thức

Xác định URL chuẩn, commit cần pin và quyền truy cập. Dùng <code>git submodule add</code> để tạo cấu hình .gitmodules và gitlink. Nếu thư mục hiện tại đã chứa một repository, kiểm tra Git có thể sử dụng repository hiện có hay cần di chuyển/clone lại vào đường dẫn sạch.

Sau đó kiểm tra:

~~~bash
git diff -- .gitmodules
git ls-files --stage -- tools/converter
git submodule status
~~~

Chỉ commit khi URL và commit được tham chiếu đúng.

## 19. Xử lý khi vô tình chạy git init trong thư mục con

Giả sử bạn đang ở <code>project/tools/converter</code> và chạy:

~~~bash
git init
~~~

Lệnh này tạo metadata Git trong thư mục con. Từ đó, các lệnh Git chạy tại đây sẽ sử dụng repository mới.

Trước tiên, xác định root:

~~~bash
git rev-parse --show-toplevel
git rev-parse --git-dir
git status
~~~

Nếu đây là repository vừa tạo nhầm và chưa có lịch sử hoặc thay đổi cần giữ, vẫn cần kiểm tra kỹ trước khi bỏ metadata. Nếu đã tạo commit hoặc có thay đổi chưa commit, hãy bảo toàn chúng.

### Bảo toàn lịch sử repository con

Nếu cần giữ các commit đã tạo, có thể tạo bundle từ repository con:

~~~bash
git bundle create /safe/location/converter-backup.bundle --all
~~~

Bundle lưu các object reachable từ refs được đưa vào. Nó không chứa thay đổi chưa commit hoặc file chưa được theo dõi. Hãy sao lưu riêng working tree và các file chưa commit theo cách phù hợp.

Nếu repository con có remote, kiểm tra:

~~~bash
git remote -v
git branch -avv
git log --all --oneline --decorate
~~~

Đừng xóa .git trước khi xác định lịch sử nào cần giữ và bản sao lưu đã đọc được.

### Chuyển file thành nội dung bình thường của repository cha

Nếu quyết định thư mục con chỉ là source code bình thường của cha, cần bỏ ranh giới repository con sau khi đã sao lưu và xác nhận loại metadata.

- Nếu .git là thư mục metadata riêng, có thể di chuyển thư mục metadata ra vị trí backup ngoài working tree rồi stage source bằng repository cha.
- Nếu .git là file, không xóa nó theo hướng dẫn dành cho thư mục; nó có thể trỏ tới submodule, worktree hoặc separate git dir.
- Nếu đây là submodule chính thức, dùng quy trình tháo submodule phù hợp; không xử lý như một repository lồng nhau vô danh.
- Nếu lịch sử con cần được giữ trong lịch sử cha, hãy lập kế hoạch tích hợp lịch sử riêng, chẳng hạn dùng subtree hoặc viết lại lịch sử vào một thư mục con. Chỉ sao chép file và bỏ metadata sẽ không chuyển các commit cũ sang repository cha.

Sau khi đã xác nhận thư mục là source thông thường, kiểm tra root của cha rồi stage file:

~~~bash
git -C /path/to/project status --short
git -C /path/to/project add tools/converter
~~~

Thay đường dẫn ví dụ bằng root thực tế. Kiểm tra index để bảo đảm Git thêm file thường thay vì gitlink:

~~~bash
git -C /path/to/project ls-files --stage -- tools/converter
~~~

Các file thông thường có mode như <code>100644</code> hoặc <code>100755</code>; nếu vẫn thấy <code>160000</code>, index đang lưu gitlink.

## 20. Nếu repository cha đã track file trước khi repository con xuất hiện

Một trường hợp dễ nhầm là thư mục con đã có source được repository cha theo dõi, sau đó ai đó mới chạy <code>git init</code> hoặc clone repository khác vào bên trong.

Trong tình huống này, Git index của cha có thể vẫn chứa các file đã track trước đó. Việc xuất hiện metadata .git không tự động chuyển toàn bộ thư mục thành một gitlink.

Kiểm tra:

~~~bash
git ls-files --stage -- tools/converter
git status --short
git -C tools/converter status --short
~~~

Nếu có nhiều file mode thông thường trong index, repository cha vẫn đang quản lý những file đó. Nếu có mode <code>160000</code>, Git đang lưu gitlink. Có thể tồn tại trạng thái chuyển tiếp hoặc file chưa được stage; hãy xử lý theo output thực tế.

Không chạy <code>git rm -r</code>, <code>git clean</code> hoặc xóa metadata một cách máy móc. Các lệnh đó có thể loại bỏ file hoặc thay đổi index rộng hơn dự kiến. Hãy sao lưu, xác định trạng thái tracked/untracked và chọn chuyển đổi có kiểm soát.

## 21. Tháo submodule đúng cách

Nếu một submodule không còn cần thiết, cần tháo liên kết khỏi superproject theo các bước có kiểm tra.

Trước hết, xác nhận đường dẫn và trạng thái:

~~~bash
git submodule status
git status --short
git -C tools/converter status --short
~~~

Sau khi đã bảo toàn thay đổi cần giữ, loại bỏ gitlink khỏi index và file cấu hình .gitmodules theo quy trình của phiên bản Git đang dùng. Ví dụ với một submodule đã được xác nhận:

~~~bash
git rm tools/converter
~~~

Lệnh này stage việc xóa submodule khỏi superproject và cập nhật .gitmodules khi phù hợp. Kiểm tra diff trước khi commit:

~~~bash
git diff --cached -- .gitmodules
git diff --cached --summary
~~~

Metadata submodule có thể còn trong thư mục .git/modules/ để phục vụ khôi phục hoặc cleanup. Chỉ dọn phần metadata còn lại sau khi chắc chắn không cần giữ repository con và hiểu rõ đường dẫn. Không xóa thủ công thư mục .git/modules của submodule khác.

Nếu muốn giữ source code như file thường thay vì xóa nội dung, hãy sao lưu/copy source ra vị trí an toàn trước, tháo gitlink, rồi đưa source vào index của repository cha theo kế hoạch riêng.

## 22. Các lệnh chẩn đoán nhanh

| Mục tiêu | Lệnh |
|---|---|
| Tìm root hiện tại | <code>git rev-parse --show-toplevel</code> |
| Tìm Git directory | <code>git rev-parse --git-dir</code> |
| Tìm Git common directory | <code>git rev-parse --git-common-dir</code> |
| Kiểm tra superproject của submodule | <code>git rev-parse --show-superproject-working-tree</code> |
| Liệt kê submodule | <code>git submodule status --recursive</code> |
| Liệt kê linked worktree | <code>git worktree list --porcelain</code> |
| Kiểm tra mode trong index | <code>git ls-files --stage -- &lt;path&gt;</code> |
| Kiểm tra gitlink đã commit | <code>git ls-tree HEAD -- &lt;path&gt;</code> |
| Kiểm tra remote repository con | <code>git -C &lt;path&gt; remote -v</code> |
| Kiểm tra trạng thái repository con | <code>git -C &lt;path&gt; status --short</code> |

Thực hiện các lệnh từ đúng repository root hoặc dùng <code>git -C</code> để chỉ định rõ đường dẫn. Điều này giảm nguy cơ vô tình thao tác trên repository con khi bạn định thay đổi repository cha.

## 23. Những lỗi thường gặp

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| <code>git status</code> ở cha chỉ hiện một thư mục chưa theo dõi | Thư mục con có repository riêng | Kiểm tra root của thư mục con và xác định có phải submodule không |
| <code>git add</code> cảnh báo embedded Git repository | Đang thêm repository con mà chưa đăng ký submodule | Chọn chuyển thành file thường, ignore, di chuyển ra ngoài hoặc tạo submodule chính thức |
| Clone cha xong thư mục con trống | Gitlink chưa được khởi tạo hoặc thiếu URL submodule | Kiểm tra .gitmodules, chạy <code>git submodule update --init --recursive</code> |
| Superproject báo submodule có commit mới | HEAD của submodule khác gitlink đã commit | Xác minh commit con, stage gitlink và commit thay đổi trong cha nếu có chủ ý |
| Git command chạy nhầm repository | Terminal đang ở trong repository con | Kiểm tra <code>git rev-parse --show-toplevel</code> hoặc dùng <code>git -C</code> |
| Không thể xóa .git như một thư mục | .git là file trỏ tới metadata khác | Đọc file, kiểm tra submodule/worktree/separate git dir trước khi xử lý |
| .gitignore không làm mất mục đã stage | Đường dẫn đã có trong index | Kiểm tra <code>git ls-files</code> và gỡ index có chủ ý |
| Xóa submodule nhưng metadata vẫn còn | Metadata submodule được lưu riêng trong .git/modules | Kiểm tra và cleanup theo quy trình, tránh xóa nhầm submodule khác |

## 24. Quy trình quyết định khi phát hiện repository lồng nhau

Có thể dùng trình tự sau trước khi chỉnh sửa:

~~~text
Phát hiện thư mục con có .git
             |
             v
So sánh root bằng git rev-parse
             |
             v
Có phải submodule?
       /             \
     Có               Không
     |                 |
Kiểm tra .gitmodules   Có trong git worktree list?
và gitlink mode       /              \
                   Có                Không
                   |                  |
              Linked worktree     Repo độc lập lồng nhau
                   |                  |
             Dùng git worktree    Xác định ý định:
             để quản lý           move / ignore / convert
                                      / submodule
~~~

Sau khi xác định loại repository, hãy bảo toàn thay đổi và lịch sử cần giữ trước khi di chuyển hoặc tháo metadata.

## 25. Checklist trước khi sửa repository lồng nhau

- [ ] Đã xác định root của repository cha và repository con.
- [ ] Đã kiểm tra .git là directory hay file.
- [ ] Đã kiểm tra submodule bằng <code>--show-superproject-working-tree</code>.
- [ ] Đã kiểm tra linked worktree bằng <code>git worktree list</code>.
- [ ] Đã kiểm tra .gitmodules và gitlink mode <code>160000</code>.
- [ ] Đã xác định repository con có commit hoặc thay đổi local cần giữ không.
- [ ] Đã sao lưu refs và working tree nếu cần.
- [ ] Đã quyết định move, ignore, convert thành file thường hay đăng ký submodule.
- [ ] Đã kiểm tra index sau khi xử lý.
- [ ] Đã thử clone hoặc khởi tạo lại trên một bản sao để xác nhận đồng đội nhận được cấu trúc mong muốn.

## 26. Những điểm cần ghi nhớ

- Git chọn repository gần nhất khi tìm metadata từ thư mục hiện tại đi lên.
- <code>git rev-parse --show-toplevel</code> xác định root mà lệnh hiện tại đang dùng.
- Repository lồng nhau có lịch sử và index riêng; Git cha không tự quản lý mọi file bên trong.
- Khi thêm embedded repository, Git có thể stage gitlink mode <code>160000</code>, không phải toàn bộ source.
- Submodule chính thức kết hợp gitlink trong tree với cấu hình URL/path trong .gitmodules.
- Submodule pin một commit cụ thể; clone cần <code>--recurse-submodules</code> hoặc <code>git submodule update --init --recursive</code>.
- Linked worktree chia sẻ repository chung và được quản lý bằng <code>git worktree</code>.
- .git có thể là directory hoặc file trỏ tới metadata ở nơi khác; không xóa khi chưa xác định loại.
- Nếu chuyển repository con thành file thường, cần bảo toàn lịch sử và thay đổi local trước khi bỏ ranh giới.
- Luôn kiểm tra root, index mode, .gitmodules, submodule status và worktree list trước khi sửa.

Nhận diện đúng ranh giới repository giúp tránh commit nhầm gitlink, bỏ sót source code hoặc làm mất lịch sử của dự án con. Khi repository con là chủ ý, hãy đăng ký và cập nhật nó như submodule hoặc worktree đúng cơ chế; khi nó xuất hiện ngoài ý muốn, hãy xác định trạng thái và bảo toàn dữ liệu trước khi chuyển đổi.

