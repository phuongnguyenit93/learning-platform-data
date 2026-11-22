# Giới hạn của assume-unchanged và skip-worktree

Git có hai cờ trong index thường được nhắc đến khi muốn giảm việc kiểm tra tệp hoặc giữ một số tệp ngoài working tree: `assume-unchanged` và `skip-worktree`. Cả hai đều tác động đến cách Git xử lý một đường dẫn trong repository local, nhưng chúng có mục đích khác nhau và đều có giới hạn rõ ràng.

`assume-unchanged` là lời hứa của người dùng rằng tệp trong working tree không thay đổi, để Git có thể bỏ qua một số lần kiểm tra trạng thái tệp. `skip-worktree` hướng dẫn Git tránh ghi tệp đó ra working tree khi có thể và được dùng chủ yếu để triển khai sparse checkout. Không cờ nào biến tệp tracked thành ignored, thay đổi lịch sử commit hoặc tạo chính sách chia sẻ cho cả nhóm.

Bài học thuộc chương **Tệp và chỉ mục** của module `SOURCE_CONTROL_GIT`. Module hướng dẫn working tree, staging area, commit, lịch sử, branch, merge, rebase, remote và tag; hiểu giới hạn của hai cờ index giúp tránh bỏ sót thay đổi hoặc làm mất dữ liệu local.

## 1. Hai cờ này nằm ở đâu?

Git quản lý nội dung và trạng thái làm việc qua nhiều lớp:

- **Working tree:** các tệp và thư mục bạn đang nhìn thấy, chỉnh sửa.
- **Index (staging area):** bản nội dung và metadata mà Git sẽ dùng cho commit tiếp theo.
- **Repository object database:** commit, tree, blob và các object lịch sử.
- **Index flags:** một số bit metadata gắn với mục trong index, ảnh hưởng đến cách Git kiểm tra hoặc materialize đường dẫn.

`assume-unchanged` và `skip-worktree` là các bit metadata cục bộ trong index. Chúng không được ghi vào commit tree, không được push lên remote và không tự truyền sang clone của người khác.

| Đặc điểm | assume-unchanged | skip-worktree |
| --- | --- | --- |
| Mục đích chính | Báo Git giả định tệp không thay đổi để có thể giảm kiểm tra stat | Báo Git tránh ghi tệp ra working tree khi có thể |
| Hành vi khi tệp vắng mặt | Không có ý nghĩa bỏ qua deletion một cách đáng tin cậy | Tệp vắng mặt được xem là có chủ đích trong các tình huống phù hợp |
| Trường hợp sử dụng chính | Tối ưu kiểm tra ở repository local trong tình huống hẹp | Sparse checkout và working tree chọn lọc |
| Thay thế .gitignore? | Không | Không |
| Thay đổi commit hoặc remote? | Không | Không |
| Là cơ chế bảo vệ thay đổi local? | Không | Không |

Cả hai cờ đều có thể gây nhầm lẫn nếu bạn xem chúng như cách “giấu” một tệp đã tracked khỏi Git.

## 2. assume-unchanged: lời hứa về trạng thái tệp

Bật cờ cho một đường dẫn:

~~~bash
git update-index --assume-unchanged -- path/to/file
~~~

Lệnh này đặt bit assume-unchanged trên mục tương ứng trong index. Git có thể bỏ qua một số lần kiểm tra metadata filesystem (ví dụ stat) cho tệp đó với giả định rằng nội dung trong working tree không thay đổi so với index.

Cơ chế này xuất phát từ nhu cầu tối ưu ở những filesystem hoặc repository có nhiều tệp, nơi việc kiểm tra metadata từng tệp có chi phí đáng kể. Nó là một lời hứa từ người dùng để Git có thể giảm công việc kiểm tra.

Tắt cờ:

~~~bash
git update-index --no-assume-unchanged -- path/to/file
~~~

Sau khi tắt, Git có thể kiểm tra lại tệp theo quy trình thông thường. Nếu tệp đã thay đổi, trạng thái modified có thể xuất hiện.

### Điều gì xảy ra nếu bạn vẫn sửa tệp?

Giả sử bạn bật cờ cho `config/local-settings.json` rồi sửa tệp đó. Vì Git được yêu cầu giả định tệp không đổi, `git status` hoặc các lệnh dựa vào việc kiểm tra working tree có thể không phát hiện thay đổi như bạn mong đợi.

Đây là lý do không nên dùng cờ này để giữ một cấu hình local riêng trong khi vẫn thường xuyên chỉnh sửa tệp. Khi cần thay đổi tệp, hãy tắt cờ trước, sau đó kiểm tra:

