# Chọn commit sang nhánh khác bằng `git cherry-pick`

Trong quá trình phát triển, đôi khi một commit đã hoàn thành trên nhánh này nhưng cần xuất hiện trên một nhánh khác. Ví dụ, nhóm đã sửa lỗi bảo mật trên `main` nhưng nhánh bảo trì `release/2.4` cũng cần bản sửa đó; hoặc một tính năng có commit độc lập cần được đưa sang nhánh thử nghiệm. Ta có thể dùng `git cherry-pick` để chọn commit cụ thể và áp dụng thay đổi của nó lên nhánh hiện tại.

`git cherry-pick` tạo commit mới trên nhánh đích dựa trên thay đổi mà commit nguồn giới thiệu. Nó giúp chuyển một phần công việc mà không cần merge toàn bộ nhánh nguồn. Vì commit mới có parent và mã định danh khác commit gốc, cherry-pick là thao tác áp dụng thay đổi có chọn lọc, không phải di chuyển cùng một commit giữa hai nhánh.

Trong học phần Git thuộc dịch vụ quản lý mã nguồn, cherry-pick bổ sung cho các thao tác chuyển nhánh, merge, rebase và hoàn tác. Dùng đúng lúc giúp đưa bản sửa cần thiết tới đúng nhánh, đồng thời giữ lịch sử dễ hiểu và hạn chế đưa theo những thay đổi chưa sẵn sàng.

## 1. Cherry-pick hoạt động như thế nào?

Giả sử nhánh `feature/payment` có một commit sửa lỗi kiểm tra số tiền, còn nhánh `release/2.4` cần đúng phần sửa đó. Lịch sử ban đầu:

```text
                 F1 --- F2  feature/payment
                /
A --- B --- C --- D  release/2.4
```

Ta đang đứng trên `release/2.4` và chạy:

```bash
git switch release/2.4
git cherry-pick F1
```

Git lấy thay đổi được giới thiệu bởi `F1`, áp dụng lên nội dung hiện tại của `release/2.4`, rồi tạo commit mới `C1`:

```text
                 F1 --- F2  feature/payment
                /
A --- B --- C --- D --- C1  release/2.4
```

`C1` có thể chứa cùng thay đổi mã nguồn như `F1`, nhưng không phải cùng commit: parent của nó là `D`, trong khi parent của `F1` là `B`. Vì nội dung commit và parent là một phần của mã định danh commit, mã hash của `C1` khác `F1`.

Cherry-pick không kéo toàn bộ lịch sử nhánh `feature/payment` vào `release/2.4`. Nó chỉ áp dụng commit được chọn. Nếu `F1` phụ thuộc vào một commit trước đó chưa có trên nhánh đích, ta có thể cần chọn thêm commit phụ thuộc theo đúng thứ tự hoặc điều chỉnh bản sửa để phù hợp với nhánh đích.

## 2. Chuẩn bị trước khi cherry-pick

Trước khi chọn commit, xác định rõ nhánh đích, commit nguồn và trạng thái repository.

```bash
git status -sb
git branch --show-current
git log --oneline --decorate --graph --all -15
```

Kiểm tra:

- Working tree và staging area không chứa thay đổi dở dang ngoài dự kiến. Cherry-pick có thể bị chặn hoặc làm việc khó kiểm soát nếu đang có thay đổi chưa commit.
- Đang đứng trên nhánh sẽ nhận thay đổi. Cherry-pick áp dụng commit lên `HEAD` hiện tại, không tự chuyển sang nhánh khác.
- Commit nguồn đã có trong repository local và đúng là commit cần chọn.
- Các commit phụ thuộc của commit nguồn đã có trên nhánh đích hoặc sẽ được áp dụng theo thứ tự phù hợp.
- Nhánh đích không có thay đổi tương tự đã được đưa vào bằng cách khác, tránh tạo bản sửa trùng lặp.

Nếu commit nguồn nằm trên remote mà local chưa có, fetch trước:

```bash
git fetch origin
git log --oneline origin/feature/payment
```

Sau khi xác định đúng commit, có thể xem nội dung trước khi áp dụng:

```bash
git show --stat <commit-id>
git show <commit-id>
```

`git show` giúp kiểm tra thông điệp, file thay đổi và patch của commit. Đừng chỉ dựa vào tiêu đề commit vì nội dung có thể rộng hơn tên gọi.

## 3. Cherry-pick một commit

Quy trình cơ bản gồm chuyển tới nhánh đích, xác định commit và chạy cherry-pick:

```bash
git switch release/2.4
git cherry-pick 7a31b20
```

Nếu áp dụng thành công và không phát sinh xung đột, Git tạo commit mới trên `release/2.4`. Thông điệp commit mới mặc định lấy từ commit nguồn. Có thể kiểm tra kết quả:

```bash
git status -sb
git log --oneline --decorate -5
git show --stat HEAD
```

Nếu muốn sửa thông điệp commit trong lúc cherry-pick, dùng `-e` hoặc `--edit`:

```bash
git cherry-pick --edit 7a31b20
```

Git mở trình soạn thảo để ta chỉnh thông điệp trước khi tạo commit. Điều này hữu ích khi cần thêm ngữ cảnh về lý do bản sửa được đưa sang nhánh bảo trì.

### Ghi nguồn gốc commit với `-x`

Khi cần giữ dấu vết commit nguồn trong thông điệp, dùng:

```bash
git cherry-pick -x 7a31b20
```

Git thêm dòng có dạng `cherry picked from commit ...` vào thông điệp commit mới. Dòng này giúp người đọc truy ngược commit gốc, hữu ích khi cùng một bản sửa được chuyển tới nhiều nhánh phát hành. Git thường chỉ thêm dòng này cho cherry-pick không có xung đột; nếu phải giải quyết xung đột thủ công, hãy chủ động ghi nguồn gốc trong thông điệp nếu quy ước dự án yêu cầu.

## 4. Cherry-pick nhiều commit

Có thể truyền nhiều mã commit trong một lệnh:

```bash
git cherry-pick 7a31b20 91cd4e2 b8f02a1
```

Git áp dụng lần lượt các commit theo thứ tự được truyền. Thứ tự rất quan trọng: commit sau có thể phụ thuộc vào thay đổi của commit trước. Nên truyền theo thứ tự từ commit nền cũ hơn tới commit mới hơn.

Ví dụ, nếu `F1` tạo hàm xử lý và `F2` bổ sung nơi gọi hàm đó, hãy áp dụng `F1` trước `F2`:

```bash
git cherry-pick F1 F2
```

Nếu chỉ muốn lấy một khoảng commit, hãy hiểu rõ cách biểu diễn revision range. `A..B` chọn các commit có thể đi tới từ `B` nhưng không có trong tập tổ tiên của `A`; nó không bao gồm `A`. Với một chuỗi tuyến tính, có thể tạo danh sách theo thứ tự cũ đến mới rồi áp dụng:

```bash
git rev-list --reverse A..B
```

Đọc danh sách trước để chắc chắn phạm vi đúng. Khi đã xác nhận, có thể truyền danh sách commit theo thứ tự đó cho `git cherry-pick` hoặc chọn từng commit rõ ràng. Nếu cần bao gồm cả commit `A`, phạm vi thường dùng là `A^..B` khi `A` có parent.

Không nên cherry-pick một khoảng lớn chỉ vì nó tiện viết ngắn. Kiểm tra từng commit để tránh đưa sang nhánh đích các thay đổi thử nghiệm, commit phụ thuộc hoặc thay đổi không thuộc phạm vi phát hành.

## 5. Áp dụng thay đổi mà chưa tạo commit bằng `-n`

Tùy chọn `-n` hoặc `--no-commit` áp dụng thay đổi từ commit nguồn vào working tree và staging area nhưng không tạo commit tự động:

```bash
git cherry-pick --no-commit 7a31b20
```

