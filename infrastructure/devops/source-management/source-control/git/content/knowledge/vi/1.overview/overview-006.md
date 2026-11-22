# Kho mã, thư mục làm việc và chỉ mục (staging area)

Git giúp quản lý thay đổi của mã nguồn qua các mốc lịch sử có thể kiểm tra và khôi phục. Để sử dụng Git an toàn, trước hết cần hiểu ba vùng thường xuyên làm việc: **repository (kho Git)**, **working tree (thư mục làm việc)** và **index (chỉ mục, thường được gọi là staging area)**. Ba vùng này liên kết với nhau nhưng có vai trò khác nhau. Khi phân biệt được chúng, bạn sẽ biết một thay đổi đang nằm ở đâu, nội dung nào sẽ được đưa vào commit tiếp theo và cách sửa lại lựa chọn staging khi cần.

Bài này thuộc chương **Tổng quan** của module **SOURCE_CONTROL_GIT**. Module hướng dẫn Git từ working tree, staging area, commit và lịch sử đến branch, merge, rebase, remote và tag; đồng thời rèn cách cộng tác qua nhánh, giải quyết xung đột, truy tìm thay đổi và khôi phục thao tác sai mà vẫn bảo toàn lịch sử quan trọng. Vì vậy, việc nắm rõ repository, working tree và index là nền tảng cho các thao tác Git ở những bài tiếp theo.

## 1. Ba vùng cần phân biệt

### Repository – kho Git

Repository là nơi Git lưu dữ liệu và lịch sử phiên bản của dự án. Trong một repository thông thường, thư mục ẩn <code>.git</code> chứa cơ sở dữ liệu đối tượng, thông tin nhánh, tham chiếu đến commit, cấu hình và các dữ liệu quản lý khác. Git dùng các đối tượng như blob, tree và commit để lưu nội dung tệp, cấu trúc thư mục và lịch sử.

Một commit đại diện cho một snapshot của dự án tại một thời điểm. Commit có thể tham chiếu đến commit cha, thông tin tác giả, thời điểm và thông điệp mô tả. Nhờ các liên kết này, Git tạo thành lịch sử mà bạn có thể xem, so sánh hoặc chuyển về một mốc phù hợp.

Trong giao tiếp hằng ngày, từ “repository” đôi khi được dùng để chỉ cả thư mục dự án đã clone về máy. Về mặt khái niệm, cần phân biệt phần dữ liệu Git quản lý với những tệp đang được checkout ra để làm việc. Một repository bare thường chỉ lưu dữ liệu Git và không có working tree; loại này thường được dùng làm kho trung tâm trên máy chủ.

### Working tree – thư mục làm việc

Working tree là tập hợp tệp và thư mục mà bạn nhìn thấy trên hệ thống tệp để đọc, tạo, sửa hoặc xóa. Đây là nơi bạn viết mã, cập nhật tài liệu, chạy ứng dụng và thực hiện các công việc hằng ngày.

Working tree có thể chứa:

- **Tệp đã được Git theo dõi (tracked):** Git đã biết đường dẫn của tệp thông qua commit hoặc index.
- **Tệp chưa được theo dõi (untracked):** tệp mới xuất hiện trong thư mục dự án nhưng chưa được đưa vào index.
- **Thay đổi chưa staging:** nội dung tệp tracked đã khác phiên bản đang có trong index.
- **Tệp bị xóa hoặc đổi tên:** thao tác trên hệ thống tệp tạo ra khác biệt so với index.

Việc lưu tệp trong trình soạn thảo chỉ làm thay đổi working tree. Git chưa tự động đưa nội dung mới vào commit chỉ vì bạn đã nhấn Save.

### Index – chỉ mục / staging area

Index là vùng trung gian ghi nhận nội dung và đường dẫn sẽ được dùng để tạo commit tiếp theo. Khi nói “stage một tệp”, nghĩa là cập nhật phiên bản của tệp đó vào index. Lệnh thường dùng là <code>git add</code>.

Index không đơn giản là một danh sách tên tệp cần commit. Nó lưu thông tin cần thiết để dựng snapshot tiếp theo, bao gồm đường dẫn, chế độ tệp và định danh đối tượng nội dung. Khi staging một tệp, Git ghi nhận nội dung tương ứng trong cơ sở dữ liệu đối tượng và cập nhật mục trong index.

Ngay sau khi checkout một commit, index thường khớp với snapshot của commit đó. Khi bạn sửa tệp, working tree thay đổi nhưng index vẫn giữ phiên bản đã staging trước đó. Khi chạy <code>git add</code>, Git cập nhật index bằng nội dung hiện tại của tệp. Do đó, nếu tiếp tục sửa tệp sau khi đã staging, phần sửa mới vẫn nằm trong working tree và cần được staging lần nữa nếu muốn đưa vào commit.

