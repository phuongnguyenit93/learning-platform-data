# Định vị commit bằng mã rút gọn, HEAD~, HEAD^ và tên tham chiếu

Khi xem lịch sử Git, bạn thường cần chỉ đúng một commit để xem nội dung, so sánh thay đổi, tạo nhánh hoặc khôi phục trạng thái. Git cho phép định vị commit bằng mã object (OID), một phần mã hash, tên branch/tag, các tên tham chiếu đặc biệt như HEAD, hoặc biểu thức quan hệ cha như <code>HEAD~2</code> và <code>HEAD^</code>.

Những cách viết này đều dẫn tới một object hoặc commit, nhưng ý nghĩa không giống nhau. Mã rút gọn nhận diện object theo hash; tên tham chiếu nhận diện vị trí có tên trong repository; <code>~</code> và <code>^</code> đi theo quan hệ parent trong đồ thị commit.

Bài này giải thích cách đọc và kết hợp các revision selector để xác định đúng commit trong lịch sử tuyến tính lẫn lịch sử có merge.

## 1. Commit được định danh bằng object ID

Mỗi Git object có một định danh được tính từ nội dung object và loại object. Định danh này thường được gọi là object ID (OID) hoặc hash.

Một commit object chứa các thông tin chính:

- Tree OID của snapshot.
- Parent OID (một hoặc nhiều parent).
- Author và committer.
- Thời gian tạo commit.
- Commit message.

Ví dụ output:

~~~bash
git log -1 --format=fuller
~~~

~~~text
commit 4f2c9a7d8e1b...
Author: Developer <dev@example.com>
Date:   Tue Nov 17 10:30:00 2026 +0700

    Add payment validation
~~~

Dòng bắt đầu bằng <code>commit</code> là OID của commit. Khi truyền OID cho các lệnh như <code>git show</code>, <code>git log</code> hoặc <code>git branch</code>, Git có thể định vị object tương ứng.

OID là định danh theo nội dung object. Nếu nội dung commit thay đổi, OID của commit cũng thay đổi. Vì vậy, commit được tạo lại sau rebase thường có OID khác commit ban đầu, dù thay đổi mã nguồn có thể tương tự.

## 2. SHA-1, SHA-256 và độ dài OID

Repository Git truyền thống dùng định dạng object SHA-1, với OID đầy đủ dài 40 ký tự hex. Git cũng hỗ trợ repository dùng định dạng SHA-256, với OID đầy đủ dài 64 ký tự hex.

Kiểm tra định dạng object của repository:

~~~bash
git rev-parse --show-object-format
~~~

Kết quả thường là:

~~~text
sha1
~~~

hoặc:

~~~text
sha256
~~~

Không nên giả định mọi OID luôn có 40 ký tự. Khi viết tài liệu, script hoặc công cụ tích hợp, hãy để Git cung cấp OID thay vì tự cắt chuỗi theo độ dài cố định.

Tùy chọn <code>--show-object-format</code> có trong Git 2.29 trở lên. Định dạng SHA-256 vẫn có một số giới hạn tương thích với công cụ hoặc dịch vụ chỉ hỗ trợ repository SHA-1; khi dùng định dạng này, hãy kiểm tra toàn bộ toolchain cùng hỗ trợ.

Lấy OID đầy đủ của commit hiện tại:

~~~bash
git rev-parse HEAD
~~~

Lấy OID đầy đủ của một commit cụ thể:

~~~bash
git rev-parse main
~~~

## 3. Mã hash rút gọn là gì?

Git cho phép dùng một tiền tố của OID thay cho OID đầy đủ, miễn là tiền tố đó đủ dài để xác định duy nhất một object trong repository hiện tại.

Ví dụ, nếu OID đầy đủ là:

~~~text
4f2c9a7d8e1b63c5...
~~~

thì <code>4f2c9a7</code> có thể dùng được nếu không có object khác bắt đầu bằng cùng chuỗi đó. Nếu xuất hiện một object khác có chung tiền tố, Git báo mã viết tắt không duy nhất và yêu cầu thêm ký tự.

Điểm cần nhớ:

- Mã rút gọn là tiền tố của OID, không phải một mã định danh mới.
- Độ dài tối thiểu cần thiết phụ thuộc số lượng object và các tiền tố trùng nhau.
- Khi repository nhận thêm object, một tiền tố trước đây duy nhất có thể trở nên mơ hồ.
- OID đầy đủ ổn định hơn để lưu trong tài liệu vận hành hoặc trao đổi chính xác giữa các repository cùng object format.