Ta có thể kiểm tra và điều chỉnh kết quả trước khi tự tạo commit:

```bash
git status
git diff
git diff --cached
```

Sau khi xem xét, có thể tạo một commit mới theo thông điệp phù hợp:

```bash
git commit -m "Backport payment validation fix"
```

`--no-commit` hữu ích khi muốn gộp nhiều thay đổi đã chọn thành một commit duy nhất, hoặc cần điều chỉnh bản vá cho phù hợp với phiên bản cũ. Khi áp dụng nhiều commit bằng `-n`, các thay đổi được tích lũy trong index và working tree; cần kiểm tra kỹ để commit cuối cùng chỉ chứa nội dung mong muốn.

## 6. Cherry-pick commit merge với `-m`

Một merge commit có nhiều parent. Git cần biết ta muốn lấy thay đổi tương đối với parent nào, vì vậy cherry-pick merge commit phải chỉ định mainline parent bằng `-m`:

```bash
git cherry-pick -m 1 <merge-commit-id>
```

`-m 1` chọn parent thứ nhất làm đường cơ sở. Git tính phần khác biệt của merge commit so với parent đó rồi áp dụng lên nhánh hiện tại. `-m 2` chọn parent thứ hai. Số thứ tự parent bắt đầu từ 1, không phải 0.

Trước khi thực hiện, kiểm tra các parent:

```bash
git show --no-patch --pretty=raw <merge-commit-id>
git log --oneline --graph --decorate -10
```

Với merge commit, `git show` có thể hiển thị nhiều parent. Cần hiểu parent nào đại diện cho nhánh nền và parent nào là nhánh được merge. Chọn sai mainline có thể tạo ra patch ngược với ý định.

Cherry-pick merge commit không tái tạo quan hệ merge giữa hai nhánh. Nó áp dụng khác biệt so với parent được chọn và tạo một commit mới trên nhánh hiện tại. Nếu mục tiêu là tích hợp đầy đủ lịch sử của một nhánh, merge thường phù hợp hơn; cherry-pick merge commit chỉ nên dùng khi đã hiểu rõ patch tương đối với mainline.

## 7. Xử lý xung đột khi cherry-pick

Xung đột xảy ra khi thay đổi từ commit nguồn không thể áp dụng tự động lên nội dung hiện tại của nhánh đích. Ví dụ, commit nguồn sửa một dòng trong `PaymentService.java`, nhưng nhánh đích đã thay đổi chính dòng đó theo cách khác.

Khi cherry-pick dừng, Git thông báo file xung đột và để thao tác ở trạng thái đang thực hiện. Kiểm tra:

```bash
git status
```

Mở file bị xung đột. Git có thể đánh dấu vùng chưa được hòa giải bằng các dấu phân cách:

```text
<<<<<<< HEAD
Nội dung hiện tại trên nhánh đích
=======
Nội dung từ commit đang cherry-pick
>>>>>>> 7a31b20
```

Đây là ví dụ minh họa; nội dung thực tế phụ thuộc file và chiến lược merge. Hãy chỉnh file thành kết quả đúng, xóa các dấu phân cách, sau đó stage file đã giải quyết:

```bash
git add src/main/java/example/PaymentService.java
git status
```

Khi tất cả xung đột đã được giải quyết và stage, tiếp tục:

```bash
git cherry-pick --continue
```

Nếu danh sách có nhiều commit, Git sẽ tiếp tục với commit kế tiếp. Có thể phải giải quyết thêm xung đột ở các commit sau.

### Hủy hoặc bỏ qua commit đang áp dụng

Nếu muốn hủy toàn bộ chuỗi cherry-pick đang dở và quay lại trạng thái trước khi bắt đầu thao tác:

```bash
git cherry-pick --abort
```

Nếu đã xác nhận commit hiện tại không cần áp dụng, có thể bỏ qua commit đó:

```bash
git cherry-pick --skip
```