~~~bash
git update-index --no-assume-unchanged -- config/local-settings.json
git status --short
git diff -- config/local-settings.json
~~~

Nếu thay đổi đó cần commit, stage sau khi đã kiểm tra nội dung. Nếu không muốn chia sẻ thay đổi local, hãy chọn cách tổ chức cấu hình riêng phù hợp hơn, ví dụ tách file local khỏi file template hoặc đưa file không tracked vào ignore cá nhân.

### assume-unchanged không có nghĩa là ignore

Một tệp đã được Git theo dõi vẫn là tracked file. Bit assume-unchanged không xóa tệp khỏi index, không ngăn commit nếu nội dung được stage và không thay thế quy tắc ignore.

Nếu mục tiêu là ngừng theo dõi một tệp nhưng vẫn giữ nó trên đĩa, cần thao tác với index, ví dụ `git rm --cached`, sau khi cân nhắc ảnh hưởng đến nhóm. Nếu mục tiêu là bỏ qua tệp mới chưa tracked, dùng `.gitignore` hoặc `.git/info/exclude`.

## 3. skip-worktree: Git tránh cập nhật đường dẫn trong working tree

Bật cờ cho một đường dẫn:

~~~bash
git update-index --skip-worktree -- path/to/file
~~~

`skip-worktree` hướng dẫn Git tránh ghi nội dung của đường dẫn đó ra working tree khi có thể. Khi một đường dẫn có cờ này không hiện diện trong working tree, Git có thể xem sự vắng mặt đó là có chủ đích thay vì báo như một tệp bị xóa thông thường.

Tắt cờ:

~~~bash
git update-index --no-skip-worktree -- path/to/file
~~~

Cờ này được Git dùng làm nền tảng cho sparse checkout: các tệp ngoài tập đường dẫn được chọn có thể được đánh dấu skip-worktree để Git không materialize chúng trong working tree.

### skip-worktree không phải cách ẩn sửa đổi local

Một số người đặt cờ này lên tệp cấu hình đã tracked để chỉnh giá trị riêng mà không muốn Git hiển thị thay đổi. Đây là cách dùng dễ gây bất ngờ:

- Git có thể không cập nhật tệp trong working tree khi branch hoặc nội dung index thay đổi.
- Khi tệp không tồn tại, Git có thể xem đó là trạng thái được chủ ý bỏ khỏi working tree.
- Nếu upstream thay đổi cùng đường dẫn, các thao tác merge, checkout hoặc cập nhật có thể làm cờ thay đổi hoặc buộc Git xử lý lại đường dẫn.
- Nếu quên cờ đang bật, bạn có thể không nhận ra tệp local đang cũ so với nội dung trong commit.

Không dựa vào skip-worktree để bảo vệ dữ liệu local hoặc che giấu một thay đổi cần được quản lý. Trước khi cập nhật branch, merge hoặc pull, kiểm tra những đường dẫn đang có cờ và bảo toàn các thay đổi local cần giữ.

## 4. Kiểm tra cờ đang bật

Git cung cấp `git ls-files` để xem các mục trong index.

### Kiểm tra assume-unchanged

Dùng:

~~~bash
git ls-files -v -- path/to/file
~~~

Với tùy chọn `-v`, Git hiển thị tag trạng thái trước đường dẫn; chữ tag viết thường cho biết mục được đánh dấu assume-unchanged. Ví dụ một đường dẫn có thể hiện là:

~~~text
h config/local-settings.json
~~~

Chữ thường là dấu hiệu cần kiểm tra. Để liệt kê toàn bộ mục có tag viết thường trên shell POSIX:

~~~bash
git ls-files -v | grep '^[a-z]'
~~~

Trên PowerShell:

~~~powershell
git ls-files -v | Select-String '^[a-z]'
~~~

### Kiểm tra skip-worktree

Dùng:

~~~bash
git ls-files -t -- path/to/file
~~~

Tùy chọn `-t` hiển thị tag trạng thái. Tag `S` biểu thị mục có skip-worktree. Để lọc danh sách trên shell POSIX:

~~~bash
git ls-files -t | grep '^S '
~~~

Trên PowerShell:

~~~powershell
git ls-files -t | Select-String '^S '
~~~

Nếu không có kết quả cho đường dẫn, có thể cờ tương ứng chưa được bật hoặc đường dẫn không có trong index. Hãy kiểm tra chính xác đường dẫn và trạng thái tracked trước khi kết luận.

## 5. Bật và tắt cờ an toàn

Các lệnh update-index tác động đến index local. Trước khi thay đổi, hãy ghi nhận trạng thái hiện tại và kiểm tra nội dung tệp.