## 4. Lấy mã rút gọn bằng git rev-parse

Dùng <code>--short</code> để yêu cầu Git in OID rút gọn:

~~~bash
git rev-parse --short HEAD
~~~

Có thể yêu cầu tối thiểu một độ dài cụ thể:

~~~bash
git rev-parse --short=12 HEAD
~~~

Con số <code>12</code> là độ dài tối thiểu mong muốn. Nếu cần nhiều ký tự hơn để bảo đảm duy nhất, Git có thể in chuỗi dài hơn.

Lấy OID rút gọn của một branch:

~~~bash
git rev-parse --short=12 main
~~~

Lấy OID rút gọn của tag:

~~~bash
git rev-parse --short=12 v2.4.0
~~~

Dùng lệnh này thay vì tự lấy vài ký tự đầu của kết quả <code>git log</code>, vì Git có trách nhiệm tính độ dài đủ duy nhất trong repository.

## 5. Xem OID và mã rút gọn trong git log

Để xem commit cùng mã hash rút gọn:

~~~bash
git log --oneline
~~~

Ví dụ:

~~~text
4f2c9a7 Add payment validation
19ab3d2 Add payment endpoint
a6e8c10 Initial project
~~~

Tùy chọn <code>--oneline</code> tương đương cách hiển thị commit ngắn gọn, thường bao gồm OID rút gọn và subject của commit message.

Muốn hiển thị rõ OID đầy đủ:

~~~bash
git log -5 --format="%H %s"
~~~

Trong đó:

- <code>%H</code> là OID đầy đủ.
- <code>%h</code> là OID rút gọn.
- <code>%s</code> là subject của commit message.
- <code>%an</code> là tên author.
- <code>%ad</code> là author date, định dạng phụ thuộc tùy chọn date.

Ví dụ:

~~~bash
git log -5 --format="%h %ad %an %s" --date=short
~~~

## 6. Vì sao không nên tự chọn độ dài hash cố định?

Một mã rút gọn 7 ký tự có thể đủ duy nhất trong repository nhỏ, nhưng không bảo đảm trong repository lớn. Khi số object tăng, xác suất tiền tố trùng cũng tăng.

Không nên viết script giả định mọi commit có mã rút gọn đúng 7 ký tự. Hãy dùng:

~~~bash
git rev-parse --short HEAD
~~~

hoặc nếu cần định dạng dễ đọc có độ dài tối thiểu:

~~~bash
git rev-parse --short=12 HEAD
~~~

Nếu cần định danh để lưu trữ lâu dài, dùng OID đầy đủ:

~~~bash
git rev-parse HEAD
~~~

Mã rút gọn phù hợp để đọc nhanh trong log và trao đổi nội bộ. OID đầy đủ phù hợp hơn khi lưu trong hệ thống tích hợp, log kiểm toán hoặc tài liệu cần tránh mơ hồ.

## 7. Tên tham chiếu (ref) là gì?

Ref là tên mà Git dùng để trỏ tới một object, thường là commit. Thay vì nhớ hash, bạn có thể dùng tên branch, tag hoặc ref đặc biệt.

Các ref phổ biến:

| Loại | Ví dụ | Vị trí thường dùng |
|---|---|---|
| Local branch | <code>main</code> | <code>refs/heads/main</code> |
| Tag | <code>v2.4.0</code> | <code>refs/tags/v2.4.0</code> |
| Remote-tracking branch | <code>origin/main</code> | <code>refs/remotes/origin/main</code> |
| HEAD | <code>HEAD</code> | Ref đặc biệt cho vị trí checkout hiện tại |
| Remote fetch result | <code>FETCH_HEAD</code> | Thông tin ref/commit nhận được từ lần fetch gần nhất |
| Previous operation tip | <code>ORIG_HEAD</code> | Ref tạm được một số thao tác cập nhật |

Tên ngắn như <code>main</code> hoặc <code>v2.4.0</code> giúp thao tác thuận tiện. Nếu có tên trùng hoặc cần rõ ràng tuyệt đối, dùng tên đầy đủ như <code>refs/heads/main</code> hoặc <code>refs/tags/v2.4.0</code>.

## 8. Local branch và remote-tracking branch khác nhau

Local branch là nhánh bạn làm việc trực tiếp, ví dụ:

~~~bash
git switch main
~~~

Ref đầy đủ của nó là:

~~~text
refs/heads/main
~~~