`--skip` bỏ qua commit đang gây dừng và tiếp tục chuỗi còn lại. Chỉ dùng khi hiểu phần thay đổi bị bỏ không cần thiết hoặc đã có cách xử lý khác; nếu bỏ qua một commit nền tảng, commit phía sau có thể không còn áp dụng được.

`git cherry-pick --quit` kết thúc việc theo dõi thao tác đang chạy nhưng để nguyên index và working tree hiện tại. Đây không phải lệnh hoàn tác. Nếu mục tiêu là quay về trạng thái trước khi cherry-pick, dùng `--abort`.

## 8. Khi commit đã được áp dụng hoặc không còn thay đổi

Nếu thay đổi từ commit nguồn đã có trong nhánh đích, cherry-pick có thể báo rằng không có thay đổi mới để commit hoặc dừng vì commit trở thành rỗng. Điều này có thể xảy ra khi:

- Bản sửa đã được merge hoặc cherry-pick trước đó.
- Một commit khác đã tạo ra cùng nội dung thay đổi.
- Trong lúc giải quyết xung đột, ta chọn nội dung khiến patch của commit hiện tại không còn thay đổi gì.

Trước khi quyết định, kiểm tra lịch sử và nội dung:

```bash
git log --oneline --all --decorate --grep="payment validation"
git show <commit-id>
git diff <target-branch>...<source-branch>
```

Nếu thay đổi đã có và không cần commit rỗng để lưu dấu vết, có thể bỏ qua commit theo hướng dẫn Git hoặc dùng `git cherry-pick --skip` khi đang ở trạng thái sequencer. Nếu cần giữ một commit rỗng có chủ đích, Git có tùy chọn `--allow-empty`; với commit trở thành rỗng do nội dung đã được áp dụng, hành vi có thể phụ thuộc phiên bản và tùy chọn `--empty`. Hãy đọc thông báo Git và xác định lý do trước khi ép tạo commit rỗng.

Không nên tiếp tục cherry-pick lặp đi lặp lại cùng một patch chỉ vì chưa thấy commit có cùng mã hash. Commit cherry-pick có mã khác commit nguồn theo thiết kế; cần so sánh nội dung và lịch sử thay vì chỉ so hash.

## 9. Cherry-pick khác merge và rebase như thế nào?

Ba thao tác có mục tiêu khác nhau:

| Thao tác | Mục đích | Ảnh hưởng lịch sử |
| --- | --- | --- |
| `git merge` | Tích hợp lịch sử của một nhánh vào nhánh hiện tại | Giữ các commit nguồn và tạo merge commit nếu không fast-forward |
| `git rebase` | Phát lại một chuỗi commit trên nền khác | Tạo commit mới cho chuỗi được phát lại, thay đổi mã commit |
| `git cherry-pick` | Chọn một hoặc một số commit cụ thể để áp dụng lên nhánh hiện tại | Tạo commit mới chứa thay đổi được chọn, không mang theo quan hệ ancestry của nhánh nguồn |

Ví dụ:

- Dùng **merge** khi muốn tích hợp toàn bộ nhánh `feature/payment` vào `main` theo lịch sử của nhánh.
- Dùng **rebase** khi muốn đặt chuỗi commit của `feature/payment` lên đầu một nhánh nền mới.
- Dùng **cherry-pick** khi chỉ cần một bản sửa riêng lẻ từ `feature/payment` trên `release/2.4`.

Cherry-pick có thể làm cùng một thay đổi xuất hiện trong lịch sử của nhiều nhánh dưới các mã commit khác nhau. Nếu sau đó merge các nhánh này, Git không nhận diện hai commit khác mã là cùng một commit chỉ vì patch tương tự. Hãy cân nhắc chiến lược nhánh và ghi nguồn gốc rõ ràng để tránh khó khăn khi tích hợp về sau.

## 10. Quy trình backport một bản sửa sang nhánh release

Backport là đưa một thay đổi từ nhánh phát triển mới hơn về nhánh phiên bản cũ hơn. Cherry-pick thường được dùng cho công việc này khi chỉ cần một số bản sửa đã được xác định.