Ví dụ kiểm tra một tệp:

~~~bash
git status --short
git ls-files -v -- config/local-settings.json
git ls-files -t -- config/local-settings.json
~~~

Bật assume-unchanged khi bạn thực sự hiểu Git sẽ bỏ qua một số lần kiểm tra:

~~~bash
git update-index --assume-unchanged -- config/local-settings.json
~~~

Bật skip-worktree trong trường hợp cần thiết:

~~~bash
git update-index --skip-worktree -- config/large-local-fixture.json
~~~

Bỏ cờ trước khi làm việc với tệp:

~~~bash
git update-index --no-assume-unchanged -- config/local-settings.json
git update-index --no-skip-worktree -- config/large-local-fixture.json
~~~

Sau khi bỏ cờ, kiểm tra trạng thái và diff:

~~~bash
git status --short
git diff -- config/local-settings.json
git diff --cached -- config/local-settings.json
~~~

Nếu tệp bị thiếu hoặc có thay đổi local, không vội chạy lệnh restore/checkout có thể ghi đè dữ liệu. Hãy sao lưu bản local cần giữ, rồi quyết định nội dung nào nên nằm trong working tree, index hoặc commit.

## 6. Các cờ không được chia sẻ qua commit hoặc push

Giả sử bạn bật assume-unchanged cho `config/app.yml` và commit các thay đổi khác. Người khác clone repository sẽ không tự nhận bit đó. Họ có index riêng và Git kiểm tra tệp theo trạng thái local của họ.

Tương tự, skip-worktree được lưu trong index của bản làm việc hiện tại. Nó không phải một thuộc tính trong commit tree như executable bit hoặc symlink mode. Push commit không mang cờ này sang remote.

Điều đó dẫn đến ba hệ quả:

1. Hai thành viên có thể có trạng thái cờ khác nhau cho cùng một đường dẫn.
2. Re-clone hoặc tạo một working tree mới có thể không giữ các cờ đã đặt thủ công.
3. Cờ không thể được dùng làm chính sách nhóm để bỏ qua một file hoặc để đồng bộ cấu hình local.

Nếu cả nhóm cần bỏ qua một loại file chưa tracked, hãy commit `.gitignore`. Nếu chỉ một người muốn ignore file local, cân nhắc `.git/info/exclude` hoặc `core.excludesFile`. Nếu nhóm cần checkout một phần repository, dùng sparse checkout theo quy trình được hỗ trợ.

## 7. Quan hệ giữa skip-worktree và sparse checkout

Sparse checkout cho phép chọn những đường dẫn được materialize trong working tree. Git dùng skip-worktree để đánh dấu các mục nằm ngoài tập đường dẫn được chọn.

Ví dụ chỉ checkout hai thư mục trong monorepo:

~~~bash
git sparse-checkout init --cone
git sparse-checkout set services/billing libraries/common
git sparse-checkout list
~~~

Git quản lý các bit skip-worktree theo tập pattern sparse checkout. Khi thay đổi phạm vi:

~~~bash
git sparse-checkout add docs/api
~~~

Git có thể materialize thêm các tệp thuộc thư mục mới. Khi tắt sparse checkout:

~~~bash
git sparse-checkout disable
~~~

Git cố gắng đưa các tệp tracked trở lại working tree; nếu repository là partial clone, quá trình này có thể cần tải thêm blob.

### Không nên chỉnh bit thủ công trong vùng sparse

Nếu sparse checkout đang bật, tránh tự đặt hoặc xóa skip-worktree cho các đường dẫn do sparse rules quản lý. Thao tác thủ công có thể khiến trạng thái index không khớp với cấu hình sparse checkout. Lệnh `git sparse-checkout reapply` có thể áp dụng lại pattern và điều chỉnh working tree/index theo cấu hình.

Kiểm tra trạng thái sparse checkout:

~~~bash
git sparse-checkout list
git status --short
git ls-files -t
~~~

Hãy dùng `git sparse-checkout set`, `add`, `reapply` và `disable` để quản lý phạm vi checkout thay vì xem skip-worktree như một công cụ độc lập để ẩn file.

## 8. Những giới hạn khi branch hoặc nội dung upstream thay đổi

Cả hai cờ đều không phải hợp đồng rằng Git sẽ luôn bỏ qua đường dẫn trong mọi thao tác. Các lệnh Git có thể kiểm tra lại, cập nhật hoặc thay đổi bit khi cần để bảo đảm index và working tree nhất quán.