Remote-tracking branch là bản ghi local về một branch trên remote, ví dụ:

~~~text
refs/remotes/origin/main
~~~

Tên rút gọn thường dùng là <code>origin/main</code>. Ref này được cập nhật khi fetch hoặc khi các thao tác remote tương ứng cập nhật tracking refs. Nó không tự thay đổi theo từng commit mới trên server nếu bạn chưa fetch.

Xem các branch:

~~~bash
git branch
git branch -r
git branch -avv
~~~

Nếu muốn biết commit hiện tại khác remote-tracking branch bao nhiêu commit, fetch trước để cập nhật thông tin rồi mới so sánh:

~~~bash
git fetch origin
git log --oneline main..origin/main
~~~

Đừng hiểu <code>origin/main</code> là con trỏ trực tiếp tới trạng thái live của server ở mọi thời điểm. Nó là ref local phản ánh lần đồng bộ gần nhất.

## 9. Tag và annotated tag khi định vị commit

Tag là ref thường dùng để đánh dấu phiên bản hoặc mốc phát hành.

Xem tag:

~~~bash
git tag --list
~~~

Xem commit mà tag trỏ tới:

~~~bash
git show v2.4.0
~~~

Lightweight tag trỏ trực tiếp tới một object, thường là commit. Annotated tag có tag object riêng chứa tagger, ngày tạo, message và có thể có chữ ký; tag object lại trỏ tới object được đánh dấu.

Khi cần lấy commit mà một tag đại diện, dùng cú pháp peel ở phần sau hoặc yêu cầu Git xác nhận loại commit.

Ví dụ:

~~~bash
git rev-parse --verify 'v2.4.0^{commit}'
~~~

Cách này hữu ích khi tag có thể là annotated tag và bạn cần commit cuối cùng thay vì tag object.

## 10. HEAD là tên tham chiếu đặc biệt

<code>HEAD</code> đại diện cho vị trí hiện tại mà repository đang checkout.

Thông thường, HEAD là symbolic ref trỏ tới branch hiện tại. Ví dụ:

~~~text
HEAD -> refs/heads/main
~~~

Khi đang làm việc trên branch main, <code>HEAD</code> và <code>main</code> thường trỏ tới cùng commit.

Kiểm tra:

~~~bash
git status -sb
git branch --show-current
git symbolic-ref --short HEAD
~~~

Nếu đang ở detached HEAD, HEAD trỏ trực tiếp tới commit thay vì branch. Khi đó, <code>git branch --show-current</code> có thể in dòng trống và <code>git symbolic-ref --short HEAD</code> không thành công vì HEAD không còn là symbolic ref.

Kiểm tra OID mà HEAD đang trỏ tới:

~~~bash
git rev-parse HEAD
~~~

## 11. HEAD~ và HEAD~n có nghĩa gì?

Dấu <code>~</code> dùng để đi ngược theo **first parent** (parent thứ nhất) của commit.

- <code>HEAD~0</code> là HEAD hiện tại.
- <code>HEAD~1</code> là parent thứ nhất của HEAD.
- <code>HEAD~2</code> là parent thứ nhất của parent thứ nhất.
- <code>HEAD~3</code> tiếp tục đi lùi ba lần theo first-parent chain.

Ví dụ lịch sử tuyến tính:

~~~text
A---B---C---D---E  main
                ^
               HEAD
~~~

Khi HEAD ở E:

| Biểu thức | Commit được chọn |
|---|---|
| <code>HEAD</code> | E |
| <code>HEAD~1</code> | D |
| <code>HEAD~2</code> | C |
| <code>HEAD~3</code> | B |
| <code>HEAD~4</code> | A |

Có thể bỏ số 1:

~~~bash
git show HEAD~
~~~

Tương đương:

~~~bash
git show HEAD~1
~~~

<code>HEAD~</code> cũng tương đương <code>HEAD^</code> trong trường hợp parent thứ nhất.

## 12. HEAD^ và HEAD^n có nghĩa gì?

Dấu <code>^</code> chọn một parent cụ thể của commit.

- <code>HEAD^</code> tương đương <code>HEAD^1</code>, tức parent thứ nhất.
- <code>HEAD^2</code> chọn parent thứ hai.
- <code>HEAD^3</code> chọn parent thứ ba nếu commit có ít nhất ba parent.

Trong lịch sử tuyến tính, mỗi commit thông thường chỉ có một parent, vì vậy <code>HEAD^</code> và <code>HEAD~1</code> cho cùng kết quả.