Giả sử nhóm đã sửa lỗi trên `main` và muốn chuyển commit đó sang `release/2.4`:

### Bước 1: Cập nhật thông tin remote

```bash
git fetch origin
git log --oneline origin/main -10
```

Tìm commit đã được review và xác nhận phù hợp với nhánh release. Kiểm tra patch và các phụ thuộc của nó.

### Bước 2: Chuyển tới nhánh release

```bash
git switch release/2.4
git status -sb
```

Đảm bảo working tree sạch và đúng nhánh đích. Nếu nhánh release local cần cập nhật từ remote, tích hợp trạng thái mới nhất theo quy trình dự án trước khi cherry-pick.

### Bước 3: Áp dụng commit và lưu dấu nguồn gốc

```bash
git cherry-pick -x <fix-commit-id>
```

Nếu có xung đột, giải quyết theo phần trước rồi chạy `git cherry-pick --continue`.

### Bước 4: Kiểm tra kết quả

```bash
git show --stat HEAD
git show HEAD
git status -sb
```

Chạy test phù hợp với phiên bản release. Một bản sửa hoạt động trên `main` chưa chắc tương thích với API, thư viện hoặc cấu trúc mã nguồn của phiên bản cũ.

### Bước 5: Chia sẻ theo quy trình nhóm

Sau khi review và kiểm tra thành công, push nhánh release hoặc tạo pull request theo quy định:

```bash
git push origin release/2.4
```

Nếu nhánh release được bảo vệ, hãy gửi pull request thay vì push trực tiếp. Cherry-pick chỉ giải quyết việc đưa thay đổi vào nhánh local; quyền ghi và quy trình phát hành vẫn do máy chủ và nhóm quyết định.

## 11. Một số tùy chọn thường gặp

| Tùy chọn | Tác dụng |
| --- | --- |
| `-x` | Ghi mã commit nguồn vào thông điệp commit mới |
| `-e`, `--edit` | Mở editor để chỉnh thông điệp commit |
| `-n`, `--no-commit` | Áp dụng thay đổi vào index/working tree nhưng không tự tạo commit |
| `-m <parent-number>` | Chọn mainline parent khi cherry-pick merge commit |
| `--continue` | Tiếp tục chuỗi sau khi đã giải quyết xung đột |
| `--abort` | Hủy chuỗi cherry-pick đang diễn ra và khôi phục trạng thái trước thao tác |
| `--skip` | Bỏ qua commit hiện tại và tiếp tục chuỗi |
| `--quit` | Dừng sequencer, giữ nguyên trạng thái index và working tree hiện tại |
| `--ff` | Fast-forward nếu `HEAD` hiện tại chính là parent của commit được chọn |
| `--allow-empty` | Cho phép tạo commit rỗng trong trường hợp phù hợp |

Đọc `git help cherry-pick` để xem đầy đủ tùy chọn và khác biệt theo phiên bản Git đang sử dụng.

## 12. Các lỗi và cách xử lý thường gặp

| Tình huống | Nguyên nhân có thể có | Cách xử lý |
| --- | --- | --- |
| `bad object` hoặc không tìm thấy commit | Commit chưa có trong local hoặc mã commit sai | Fetch đúng remote, xác nhận ref và mã commit |
| Cherry-pick báo conflict | Patch không áp dụng tự động lên nhánh đích | Giải quyết file, stage, chạy `--continue` |
| Cherry-pick báo empty | Thay đổi đã có hoặc bị triệt tiêu khi hòa giải | Kiểm tra nội dung, rồi skip hoặc giữ commit rỗng nếu có chủ đích |
| Cherry-pick merge commit yêu cầu `-m` | Commit nguồn có nhiều parent | Xem thứ tự parent và chọn mainline phù hợp |
| Kết quả không chạy trên release | Commit phụ thuộc API hoặc commit khác chưa được chuyển | Xem patch, tìm phụ thuộc, chọn thêm commit theo thứ tự hoặc chỉnh sửa backport |
| Đã cherry-pick nhầm commit | Chọn sai commit hoặc sai nhánh đích | Nếu đang dở, `--abort`; nếu đã tạo commit, đánh giá tác động và cân nhắc `git revert` |
| Bản sửa xuất hiện hai lần | Cùng patch đã được đưa vào bằng commit khác | So sánh diff và lịch sử trước khi tiếp tục |