Trong một lần merge có xung đột, index còn có thể lưu nhiều phiên bản cho cùng một đường dẫn để Git và người dùng xác định nội dung cần giải quyết. Sau khi chỉnh sửa xong tệp xung đột, chạy <code>git add</code> trên tệp đó để ghi nhận kết quả đã giải quyết vào index.

## 2. Repository, working tree, index và HEAD liên hệ với nhau thế nào?

HEAD cho biết commit hiện tại mà repository đang đứng. Thông thường HEAD tham chiếu đến nhánh hiện tại; trong trạng thái detached HEAD, HEAD tham chiếu trực tiếp đến một commit. Khi checkout hoặc chuyển nhánh, Git dùng commit được chọn để cập nhật working tree và index.

Luồng làm việc cơ bản có thể hình dung như sau:

~~~mermaid
flowchart TD
    H["HEAD: commit hiện tại"] -->|"checkout / switch"| I["Index: snapshot dự kiến cho commit tiếp theo"]
    H -->|"checkout / switch"| W["Working tree: các tệp trên ổ đĩa"]
    W -->|"git add"| I
    I -->|"git commit"| C["Commit mới"]
    C -->|"nhánh hiện tại được cập nhật"| H2["HEAD: commit mới"]
~~~

Ba thao tác chính có ý nghĩa khác nhau:

1. **Sửa tệp:** thay đổi working tree.
2. **Staging bằng <code>git add</code>:** cập nhật index theo nội dung hiện tại của đường dẫn được chọn.
3. **Commit bằng <code>git commit</code>:** tạo commit từ snapshot đang có trong index và cập nhật nhánh hiện tại.

Vì commit được tạo từ index, Git cho phép bạn chọn chính xác phần thay đổi nào thuộc về một commit. Các chỉnh sửa chưa staging vẫn ở working tree và không tự động được đưa vào commit thông thường.

| Vùng | Chứa gì? | Thao tác thường làm thay đổi vùng |
|---|---|---|
| Repository (<code>.git</code>) | Đối tượng Git, commit, nhánh, tham chiếu và cấu hình | <code>git commit</code>, <code>git branch</code>, <code>git fetch</code> và các lệnh quản lý lịch sử |
| Working tree | Tệp dự án đang hiển thị trên ổ đĩa | Trình soạn thảo, công cụ build, <code>git restore</code>, <code>git checkout</code> hoặc <code>git switch</code> |
| Index | Snapshot dự kiến cho commit tiếp theo | <code>git add</code>, <code>git rm</code>, <code>git restore --staged</code> |
| HEAD | Vị trí commit hiện tại | <code>git commit</code>, <code>git switch</code>, <code>git checkout</code>, một số dạng <code>git reset</code> |

Trong thực tế, các lệnh Git có thể tác động đến nhiều vùng cùng lúc. Bảng trên mô tả vai trò chính để bạn định hướng; hãy đọc tài liệu của từng lệnh trước khi dùng các tùy chọn có thể ghi đè nội dung.

## 3. Theo dõi trạng thái bằng git status

<code>git status</code> là lệnh nên chạy thường xuyên, đặc biệt trước khi staging, commit, chuyển nhánh hoặc xử lý xung đột. Lệnh này cho biết nhánh hiện tại và những khác biệt giữa HEAD, index và working tree.

~~~bash
git status
git status --short
~~~

Ở chế độ ngắn, Git thường hiển thị hai ký tự trạng thái trước đường dẫn: <code>XY path</code>.

- Ký tự **X** mô tả trạng thái của đường dẫn trong index so với HEAD.
- Ký tự **Y** mô tả trạng thái của working tree so với index.

Một số trạng thái thường gặp:

| Hiển thị | Ý nghĩa |
|---|---|
| <code>?? notes.txt</code> | Tệp chưa được theo dõi |
| <code> M README.md</code> | Tệp tracked đã sửa trong working tree, chưa staging |
| <code>M  README.md</code> | Thay đổi đã staging trong index |
| <code>MM README.md</code> | Tệp đã staging, sau đó tiếp tục được sửa trong working tree |
| <code>A  new-file.txt</code> | Tệp mới đã được staging |
| <code>D  old-file.txt</code> | Việc xóa tệp đã được staging |
| <code> D old-file.txt</code> | Tệp tracked đã bị xóa trong working tree nhưng việc xóa chưa staging |
| <code>UU src/App.java</code> | Tệp đang ở trạng thái xung đột cần giải quyết |