Khác biệt thể hiện rõ ở merge commit, vì merge commit thường có hai parent.

Ví dụ:

~~~text
        D---E
       /     \
A---B---C-----M  main
              ^
             HEAD
~~~

Trong ví dụ này:

- Parent thứ nhất của M là C (nhánh được checkout khi merge).
- Parent thứ hai của M là E (tip của nhánh được merge).

Vì vậy:

~~~bash
git show HEAD^1
git show HEAD^2
~~~

Lệnh đầu xem C; lệnh thứ hai xem E.

## 13. Phân biệt HEAD~2, HEAD^^ và HEAD^2

Đây là chỗ người mới học Git thường nhầm.

Trong lịch sử tuyến tính:

~~~text
A---B---C  main
        ^
       HEAD
~~~

Các biểu thức sau cùng trỏ tới A:

- <code>HEAD~2</code>
- <code>HEAD^^</code>
- <code>HEAD~1~1</code>
- <code>HEAD^1^1</code>

Nhưng trong merge commit:

~~~text
        D---E
       /     \
A---B---C-----M
              ^
             HEAD
~~~

Ý nghĩa khác nhau:

| Biểu thức | Đường đi |
|---|---|
| <code>HEAD~2</code> | M → parent 1 là C → parent 1 là B |
| <code>HEAD^^</code> | M → parent 1 là C → parent 1 là B |
| <code>HEAD^2</code> | M → parent 2 là E |
| <code>HEAD^1</code> | M → parent 1 là C |

Hãy nhớ: số sau dấu <code>~</code> là số bước đi theo first parent; số sau dấu <code>^</code> là số thứ tự parent được chọn tại một commit.

## 14. Dùng ~ và ^ để duyệt lịch sử có merge

Với merge commit, việc chọn parent quyết định lịch sử bạn đang đi theo.

Ví dụ:

~~~bash
git log --oneline --graph --decorate --all
~~~

Giả sử HEAD là merge commit M:

~~~bash
git show HEAD^1
git show HEAD^2
git log --oneline HEAD~3
git log --oneline HEAD^2
~~~

Một số trường hợp sử dụng:

- Xem nhánh chính trước khi merge: thường dùng <code>HEAD^1</code>.
- Xem tip của nhánh vừa được merge: thường dùng <code>HEAD^2</code>.
- Đi lùi nhiều commit theo tuyến first-parent: dùng <code>HEAD~n</code>.
- Đi qua parent cụ thể của một merge: dùng <code>HEAD^n</code>.

Không phải merge commit nào cũng có đúng hai parent. Octopus merge có thể có nhiều parent. Nếu chọn parent index không tồn tại, Git sẽ báo lỗi.

## 15. ^0: yêu cầu commit hiện tại của revision

Cú pháp <code>^0</code> có nghĩa là xác nhận revision đang trỏ tới một commit và trả về chính commit đó, không đi sang parent.

Ví dụ:

~~~bash
git rev-parse 'HEAD^0'
git rev-parse 'main^0'
git rev-parse 'v2.4.0^0'
~~~

Cú pháp này hữu ích khi revision có thể là tên tag trỏ tới annotated tag object. <code>^{commit}</code> rõ nghĩa hơn khi mục tiêu là peel tag và xác nhận object cuối cùng thuộc loại commit.

Một root commit không có parent. Vì vậy, <code>HEAD^</code> tại root commit sẽ thất bại, nhưng <code>HEAD^0</code> vẫn trả về chính root commit.

## 16. Peel tag với ^{} và ^{commit}

Git hỗ trợ cú pháp peel để đi từ tag object tới object được tag trỏ tới.

- <code>v2.4.0^{}</code> yêu cầu Git peel tag đệ quy tới object không còn là tag.
- <code>v2.4.0^{commit}</code> yêu cầu Git peel và xác nhận object đích là commit.
- <code>v2.4.0^{tree}</code> yêu cầu object đích là tree.

Ví dụ:

~~~bash
git rev-parse 'v2.4.0^{}'
git rev-parse 'v2.4.0^{commit}'
git cat-file -t 'v2.4.0^{commit}'
~~~

Lệnh cuối in loại object, trong trường hợp này là <code>commit</code>.

Dùng dấu nháy đơn quanh revision expression để shell không diễn giải ký tự đặc biệt. Điều này đặc biệt hữu ích trong Bash, PowerShell và các script đa nền tảng.

## 17. Các tên tham chiếu đặc biệt khác