Nếu cherry-pick đã hoàn tất và tạo commit sai, đừng tùy tiện reset nhánh dùng chung. Với commit đã chia sẻ, `git revert <new-commit-id>` thường là cách tạo commit mới đảo ngược thay đổi, giữ lịch sử đã công bố. Trên nhánh cá nhân chưa chia sẻ, có thể chọn cách sửa lịch sử phù hợp nhưng phải kiểm tra working tree và các commit phía sau trước khi thao tác.

## 13. Thực hành

Thực hiện trên repository thử nghiệm để không ảnh hưởng nhánh đang dùng chung:

1. Tạo nhánh `feature/report` và tạo một commit bổ sung chức năng báo cáo.
2. Tạo nhánh `release/test` từ một commit trước đó, sao cho nhánh này chưa có commit báo cáo.
3. Chuyển sang `release/test` và chạy `git cherry-pick <commit-id>` để chọn commit báo cáo.
4. Dùng `git log --oneline --graph --decorate --all` để quan sát hai nhánh có các commit mang nội dung tương tự nhưng mã commit khác nhau.
5. Thử `git cherry-pick -x <commit-id>` với một commit sửa khác và kiểm tra thông điệp mới.
6. Thử `git cherry-pick -n <commit-id>`, kiểm tra index/working tree rồi tự tạo commit.
7. Trong một nhánh thử nghiệm khác, tạo tình huống hai nhánh sửa cùng dòng để quan sát conflict; giải quyết bằng `--continue`, sau đó thử lại và hủy bằng `--abort`.
8. Tạo merge commit trong repository thử nghiệm và xem các parent bằng `git show --pretty=raw`; thử cherry-pick merge commit với mainline phù hợp.

Sau thực hành, giải thích vì sao cherry-pick tạo commit mới, khi nào cần chọn nhiều commit theo thứ tự, và vì sao backport cần chạy test trên chính nhánh phiên bản cũ.

## 14. Tự kiểm tra kiến thức

1. `git cherry-pick <commit>` áp dụng thay đổi của commit nguồn lên vị trí nào?
2. Vì sao commit được tạo bởi cherry-pick có mã hash khác commit nguồn?
3. Cần kiểm tra những gì trước khi cherry-pick một commit từ remote branch?
4. `git cherry-pick -x` bổ sung thông tin gì vào commit mới?
5. `--no-commit` phù hợp với trường hợp nào?
6. Vì sao cherry-pick merge commit cần chỉ định `-m` và mainline parent?
7. Khi xảy ra conflict, thứ tự thao tác để tiếp tục cherry-pick là gì?
8. `--abort`, `--skip` và `--quit` khác nhau ra sao?
9. Khi nào nên dùng merge hoặc rebase thay cho cherry-pick?
10. Vì sao cần kiểm tra khả năng trùng patch trước khi backport?

## Kết luận

`git cherry-pick` giúp chọn commit cụ thể và áp dụng thay đổi của nó lên nhánh hiện tại. Đây là công cụ hữu ích cho backport, chuyển bản sửa khẩn cấp và tái sử dụng một phần công việc giữa các nhánh. Hãy xác định đúng nhánh đích và commit nguồn, kiểm tra phụ thuộc, xử lý conflict có chủ đích rồi xác minh nội dung sau khi áp dụng. Vì cherry-pick tạo commit mới và không mang theo quan hệ lịch sử của nhánh nguồn, cần ghi dấu nguồn gốc và phối hợp với nhóm khi cùng một bản sửa được đưa tới nhiều nhánh.