Khoảng trắng ở một vị trí cũng có ý nghĩa: ví dụ <code> M</code> có nghĩa là cột index không có thay đổi, còn cột working tree có thay đổi. Đừng chỉ nhìn chữ <code>M</code>; hãy xác định nó nằm ở cột nào.

<code>git status</code> có thể báo thêm rằng nhánh hiện tại đang ahead hoặc behind so với nhánh upstream. Đây là thông tin về quan hệ giữa lịch sử local và remote, không phải trạng thái staging của từng tệp.

## 4. Staging và kiểm tra nội dung sẽ commit

### Thêm thay đổi vào index

Một số lệnh staging phổ biến:

~~~bash
# Stage một tệp cụ thể
git add README.md

# Stage nhiều đường dẫn cụ thể
git add src/App.java docs/setup.md

# Stage toàn bộ thay đổi trong working tree
git add -A

# Stage thay đổi của các tệp đã được theo dõi
git add -u

# Chọn từng phần thay đổi để staging
git add -p
~~~

<code>git add -A</code> cập nhật index với các tệp mới, tệp đã sửa và tệp đã xóa trong phạm vi working tree. <code>git add -u</code> chỉ cập nhật các đường dẫn đã được theo dõi, vì vậy không thêm tệp untracked mới. <code>git add .</code> áp dụng cho thư mục hiện tại và các thư mục con; nếu đang đứng trong một thư mục con, phạm vi có thể hẹp hơn toàn bộ repository.

Với dự án có nhiều thay đổi độc lập, nên staging theo đường dẫn hoặc theo từng phần bằng <code>git add -p</code>. Cách này giúp một commit chỉ chứa những thay đổi có cùng mục đích, làm lịch sử dễ đọc và dễ review hơn.

### Xem khác biệt trước khi commit

Git có các lệnh diff để so sánh từng cặp vùng:

~~~bash
# So sánh working tree với index: phần đã sửa nhưng chưa staging
git diff

# So sánh index với HEAD: phần sẽ nằm trong commit tiếp theo
git diff --staged

# Cú pháp tương đương với --staged
git diff --cached

# So sánh working tree với HEAD, gồm cả thay đổi staged và unstaged
git diff HEAD
~~~

Hãy nhớ:

- <code>git diff</code> giúp kiểm tra phần chưa staging.
- <code>git diff --staged</code> giúp kiểm tra phần đã staging và dự kiến được commit.
- <code>git diff HEAD</code> cho góc nhìn tổng thể về khác biệt hiện tại so với commit đang checkout.

Các lệnh diff thông thường không hiển thị nội dung của tệp untracked vì tệp đó chưa có trong index. Muốn đưa tệp mới vào luồng so sánh staging, hãy chạy <code>git add</code> trước; việc này chỉ cập nhật index, chưa tạo commit.

### Ví dụ: staging không đồng nghĩa với commit

Giả sử bạn đang làm việc với <code>README.md</code>:

1. Mở tệp và thêm một đoạn hướng dẫn. Lúc này working tree thay đổi, index chưa đổi.
2. Chạy <code>git status --short</code>; bạn có thể thấy <code> M README.md</code>.
3. Chạy <code>git diff</code> để xem nội dung mới.
4. Chạy <code>git add README.md</code>; nội dung hiện tại được đưa vào index.
5. Chạy <code>git status --short</code>; trạng thái chuyển thành <code>M  README.md</code>.
6. Chạy <code>git diff --staged</code> để kiểm tra chính xác nội dung đã chọn.
7. Chạy <code>git commit -m "docs: update README"</code> để tạo commit từ index.

Nếu sau bước 4 bạn tiếp tục sửa <code>README.md</code>, Git sẽ có một phiên bản trong index và một phiên bản mới hơn trong working tree. <code>git status --short</code> thường hiển thị <code>MM README.md</code>. Lần commit tiếp theo chỉ chứa phiên bản đã staging ở bước 4; phần sửa sau đó vẫn chưa được commit cho đến khi bạn staging lại.

## 5. Bỏ staging và khôi phục thay đổi

Đôi khi bạn staging nhầm tệp hoặc muốn tách một thay đổi thành nhiều commit. Có thể cập nhật lại index mà không làm mất nội dung đang có trong working tree.

~~~bash
# Bỏ staging một tệp, giữ nguyên nội dung trong working tree
git restore --staged README.md

# Bỏ staging tất cả đường dẫn
git restore --staged .

# Bỏ thay đổi chưa staging của một tệp, khôi phục từ index
git restore README.md
~~~

Hai lệnh <code>git restore</code> trên giải quyết hai việc khác nhau:

- <code>git restore --staged &lt;path&gt;</code> cập nhật index từ HEAD cho đường dẫn được chọn. Nội dung trong working tree được giữ lại. Với một tệp mới chưa có trong HEAD, thao tác này gỡ tệp khỏi index để nó trở lại trạng thái untracked.
- <code>git restore &lt;path&gt;</code> cập nhật working tree từ index. Các chỉnh sửa chưa staging của đường dẫn đó sẽ bị loại bỏ.

Vì vậy, trước khi chạy lệnh restore, hãy kiểm tra <code>git status</code> và <code>git diff</code>. Nếu không chắc nội dung nào sẽ bị thay thế, hãy sao lưu hoặc lưu lại phần thay đổi cần giữ. Không nên chạy <code>git restore</code> hàng loạt khi chưa xác định rõ phạm vi.

Một số lệnh liên quan đến việc xóa khỏi theo dõi:

~~~bash
# Xóa tệp khỏi working tree và staging việc xóa
git rm path/to/file.txt

# Gỡ tệp khỏi index nhưng giữ tệp trên ổ đĩa
git rm --cached path/to/file.txt
~~~

<code>git rm --cached</code> thường hữu ích khi bạn lỡ đưa một tệp vào Git và muốn ngừng theo dõi tệp đó. Nếu tệp cần được bỏ qua ở các lần sau, hãy thêm quy tắc phù hợp vào <code>.gitignore</code>. Quy tắc <code>.gitignore</code> chủ yếu áp dụng cho tệp chưa được theo dõi; nó không tự động ngừng theo dõi một tệp đã có trong lịch sử. Với tệp đã tracked, cần gỡ khỏi index bằng thao tác phù hợp.

## 6. Tệp mới, tệp bị xóa, đổi tên và xung đột

### Tệp mới và tệp bị bỏ qua

Khi tạo một tệp mới trong working tree, <code>git status</code> báo tệp đó là untracked. Git chưa đưa nội dung tệp vào commit. Chạy <code>git add &lt;path&gt;</code> để bắt đầu theo dõi tệp và đưa phiên bản hiện tại vào index.

Nếu không muốn Git đề xuất một số tệp, chẳng hạn tệp build, log hoặc cấu hình riêng của máy phát triển, có thể khai báo mẫu trong <code>.gitignore</code>. Ví dụ:

~~~gitignore
build/
*.log
.env.local
~~~

Các mẫu trên lần lượt bỏ qua thư mục <code>build</code>, tệp có phần mở rộng <code>.log</code> và tệp <code>.env.local</code>. Hãy kiểm tra quy tắc ignore để tránh vô tình bỏ qua tệp nguồn cần đưa vào repository. Tệp đã được theo dõi vẫn tiếp tục được theo dõi dù sau đó khớp một mẫu trong <code>.gitignore</code>.

### Xóa và đổi tên

Nếu xóa một tệp tracked trực tiếp trong trình quản lý tệp, working tree ghi nhận sự vắng mặt của tệp nhưng index chưa được cập nhật. <code>git status</code> sẽ báo trạng thái xóa chưa staging. Chạy <code>git add -A</code> hoặc <code>git rm &lt;path&gt;</code> để staging việc xóa.

Khi đổi tên tệp, Git thường biểu diễn thay đổi ở index bằng việc bỏ đường dẫn cũ và thêm đường dẫn mới. Git không lưu thao tác rename như một loại đối tượng độc lập; khi hiển thị lịch sử hoặc diff, Git nhận diện rename dựa trên mức độ tương đồng của nội dung. Vì vậy, tên tệp hiển thị trong diff có thể phụ thuộc vào khả năng phát hiện tương đồng.

### Xung đột merge

Khi merge hoặc rebase gặp xung đột, một đường dẫn có thể có nhiều phiên bản trong index, tương ứng với base, phía hiện tại và phía được đưa vào. <code>git status</code> đánh dấu đường dẫn đó là unmerged, ví dụ <code>UU</code>.

Quy trình xử lý thường gồm:

1. Chạy <code>git status</code> để xác định các tệp xung đột.
2. Mở từng tệp và đọc các dấu phân cách xung đột do Git chèn vào.
3. Chỉnh sửa thành nội dung cuối cùng mong muốn và xóa các dấu phân cách.
4. Chạy <code>git add &lt;path&gt;</code> để ghi nhận kết quả đã giải quyết vào index.
5. Chạy <code>git status</code> và <code>git diff --staged</code> để kiểm tra trước khi hoàn tất merge hoặc rebase theo hướng dẫn của Git.