Ngoài HEAD, Git có một số tên tham chiếu hữu ích:

| Tên | Ý nghĩa thường gặp |
|---|---|
| <code>HEAD</code> | Commit hoặc branch hiện đang checkout |
| <code>ORIG_HEAD</code> | Vị trí HEAD trước một số thao tác lớn như reset/merge |
| <code>FETCH_HEAD</code> | Thông tin các ref/commit nhận từ lần fetch gần nhất |
| <code>MERGE_HEAD</code> | Commit đang được merge vào HEAD khi merge chưa hoàn tất |
| <code>CHERRY_PICK_HEAD</code> | Commit đang được cherry-pick khi thao tác chưa hoàn tất |

Các tên này không phải branch thông thường. Một số chỉ tồn tại trong lúc một thao tác đang diễn ra hoặc được cập nhật khi có thao tác khác.

Ví dụ kiểm tra ORIG_HEAD:

~~~bash
git show --no-patch --oneline ORIG_HEAD
~~~

Kiểm tra FETCH_HEAD:

~~~bash
git show --no-patch --oneline FETCH_HEAD
~~~

Nếu ref không tồn tại trong trạng thái hiện tại, Git sẽ báo không thể phân giải revision đó. Không nên dùng chúng như một thay thế ổn định cho branch hoặc tag.

## 18. Upstream selector: @{upstream} và @{u}

Một branch có thể cấu hình upstream branch, thường là remote-tracking branch mà local branch theo dõi.

Ví dụ branch local <code>feature/payment</code> theo dõi <code>origin/feature/payment</code>. Có thể dùng:

~~~bash
git rev-parse --abbrev-ref '@{upstream}'
~~~

Hoặc dạng rút gọn:

~~~bash
git rev-parse --abbrev-ref '@{u}'
~~~

Xem commit upstream:

~~~bash
git log -1 --oneline '@{upstream}'
~~~

Các biểu thức <code>@{upstream}</code> và <code>@{u}</code> phụ thuộc cấu hình upstream của branch hiện tại. Nếu branch chưa thiết lập upstream, Git không thể phân giải biểu thức này.

Xem cấu hình tracking:

~~~bash
git branch -vv
~~~

## 19. Reflog selector ref@{n} khác với HEAD~n

Git có hai cú pháp dễ bị nhầm vì cùng dùng dấu ngoặc nhọn:

- <code>HEAD~2</code> đi lùi hai thế hệ theo first parent trong đồ thị commit.
- <code>HEAD@{2}</code> chọn entry thứ ba trong reflog của HEAD, tức một trạng thái HEAD đã được ghi trước đó.

Ví dụ:

~~~bash
git reflog show HEAD
git show 'HEAD@{2}'
git show HEAD~2
~~~

Hai lệnh <code>git show</code> có thể hiển thị hai commit hoàn toàn khác nhau.

Reflog selector có thể dùng với tên ref khác:

~~~bash
git show 'main@{1}'
git show 'origin/main@{1}'
~~~

Các entry reflog là local, có thể hết hạn hoặc bị xóa. <code>~</code> và <code>^</code> dựa trên quan hệ parent trong commit graph, không dựa trên số thứ tự thao tác local.

## 20. Dùng revision selector với git show

<code>git show</code> là cách nhanh để xem commit được chọn và thay đổi của commit đó.

Ví dụ:

~~~bash
git show HEAD
git show HEAD~1
git show HEAD^2
git show 4f2c9a7
git show main
git show v2.4.0
~~~

Chỉ xem metadata commit, không hiển thị patch:

~~~bash
git show --no-patch --format=fuller HEAD~2
~~~

Chỉ xem danh sách file và thống kê thay đổi:

~~~bash
git show --stat HEAD^
~~~

Nếu revision là một tag annotated, <code>git show</code> có thể hiển thị cả thông tin tag và object được tag trỏ tới. Dùng <code>^{commit}</code> khi muốn xác nhận chính xác đối tượng commit.

## 21. Dùng revision selector với git log

<code>git log</code> nhận một hoặc nhiều revision để giới hạn lịch sử cần xem.

Ví dụ:

~~~bash
git log --oneline HEAD~5..HEAD
~~~

Lệnh này liệt kê các commit reachable từ HEAD nhưng không thuộc phần lịch sử được chỉ ra bởi HEAD~5. Với lịch sử tuyến tính, kết quả thường là năm commit gần nhất sau mốc đó.

Xem lịch sử từ một branch:

~~~bash
git log --oneline main
~~~

Xem lịch sử từ remote-tracking branch:

~~~bash
git log --oneline origin/main
~~~

Xem đồ thị của nhiều refs:

~~~bash
git log --graph --decorate --oneline --all
~~~

Lưu ý, toán tử <code>..</code> trong revision range của <code>git log</code> có nghĩa tập commit ở phía phải mà phía trái không chứa. Nó không phải cú pháp đi lùi parent như <code>~</code>.

## 22. Dùng revision selector với git diff

<code>git diff</code> so sánh snapshot của hai revision:

~~~bash
git diff HEAD~1 HEAD
~~~

So sánh parent thứ nhất của merge với merge commit:

~~~bash
git diff HEAD^1 HEAD
~~~

So sánh parent thứ hai của merge với merge commit:

~~~bash
git diff HEAD^2 HEAD
~~~

So sánh branch:

~~~bash
git diff main feature/payment
~~~

Trong <code>git diff A B</code>, Git so sánh tree của A với tree của B. Cần chú ý hướng so sánh: phần thêm/xóa được xác định từ A sang B.

Dạng ba chấm trong <code>git diff A...B</code> so sánh merge-base của A và B với B. Cách này thường hữu ích khi muốn xem thay đổi của nhánh B kể từ điểm phân nhánh chung.

## 23. Dùng revision selector với branch và checkout

Có thể tạo branch mới từ một revision bất kỳ:

~~~bash
git branch feature/restore HEAD~2
~~~

Lệnh trên tạo branch mới trỏ tới commit cách HEAD hai bước theo first parent, nhưng không chuyển working tree sang branch mới.

Tạo và chuyển sang branch mới:

~~~bash
git switch -c feature/restore HEAD~2
~~~

Nếu chỉ muốn xem một commit mà không tạo branch:

~~~bash
git switch --detach HEAD~2
~~~

Lúc này repository ở trạng thái detached HEAD. Bạn có thể xem hoặc thử nghiệm, nhưng nếu tạo commit mới thì nên tạo branch để giữ commit đó trước khi rời trạng thái này.

Không dùng <code>git checkout</code> với một tên mơ hồ khi muốn chuyển branch. <code>git switch</code> làm rõ ý định chuyển nhánh; <code>git restore</code> dành cho thao tác khôi phục file.

## 24. Xác minh revision trước khi dùng trong script

Khi revision đến từ tham số người dùng hoặc dữ liệu bên ngoài, hãy xác minh trước khi đưa vào lệnh thay đổi repository.

Kiểm tra revision có tồn tại và phân giải thành commit:

~~~bash
git rev-parse --verify --end-of-options 'main^{commit}'
~~~

Nếu hợp lệ, lệnh in OID commit. Nếu không hợp lệ hoặc revision không thể peel thành commit, lệnh trả lỗi.

Có thể kiểm tra loại object:

~~~bash
git cat-file -t 'main^{commit}'
~~~

Kết quả mong đợi:

~~~text
commit
~~~

Dùng <code>--end-of-options</code> giúp Git không diễn giải một chuỗi đầu vào bắt đầu bằng dấu gạch ngang như một option của lệnh. Trong script, vẫn cần xử lý mã thoát và kiểm tra input theo ngữ cảnh.

## 25. Phân biệt revision và pathspec

Một số lệnh Git nhận cả revision và đường dẫn file. Dấu <code>--</code> dùng để kết thúc danh sách revision/options và bắt đầu pathspec.

Ví dụ:

~~~bash
git log main -- src/payment
git show HEAD~1 -- src/payment/service.java
git diff HEAD~2 HEAD -- src/payment
~~~

Trong các lệnh trên:

- <code>main</code>, <code>HEAD~1</code>, <code>HEAD~2</code> là revision.
- <code>src/payment</code> hoặc đường dẫn file là pathspec.
- <code>--</code> giúp Git hiểu phần sau là đường dẫn, kể cả khi tên file có thể giống tên ref.

Khi cần kiểm tra chính xác một revision, dùng <code>git rev-parse --verify</code>. Khi cần giới hạn lịch sử theo file, dùng pathspec sau <code>--</code>.

## 26. Bảng tra cứu nhanh các biểu thức revision