Ví dụ, bạn đánh dấu một tệp cấu hình bằng skip-worktree rồi fetch branch mới có thay đổi cho chính tệp đó. Khi checkout, merge hoặc rebase, Git có thể cần xử lý khác với kỳ vọng ban đầu; có thể phát sinh xung đột hoặc cờ bị bỏ để Git có thể cập nhật tệp.

Với assume-unchanged, nếu tệp thực sự thay đổi nhưng Git đang dựa trên lời hứa không đổi, trạng thái có thể bị bỏ sót cho đến khi bạn bỏ cờ và Git kiểm tra lại.

Trước các thao tác lớn như merge, rebase, switch branch hoặc pull, nên kiểm tra và bỏ những cờ không còn cần thiết. Đừng dùng chúng để che trạng thái local trong thời gian dài.

## 9. Lựa chọn thay thế đúng mục đích

Hãy chọn công cụ theo vấn đề bạn cần giải quyết:

| Nhu cầu | Cách phù hợp | Vì sao |
| --- | --- | --- |
| Bỏ qua build output hoặc cache chưa tracked | `.gitignore` | Quy tắc chia sẻ cùng repository |
| Ignore file local chưa tracked chỉ trên máy mình | `.git/info/exclude` hoặc `core.excludesFile` | Không thay đổi quy tắc của nhóm |
| Tách cấu hình môi trường riêng khỏi file dùng chung | File template + file local ignored, biến môi trường hoặc config ngoài repository | Tránh sửa một tệp tracked rồi cố giấu thay đổi |
| Chỉ checkout vài thư mục trong monorepo | `git sparse-checkout` | Git quản lý working tree chọn lọc và skip-worktree |
| Tối ưu kiểm tra stat trong trường hợp đặc biệt | `assume-unchanged` | Chỉ dùng khi chấp nhận lời hứa tệp không thay đổi |
| Giữ file tracked khỏi working tree theo sparse rules | `skip-worktree` thông qua sparse checkout | Đúng cơ chế Git dùng cho sparse working tree |

### Ví dụ: cấu hình local riêng

Thay vì chỉnh `config/app.yml` đã tracked rồi bật assume-unchanged, có thể thiết kế:

~~~text
config/
  app.example.yml
  app.local.yml
~~~

Commit `app.example.yml`, ignore `app.local.yml` và để ứng dụng nạp file local nếu tồn tại. Hoặc giữ file cấu hình dùng chung nhưng đọc giá trị riêng từ environment variables.

Cách này làm rõ đâu là cấu hình nhóm quản lý, đâu là cấu hình cá nhân; Git không phải đoán xem một tệp tracked có nên được kiểm tra hay không.

## 10. Quy trình chẩn đoán khi Git không thấy thay đổi

Nếu bạn sửa một tệp tracked nhưng `git status` không báo modified, đừng lập tức kết luận Git bị lỗi. Kiểm tra các cờ:

~~~bash
git ls-files -v -- path/to/file
git ls-files -t -- path/to/file
~~~

Nếu phát hiện assume-unchanged, bỏ cờ:

~~~bash
git update-index --no-assume-unchanged -- path/to/file
~~~

Nếu phát hiện skip-worktree, bỏ cờ khi bạn chủ ý muốn tệp trở lại phạm vi kiểm tra/checkout:

~~~bash
git update-index --no-skip-worktree -- path/to/file
~~~

Sau đó kiểm tra:

~~~bash
git status --short
git diff -- path/to/file
git diff --cached -- path/to/file
~~~

Nếu tệp không xuất hiện trong index, kiểm tra lại tên và đường dẫn bằng:

~~~bash
git ls-files -- path/to/file
~~~

Nếu tệp không tracked, kiểm tra quy tắc ignore:

~~~bash
git check-ignore -v -- path/to/file
~~~

Nếu file bị ignore nhưng cần thêm vào Git, hãy cân nhắc lý do ignore trước; chỉ khi chắc chắn muốn theo dõi mới dùng:

~~~bash
git add -f -- path/to/file
~~~

`git add -f` ép thêm một đường dẫn bị ignore vào index. Nó không phải cách xử lý cho assume-unchanged hoặc skip-worktree.

## 11. Bảng so sánh hành vi và rủi ro