Trong lúc tệp còn xung đột, không nên xem index như một snapshot hoàn chỉnh để commit thông thường. Việc staging tệp sau khi sửa là tín hiệu cho Git biết bạn đã chọn nội dung giải quyết xung đột.

## 7. Quy trình làm việc an toàn trước mỗi commit

Một quy trình ngắn gọn nhưng hiệu quả:

~~~bash
# 1. Kiểm tra trạng thái hiện tại
git status

# 2. Xem phần chưa staging
git diff

# 3. Chọn thay đổi cần đưa vào commit
git add -p
# Hoặc dùng git add <path> nếu muốn chọn cả tệp

# 4. Kiểm tra snapshot dự kiến
git status
git diff --staged

# 5. Tạo commit
git commit -m "feat: describe the change"

# 6. Xác nhận trạng thái sau commit
git status
~~~

Thông điệp commit nên mô tả mục đích thay đổi bằng câu ngắn, rõ ràng. Trước khi commit, hãy tự trả lời ba câu hỏi:

- Các tệp đã staging có đúng thuộc phạm vi công việc này không?
- Nội dung trong <code>git diff --staged</code> có chứa bí mật, tệp build hoặc thay đổi ngoài ý muốn không?
- Có thay đổi nào còn nằm trong working tree mà bạn định đưa vào commit nhưng chưa staging không?

Không nhất thiết phải staging toàn bộ dự án trong mọi lần commit. Một commit nhỏ, tập trung thường dễ đọc, review, revert và truy tìm nguyên nhân hơn.

## 8. Những hiểu lầm thường gặp

| Hiểu lầm | Cách hiểu chính xác |
|---|---|
| Lưu tệp trong editor là đã commit | Lưu tệp chỉ cập nhật working tree. Cần staging rồi commit để tạo mốc lịch sử. |
| <code>git add</code> tạo commit | <code>git add</code> chỉ cập nhật index; <code>git commit</code> mới tạo commit. |
| Đã staging thì mọi sửa đổi tiếp theo cũng tự được staging | Index giữ phiên bản tại thời điểm staging. Sửa tệp sau đó tạo khác biệt mới trong working tree. |
| <code>git commit</code> luôn lấy mọi thay đổi trên ổ đĩa | Commit thông thường tạo snapshot từ index. Thay đổi chưa staging không được đưa vào commit. |
| <code>.gitignore</code> sẽ bỏ theo dõi mọi tệp khớp mẫu | <code>.gitignore</code> không tự bỏ theo dõi tệp đã tracked. |
| Git lưu thao tác đổi tên như một loại đối tượng riêng | Git chủ yếu lưu snapshot và suy luận rename khi hiển thị diff hoặc lịch sử. |
| Index chỉ là danh sách tệp | Index chứa thông tin để dựng snapshot, bao gồm đường dẫn, chế độ tệp và định danh nội dung; khi có xung đột, một đường dẫn còn có thể có nhiều stage. |

Không chỉnh sửa trực tiếp các tệp nội bộ trong <code>.git</code> hoặc index để thay đổi trạng thái repository. Hãy dùng các lệnh Git tương ứng để Git cập nhật dữ liệu nhất quán.

## 9. Bài tập tự kiểm tra

Thực hành trong một repository thử nghiệm để không ảnh hưởng đến công việc đang làm:

1. Tạo một tệp mới <code>notes.txt</code>, chạy <code>git status</code>. Vì sao tệp được báo là untracked?
2. Chạy <code>git add notes.txt</code>, rồi chạy <code>git status</code> và <code>git diff --staged</code>. Trạng thái và nội dung hiển thị thay đổi thế nào?
3. Sửa <code>notes.txt</code> thêm một dòng nhưng không chạy <code>git add</code>. Vì sao trạng thái có thể là <code>MM</code>?
4. Chạy <code>git restore --staged notes.txt</code>. Nội dung tệp trên ổ đĩa có bị mất không? Hãy kiểm tra bằng <code>git diff</code>.
5. Stage lại tệp, tạo commit, sau đó chạy <code>git status</code>. Vì sao index thường trở lại trạng thái khớp với HEAD?
6. Thêm một tệp log vào <code>.gitignore</code>. Thử với một tệp log mới và một tệp log đã tracked để quan sát sự khác nhau.

Nếu có thể giải thích được tệp nào đang ở working tree, phiên bản nào đang nằm trong index và commit tiếp theo sẽ lấy nội dung từ đâu, bạn đã nắm được nền tảng quan trọng nhất của staging area. Từ nền tảng này, các thao tác tạo commit, chuyển nhánh, merge, rebase và xử lý xung đột sẽ dễ dự đoán hơn.