| Biểu thức | Ý nghĩa |
|---|---|
| <code>HEAD</code> | Commit hiện tại |
| <code>HEAD~</code> | Parent thứ nhất của HEAD |
| <code>HEAD~1</code> | Parent thứ nhất của HEAD |
| <code>HEAD~2</code> | Đi theo first parent hai lần |
| <code>HEAD^</code> | Parent thứ nhất của HEAD |
| <code>HEAD^1</code> | Parent thứ nhất của HEAD |
| <code>HEAD^2</code> | Parent thứ hai của HEAD |
| <code>HEAD^^</code> | Đi theo parent thứ nhất hai lần |
| <code>HEAD^0</code> | Chính commit HEAD sau khi xác nhận loại commit |
| <code>main</code> | Local branch main |
| <code>origin/main</code> | Remote-tracking branch origin/main |
| <code>refs/heads/main</code> | Tên đầy đủ của local branch main |
| <code>refs/tags/v2.4.0</code> | Tên đầy đủ của tag |
| <code>v2.4.0^{commit}</code> | Commit mà tag peel tới |
| <code>HEAD@{1}</code> | Vị trí HEAD ở entry reflog trước đó |
| <code>@{u}</code> | Upstream của branch hiện tại |

## 27. Lỗi thường gặp khi định vị commit

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Git báo ambiguous short object ID | Mã hash rút gọn không còn duy nhất | Lấy OID đầy đủ hoặc dùng tiền tố dài hơn do Git cung cấp |
| <code>HEAD^</code> không phân giải được | HEAD đang ở root commit không có parent | Dùng <code>HEAD^0</code> để lấy chính commit |
| <code>HEAD^2</code> báo lỗi | Commit không có parent thứ hai | Kiểm tra commit có phải merge commit hay không |
| <code>HEAD~2</code> không phân giải được | Lịch sử first-parent không đủ hai bước | Xem <code>git log --graph</code> và chọn revision phù hợp |
| <code>origin/main</code> cũ hơn server | Chưa fetch remote | Chạy <code>git fetch origin</code> rồi kiểm tra lại |
| <code>@{u}</code> không hợp lệ | Branch chưa cấu hình upstream | Kiểm tra <code>git branch -vv</code> và thiết lập upstream nếu cần |
| Tag không trả về commit trực tiếp | Annotated tag trỏ tới tag object | Dùng <code>tag^{commit}</code> để peel và xác nhận |
| Tên revision bị hiểu nhầm thành đường dẫn | Revision/pathspec mơ hồ | Dùng ref đầy đủ hoặc dấu <code>--</code> trước pathspec |

## 28. Quy trình chọn revision đúng

Khi cần định vị một commit, có thể làm theo thứ tự:

1. Xác định bạn muốn commit hiện tại, commit theo tên branch/tag hay một tổ tiên của commit.
2. Nếu đã biết OID, dùng OID đầy đủ hoặc mã rút gọn đủ duy nhất.
3. Nếu dùng branch/tag, kiểm tra ref có tồn tại và trỏ tới object loại nào.
4. Nếu đi lùi trong lịch sử, chọn <code>~n</code> cho first-parent chain hoặc <code>^n</code> cho parent cụ thể.
5. Nếu có merge commit, xem đồ thị bằng <code>git log --graph --oneline --decorate --all</code> trước khi chọn parent.
6. Xác minh revision bằng <code>git show</code> hoặc <code>git rev-parse --verify</code>.
7. Chỉ dùng revision đã xác minh trong lệnh thay đổi branch, reset hoặc push.

Ví dụ, muốn tạo branch từ parent thứ hai của merge commit hiện tại:

~~~bash
git show --no-patch --oneline HEAD^2
git branch feature/from-merged-side HEAD^2
~~~

Muốn tạo branch từ commit trước HEAD hai bước theo first parent:

~~~bash
git switch -c feature/previous-point HEAD~2
~~~

Hai ví dụ này chọn hai đường đi khác nhau trong commit graph. Hãy xác nhận bằng <code>git show</code> trước khi tạo branch nếu lịch sử có merge.

## 29. Bài tập thực hành

Tạo repository thử nghiệm hoặc dùng một repository demo có thể thao tác an toàn.

### Bài tập A — Lấy mã hash đầy đủ và rút gọn

Chạy:

~~~bash
git rev-parse --show-object-format
git rev-parse HEAD
git rev-parse --short HEAD
git rev-parse --short=12 HEAD
git log --oneline -5
~~~

Ghi lại sự khác biệt giữa OID đầy đủ và mã rút gọn. Thử tăng số commit hoặc clone repository lớn hơn để quan sát độ dài abbreviation.

### Bài tập B — Đi lùi theo first parent