| Tình huống | assume-unchanged | skip-worktree |
| --- | --- | --- |
| Tệp tracked bị sửa local | Git có thể không phát hiện vì bỏ qua một số kiểm tra | Git có thể xử lý đặc biệt; không đảm bảo thay đổi local được giữ kín |
| Tệp vắng khỏi working tree | Không phải mục đích chính; có thể được xem là deletion khi kiểm tra lại | Sự vắng mặt thường được xem là có chủ đích |
| Checkout branch mới | Cờ không bảo đảm giữ nguyên tệp hoặc tránh xung đột | Git cố tránh ghi tệp khi có thể; thay đổi upstream có thể làm Git phải xử lý lại |
| Commit | Cờ không tự ngăn nội dung được stage và commit | Cờ không tự ngăn nội dung được stage và commit |
| Clone khác | Không được truyền sang | Không được truyền sang |
| Dùng cho sparse checkout | Không | Có, đây là một ứng dụng chính |
| Dùng để ignore file mới | Không | Không |

Cần nhớ: index flag chỉ ảnh hưởng hành vi Git ở một working tree cụ thể. Nó không thay thế kiểm soát phiên bản, ignore rules hay quản lý cấu hình.

## 12. Những sai lầm thường gặp

- **Dùng assume-unchanged để giấu file cấu hình local:** Git có thể không phát hiện khi file đổi và bạn quên bỏ cờ trước commit.
- **Dùng skip-worktree như .gitignore:** file vẫn tracked và cờ không tạo quy tắc ignore.
- **Cho rằng cờ được chia sẻ với đồng đội:** cờ nằm trong index local, không nằm trong commit.
- **Cho rằng cờ sẽ tồn tại mãi qua mọi thao tác:** Git có thể kiểm tra lại hoặc điều chỉnh cờ khi checkout/merge cần thiết.
- **Tự sửa skip-worktree trong sparse checkout:** có thể làm trạng thái index lệch khỏi pattern sparse.
- **Không kiểm tra cờ khi status không thấy thay đổi:** có thể mất thời gian tìm sai nguyên nhân.
- **Chạy restore hoặc checkout ngay khi bỏ cờ:** có nguy cơ ghi đè bản local cần giữ; hãy sao lưu và review trước.
- **Nhầm index flag với file mode:** executable bit, symlink mode và skip-worktree/assume-unchanged có ý nghĩa khác nhau.

## 13. Sơ đồ lựa chọn

~~~mermaid
flowchart TD
    A[Muốn thay đổi cách Git xử lý một tệp tracked] --> B{Mục tiêu là gì?}
    B -- Bỏ qua file chưa tracked --> C[.gitignore hoặc info/exclude]
    B -- Chỉ checkout một phần repository --> D[git sparse-checkout]
    B -- Tách cấu hình local --> E[File template, config local hoặc environment]
    B -- Giảm stat check trong trường hợp hẹp --> F[assume-unchanged]
    D --> G[Git quản lý skip-worktree]
    F --> H[Theo dõi cờ và bỏ cờ trước khi sửa]
    C --> I[Kiểm tra status và ignore rules]
    E --> I
    G --> I
    H --> I
~~~

Trước khi bật hoặc tắt cờ, hãy tự xác nhận:

1. Tệp có đang được tracked và có trong index không?
2. Tôi cần tối ưu stat check hay cần giới hạn working tree?
3. Có sparse checkout đang quản lý skip-worktree không?
4. Tôi đã sao lưu thay đổi local trước khi bỏ cờ hoặc checkout chưa?
5. Tôi hiểu cờ không được commit/push và không áp dụng cho đồng đội chưa?
6. Sau khi thay đổi cờ, tôi đã kiểm tra lại status, working tree và staged diff chưa?

`assume-unchanged` và `skip-worktree` là hai chỉ dẫn ở mức index với mục đích khác nhau. Dùng assume-unchanged chỉ khi thực sự muốn Git giảm kiểm tra tệp mà bạn cam kết không sửa; dùng skip-worktree trong bối cảnh working tree chọn lọc, tốt nhất thông qua sparse checkout. Khi mục tiêu là ignore, tách cấu hình local hoặc quản lý generated files, hãy dùng cơ chế dành riêng cho mục tiêu đó.

## Tài liệu tham khảo

- [Git documentation: git-update-index](https://git-scm.com/docs/git-update-index) — mô tả assume-unchanged, skip-worktree và các tùy chọn cập nhật index.
- [Git documentation: git-ls-files](https://git-scm.com/docs/git-ls-files) — hiển thị tag trạng thái index bằng `-t` và `-v`.
- [Git documentation: git-sparse-checkout](https://git-scm.com/docs/git-sparse-checkout) — quản lý sparse working tree và skip-worktree.
- [Git documentation: gitignore](https://git-scm.com/docs/gitignore) — phân biệt ignore rules với trạng thái tracked/index.
- [Git FAQ: assume-unchanged and skip-worktree](https://git-scm.com/docs/git-update-index#_using_assume_unchanged_bit) — ngữ nghĩa và giới hạn của các index bit.