Chạy:

~~~bash
git log --graph --oneline --decorate -10
git show HEAD~
git show HEAD~2
git show HEAD^^
~~~

Đối chiếu commit mà các biểu thức chọn. Nếu lịch sử hiện tại tuyến tính, <code>HEAD~2</code> và <code>HEAD^^</code> sẽ trỏ tới cùng commit.

### Bài tập C — Phân biệt parent của merge

Trong repository có merge commit, tìm commit merge rồi chạy:

~~~bash
git show --no-patch --format=raw HEAD
git show HEAD^1
git show HEAD^2
git show HEAD~2
~~~

Đọc các dòng parent của merge commit và xác định parent thứ nhất, thứ hai. So sánh với đồ thị:

~~~bash
git log --graph --oneline --decorate --all
~~~

Nếu HEAD không phải merge commit, chuyển tới một merge commit đã có trong lịch sử hoặc tạo merge trong repository lab.

### Bài tập D — Phân giải tên ref

Chạy:

~~~bash
git branch -avv
git tag --list
git show-ref --heads --tags
git rev-parse --verify 'HEAD^{commit}'
git rev-parse --verify 'main^{commit}'
~~~

Thử dùng ref đầy đủ <code>refs/heads/main</code> và so sánh với tên ngắn <code>main</code>.

### Bài tập E — Phân biệt reflog selector

Chạy:

~~~bash
git reflog show HEAD
git show 'HEAD@{1}'
git show HEAD~1
~~~

Giải thích vì sao hai commit có thể khác nhau: một biểu thức chọn trạng thái ref trong reflog, biểu thức kia đi theo parent của commit.

## 30. Checklist trước khi dùng revision trong lệnh quan trọng

- [ ] Đã biết mình đang ở repository nào và branch nào.
- [ ] Đã phân biệt OID đầy đủ với OID rút gọn.
- [ ] Đã dùng Git để xác định abbreviation đủ duy nhất.
- [ ] Đã xác định tên ref là local branch, remote-tracking branch hay tag.
- [ ] Đã fetch nếu cần thông tin mới từ remote.
- [ ] Đã hiểu <code>~n</code> đi theo first parent.
- [ ] Đã hiểu <code>^n</code> chọn parent thứ n.
- [ ] Đã kiểm tra parent graph nếu revision nằm gần merge commit.
- [ ] Đã phân biệt <code>HEAD~n</code> với <code>HEAD@{n}</code>.
- [ ] Đã xác minh revision bằng <code>git show</code> hoặc <code>git rev-parse --verify</code>.
- [ ] Đã dùng <code>--</code> để tách revision khỏi pathspec khi cần.
- [ ] Đã lưu OID đầy đủ trước khi thực hiện thao tác có thể thay đổi lịch sử.

## 31. Những điểm cần ghi nhớ

- Commit được định danh bằng OID; định dạng phổ biến là SHA-1, nhưng repository SHA-256 có OID dài hơn.
- Mã hash rút gọn phải đủ duy nhất trong repository; dùng <code>git rev-parse --short</code> thay vì tự cắt chuỗi.
- Branch, tag và remote-tracking branch là tên tham chiếu tới object.
- <code>HEAD</code> đại diện cho vị trí checkout hiện tại; trong detached HEAD, nó trỏ trực tiếp tới commit.
- <code>HEAD~n</code> đi lùi n lần theo parent thứ nhất.
- <code>HEAD^n</code> chọn parent thứ n của commit; <code>HEAD^</code> tương đương <code>HEAD^1</code>.
- Trong merge commit, <code>HEAD^1</code> và <code>HEAD^2</code> thường trỏ tới hai nhánh cha khác nhau.
- <code>HEAD^0</code> xác nhận chính commit hiện tại; <code>tag^{commit}</code> peel tag tới commit.
- <code>HEAD@{n}</code> là selector của reflog, khác với <code>HEAD~n</code>.
- Dùng <code>git show</code> và <code>git rev-parse --verify</code> để xác nhận revision trước khi thay đổi lịch sử.
- Dùng dấu <code>--</code> để tách revision và pathspec trong các lệnh nhận cả hai loại đối số.

Khi nắm được OID, tên ref và cách đi theo parent, bạn có thể định vị chính xác commit cần xem hoặc thao tác. Hãy đọc đồ thị trước khi chọn parent ở merge commit, dùng abbreviation do Git tạo và xác minh revision trước các lệnh có ảnh hưởng tới branch hoặc lịch sử.

