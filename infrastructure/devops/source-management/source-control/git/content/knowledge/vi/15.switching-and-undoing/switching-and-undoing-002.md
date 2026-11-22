# Git reset --soft tác động đến HEAD và giữ chỉ mục

Trong Git, một commit đã được tạo không có nghĩa là lịch sử đã phải giữ nguyên mãi mãi. Khi làm việc trên nhánh cá nhân, bạn có thể cần bỏ commit cuối để tạo lại với thông điệp tốt hơn, gộp vài commit nhỏ thành một commit có ý nghĩa hoặc bổ sung nội dung trước khi ghi nhận lại. Lệnh `git reset --soft` hỗ trợ những tình huống đó bằng cách di chuyển `HEAD` đến một commit khác trong khi giữ nguyên staging area (index) và working tree.

Điểm quan trọng nhất của `--soft` là Git chỉ thay đổi vị trí của `HEAD` hoặc nhánh hiện tại. Nội dung đã staging và các tệp đang làm dở vẫn được giữ nguyên. Vì mốc so sánh `HEAD` đã thay đổi, trạng thái hiển thị trong `git status` có thể khác trước dù index và working tree không bị chỉnh sửa.

## 1. Ôn lại HEAD, index và working tree

Để hiểu `git reset --soft`, trước hết cần phân biệt ba thành phần trong repository.

| Thành phần | Vai trò | Câu hỏi cần trả lời |
| --- | --- | --- |
| HEAD | Xác định commit hiện tại; thường trỏ đến nhánh đang checkout | Bạn đang đứng tại commit nào? |
| Index (staging area) | Lưu nội dung đã chọn cho commit tiếp theo | Nội dung nào đã được chuẩn bị để commit? |
| Working tree | Các tệp thực tế trong thư mục dự án | Bạn đang có những thay đổi nào trên tệp? |

Có thể kiểm tra trạng thái bằng:

~~~bash
git status
git log --oneline --decorate -5
git diff
git diff --cached
~~~

- `git status` cho biết thay đổi đã staging, chưa staging và tệp chưa được theo dõi.
- `git log` cho biết các commit gần đây và nhánh hiện tại đang trỏ đến đâu.
- `git diff` so sánh working tree với index, tức các thay đổi chưa staging.
- `git diff --cached` so sánh index với `HEAD`, tức các thay đổi đã staging để commit.

Hai lệnh diff nhìn vào hai cặp trạng thái khác nhau. Vì thế, một thay đổi có thể xuất hiện trong `git diff --cached` mà không xuất hiện trong `git diff`.

## 2. Git reset --soft làm gì?

Cú pháp:

~~~bash
git reset --soft <commit>
~~~

`<commit>` là mốc lịch sử mà bạn muốn `HEAD` hoặc nhánh hiện tại trỏ tới. Có thể dùng mã commit, tên nhánh, tag hoặc biểu thức như `HEAD~1`.

Khi chạy lệnh này, Git:

1. Di chuyển `HEAD` đến commit đích. Nếu đang checkout một nhánh bình thường, tham chiếu của nhánh đó được di chuyển.
2. Giữ nguyên index như trước lệnh.
3. Giữ nguyên working tree như trước lệnh.

Nói cách khác, `--soft` không checkout lại nội dung của commit đích và không đưa tệp trong thư mục làm việc về trạng thái cũ. Nó chỉ thay đổi mốc lịch sử mà index được so sánh.

### 2.1. Minh họa bằng lịch sử commit

Giả sử nhánh đang có lịch sử:

~~~text
A --- B --- C  (HEAD -> feature/payment)
~~~

Bạn muốn bỏ commit `C` khỏi đầu nhánh nhưng vẫn giữ toàn bộ nội dung của commit đó ở staging area:

~~~bash
git reset --soft HEAD~1
~~~

Sau lệnh, nhánh sẽ trỏ về `B`:

~~~text
A --- B  (HEAD -> feature/payment)

Index:       vẫn giữ nội dung trước reset
Working tree: vẫn giữ các tệp trước reset
~~~

Commit `C` không còn là đầu nhánh hiện tại, nhưng đối tượng commit chưa bị xóa ngay khỏi repository. Nó có thể vẫn được tìm lại qua reflog trong thời gian lưu giữ của Git hoặc qua một tham chiếu khác như nhánh backup.

Do index vẫn chứa nội dung trước reset, Git sẽ hiển thị phần khác biệt giữa `B` và index là thay đổi đã staging. Đây chính là cách `reset --soft` giữ lại nội dung của commit vừa được đưa ra khỏi đầu nhánh.

### 2.2. Index được giữ nguyên nhưng trạng thái staged có thể thay đổi

Cần phân biệt hai ý:

- **Nội dung index không đổi:** các blob và mode đang được staging vẫn như trước khi chạy lệnh.
- **Kết quả so sánh với HEAD thay đổi:** vì HEAD đã lùi về commit khác, `git diff --cached` có thể hiển thị nhiều thay đổi staged hơn.

Ví dụ, trước reset:

- `HEAD` trỏ đến commit `C`.
- Index chứa nội dung của `C`.
- Working tree có thêm một chỉnh sửa chưa staging.

Sau `git reset --soft HEAD~1`:

- `HEAD` trỏ đến `B`.
- Index vẫn chứa nội dung của `C`.
- Working tree vẫn chứa chỉnh sửa chưa staging.

Khi đó:

- `git diff --cached` hiển thị phần khác biệt giữa `B` và index, thường bao gồm nội dung của commit `C`.
- `git diff` vẫn hiển thị phần khác biệt giữa index và working tree, tức các chỉnh sửa chưa staging trước đó.

Không nên diễn giải việc xuất hiện thêm staged changes là Git đã tự stage lại tệp. Index vốn đã giữ nguyên; chỉ có commit nền để so sánh được thay đổi.

## 3. Trường hợp sử dụng phổ biến

### 3.1. Bỏ commit cuối nhưng giữ thay đổi ở trạng thái staged

Giả sử bạn vừa tạo commit nhưng nhận ra thông điệp chưa rõ hoặc muốn bổ sung nội dung rồi tạo lại commit.

Kiểm tra trước:

~~~bash
git status
git log --oneline -5
~~~

Nếu commit cuối là commit cần đưa ra khỏi đầu nhánh:

~~~bash
git reset --soft HEAD~1
~~~

Kiểm tra sau reset:

~~~bash
git status
git diff --cached
git diff
~~~

Các thay đổi thuộc commit vừa bỏ vẫn nằm trong index. Bạn có thể tiếp tục chỉnh sửa working tree, stage phần bổ sung rồi tạo commit mới:

~~~bash
git add src/PaymentService.java
git diff --cached
git commit -m "Validate payment reference"
~~~

Kết quả là nhánh có một commit mới với nội dung đã chuẩn bị. Mã commit mới sẽ khác commit cũ vì lịch sử đã thay đổi.

### 3.2. Gộp hai hoặc nhiều commit gần nhất thành một commit

Khi làm việc, bạn có thể tạo các commit nhỏ như:

~~~text
A --- B --- C --- D  (HEAD -> feature/payment)
~~~

Nếu muốn gộp `C` và `D` thành một commit, có thể lùi HEAD về `B` và giữ lại nội dung của cả hai commit trong index:

~~~bash
git reset --soft HEAD~2
git status
git diff --cached
~~~

Sau đó tạo commit mới:

~~~bash
git commit -m "Implement payment validation"
~~~

Lịch sử sau đó có dạng:

~~~text
A --- B --- E  (HEAD -> feature/payment)
~~~

Trong đó `E` chứa nội dung tổng hợp từ `C` và `D`. Các commit cũ không còn nằm trên đường đi của nhánh hiện tại.

Trước khi gộp, hãy kiểm tra xem các commit có thuộc cùng một mục đích hay không. Không nên gộp những thay đổi độc lập nếu việc tách chúng giúp review, truy tìm lỗi hoặc hoàn tác dễ hơn.

### 3.3. Gộp commit cuối với thay đổi đang staging

Giả sử bạn đã commit một phần công việc, sau đó phát hiện cần thêm một thay đổi nhỏ. Bạn chỉnh sửa và staging phần bổ sung:

~~~bash
git add src/PaymentService.java
git status
~~~

Nếu muốn tạo một commit mới chứa cả commit vừa tạo trước đó và phần bổ sung đang staging:

~~~bash
git reset --soft HEAD~1
git diff --cached
git commit -m "Complete payment validation"
~~~

Vì index được giữ nguyên, nó chứa nội dung của commit cũ cùng phần thay đổi đã staging sau commit đó. Working tree cũng giữ nguyên, bao gồm mọi thay đổi chưa staging.

Trước khi commit lại, kiểm tra kỹ `git diff --cached` để tránh đưa vào những tệp đã staging từ trước nhưng không thuộc mục đích commit mới.

### 3.4. Thay đổi nội dung và thông điệp của commit cuối

Nếu chỉ muốn sửa thông điệp hoặc bổ sung một ít nội dung vào commit cuối, `git commit --amend` thường trực tiếp hơn:

~~~bash
git add src/PaymentService.java
git commit --amend
~~~

Một cách khác là dùng `reset --soft HEAD~1`, sau đó tạo commit mới. Cả hai cách đều tạo ra một commit mới thay cho commit cũ ở đầu nhánh, nhưng thao tác amend diễn đạt rõ ý định chỉnh sửa commit cuối.

Chọn cách phù hợp với quy trình của nhóm. Nếu commit đã được push và người khác đang dựa trên nó, cả amend và reset rồi commit lại đều làm thay đổi lịch sử đã chia sẻ.

## 4. Quy trình thực hiện an toàn

Trước khi chạy `git reset --soft`, hãy xác định chính xác commit đích và bảo toàn tham chiếu đến đầu nhánh hiện tại nếu cần.

### 4.1. Kiểm tra trạng thái và lịch sử

~~~bash
git status --short --branch
git branch --show-current
git log --oneline --decorate -5
git diff
git diff --cached
~~~

Hãy xác nhận:

- Đang ở đúng nhánh cần chỉnh lịch sử.
- Commit dự định bỏ hoặc gộp đúng là commit ở vị trí mong muốn.
- Các thay đổi staged và unstaged hiện có đều đã được hiểu rõ.
- Không có thay đổi không liên quan mà bạn vô tình đưa vào commit mới.

### 4.2. Tạo nhánh backup cho đầu nhánh hiện tại

Nếu thao tác ảnh hưởng đến nhiều commit hoặc bạn chưa quen reset, có thể tạo nhánh backup trỏ đến commit hiện tại:

~~~bash
git branch backup/before-soft-reset
~~~

Tên nhánh backup phải chưa tồn tại. Nếu đã có, chọn tên khác để không làm thay đổi tham chiếu đang được dùng.

Nhánh backup giữ một tham chiếu đến commit cũ. Nó bảo toàn mốc commit, không sao lưu riêng các thay đổi đang nằm trong index hoặc working tree; hãy kiểm tra và bảo toàn những thay đổi đó nếu chúng cũng quan trọng. Nếu cần đưa HEAD về mốc ban đầu, bạn có thể dùng tham chiếu backup.

### 4.3. Chạy reset với mốc rõ ràng

Để đưa HEAD lùi một commit:

~~~bash
git reset --soft HEAD~1
~~~

Để lùi hai commit:

~~~bash
git reset --soft HEAD~2
~~~

Hoặc chỉ định trực tiếp mã commit:

~~~bash
git reset --soft a1b2c3d
~~~

Mã commit trong ví dụ chỉ mang tính minh họa. Hãy thay bằng commit thực tế mà bạn đã xác định qua `git log`.

### 4.4. Kiểm tra lại index và working tree

Sau reset:

~~~bash
git status
git diff --cached
git diff
git log --oneline --decorate -5
~~~

Kiểm tra nội dung staged có đúng là phần bạn muốn đưa vào commit tiếp theo hay không. Nếu có thay đổi chưa staging, chúng vẫn được thể hiện trong `git diff`.

Khi đã xác nhận, có thể:

- Chỉnh sửa tiếp rồi stage các tệp cần thiết.
- Bỏ staging một phần bằng `git restore --staged <file>` nếu không muốn đưa tệp đó vào commit tiếp theo.
- Tạo commit mới bằng `git commit`.

Ví dụ:

~~~bash
git restore --staged docs/draft.md
git diff
git diff --cached
git commit -m "Refine payment validation"
~~~

Lệnh `git restore --staged` chỉ đưa nội dung staged của đường dẫn về trạng thái trong HEAD hiện tại; nó giữ nội dung working tree. Sau soft reset, HEAD đã lùi về mốc mới, vì vậy hãy kiểm tra diff trước khi dùng.

## 5. So sánh reset --soft, reset --mixed và reset --hard

Ba chế độ reset khác nhau ở mức độ tác động đến index và working tree.

| Chế độ | Di chuyển HEAD/nhánh | Cập nhật index | Cập nhật working tree |
| --- | --- | --- | --- |
| `--soft` | Có | Giữ nguyên | Giữ nguyên |
| `--mixed` | Có | Đặt lại theo commit đích | Giữ nguyên |
| `--hard` | Có | Đặt lại theo commit đích | Đặt lại theo commit đích |

### 5.1. --soft

~~~bash
git reset --soft HEAD~1
~~~

Dùng khi muốn bỏ commit khỏi đầu nhánh nhưng vẫn giữ toàn bộ nội dung của commit đó trong staging area. Đây là chế độ phù hợp khi chuẩn bị tạo lại hoặc gộp commit.

### 5.2. --mixed

~~~bash
git reset --mixed HEAD~1
~~~

Đây là chế độ mặc định nếu không chỉ định `--soft` hoặc `--hard`. Nó di chuyển HEAD và cập nhật index về trạng thái commit đích, nhưng không cập nhật working tree.

Vì vậy, thay đổi từ commit vừa bỏ thường xuất hiện trong working tree dưới dạng chưa staging. Bạn có thể chọn lại từng phần bằng `git add`.

### 5.3. --hard

~~~bash
git reset --hard HEAD~1
~~~

Chế độ này di chuyển HEAD, cập nhật index và ghi lại working tree theo commit đích. Những thay đổi chưa commit trên các tệp đã được Git theo dõi có thể bị ghi đè và mất. Tệp chưa được theo dõi thường được giữ nguyên, trừ khi chúng nằm cản trở việc ghi một tệp đã được Git theo dõi; trong trường hợp đó Git có thể xóa chúng.

Chỉ dùng `--hard` khi bạn đã xác nhận muốn bỏ các thay đổi trên working tree. Nếu mục tiêu chỉ là bỏ commit nhưng giữ nội dung, `--soft` hoặc `--mixed` phù hợp hơn.

## 6. So sánh reset --soft với revert

`reset --soft` và `git revert` giải quyết hai nhu cầu khác nhau.

| Tiêu chí | `git reset --soft` | `git revert` |
| --- | --- | --- |
| Cách hoạt động | Di chuyển HEAD/nhánh về commit khác | Tạo commit mới đảo ngược thay đổi |
| Commit cũ | Không còn nằm trên đầu nhánh hiện tại | Vẫn nằm trong lịch sử |
| Index | Giữ nguyên | Thay đổi được chuẩn bị cho commit revert theo quy trình |
| Phù hợp | Chỉnh lịch sử local, gộp hoặc tạo lại commit | Hoàn tác thay đổi đã chia sẻ |
| Ảnh hưởng đến người khác | Có thể cần đồng bộ lại nếu đã push | Thường dễ phối hợp trên nhánh dùng chung |

Nếu commit đã được push lên nhánh dùng chung, `git revert` thường là lựa chọn an toàn hơn:

~~~bash
git revert <commit>
~~~

Lệnh tạo một commit mới có tác dụng ngược với commit được chỉ định. Nó giữ lại dấu vết thay đổi ban đầu và việc hoàn tác trong lịch sử.

Không dùng `reset --soft` để âm thầm viết lại lịch sử trên nhánh chung. Nếu nhóm chủ động yêu cầu viết lại lịch sử, cần phối hợp với người đang sử dụng nhánh và thực hiện push cập nhật theo quy trình đã thống nhất.

## 7. Khôi phục nếu reset đến nhầm commit

### 7.1. Dùng nhánh backup

Nếu đã tạo nhánh backup trước khi reset:

~~~bash
git reset --soft backup/before-soft-reset
~~~

Lệnh đưa HEAD hoặc nhánh hiện tại trở lại commit mà backup đang trỏ tới, đồng thời vẫn giữ index và working tree hiện tại. Hãy kiểm tra lại `git status` và diff sau thao tác.

### 7.2. Dùng reflog để tìm đầu nhánh cũ

Nếu chưa tạo backup, reflog thường ghi lại các lần cập nhật HEAD và nhánh local:

~~~bash
git reflog
~~~

Ví dụ, bạn có thể thấy một dòng ghi nhận thao tác reset gần đây và commit trước đó. Xác định đúng mã commit cũ rồi tạo một nhánh cứu hộ:

~~~bash
git branch rescue/before-reset <commit-cu>
~~~

Hoặc nếu chắc chắn muốn đưa nhánh hiện tại về commit đó mà vẫn giữ index và working tree:

~~~bash
git reset --soft <commit-cu>
~~~

Reflog là nhật ký cục bộ và có thời hạn lưu giữ. Nó hữu ích để tìm lại commit vừa bị tách khỏi nhánh, nhưng không thay thế bản backup lâu dài. Khi phát hiện reset nhầm, nên kiểm tra reflog sớm và tạo một nhánh cứu hộ trước khi thực hiện thêm thao tác ghi đè lịch sử.

### 7.3. Hiểu giới hạn của việc khôi phục

Sau `reset --soft`, commit cũ thường vẫn tồn tại trong object database dù không còn được nhánh hiện tại tham chiếu. Git có thể dọn các đối tượng không còn được tham chiếu sau thời gian và theo quy trình garbage collection. Vì vậy, không nên coi khả năng tìm lại bằng reflog là bảo đảm vĩnh viễn.

Nếu nội dung quan trọng, hãy tạo backup branch hoặc bản sao lưu trước khi chỉnh lịch sử.

## 8. Một số lưu ý đặc biệt

### 8.1. HEAD đang detached

Nếu đang ở trạng thái detached HEAD, `HEAD` trỏ trực tiếp đến commit thay vì thông qua một nhánh local. Khi chạy:

~~~bash
git reset --soft <commit>
~~~

Git di chuyển HEAD đến commit đích nhưng không di chuyển một nhánh local thông thường. Nếu muốn tiếp tục phát triển công việc, hãy tạo hoặc chuyển sang nhánh phù hợp trước khi thay đổi lịch sử.

Kiểm tra trạng thái detached bằng:

~~~bash
git status -sb
git branch --show-current
~~~

Nếu `git branch --show-current` không in tên nhánh, có thể bạn đang ở detached HEAD.

### 8.2. HEAD~1 và HEAD^ trong lịch sử có merge commit

`HEAD~1` tương đương với cha thứ nhất của commit hiện tại. `HEAD~2` đi theo cha thứ nhất thêm một bước nữa. Với merge commit, có nhiều cha, nên `HEAD~1` không có nghĩa là mọi nhánh cha đều được chọn.

Trước khi reset một merge commit, xem đồ thị:

~~~bash
git log --oneline --graph --decorate -10
~~~

Nếu muốn chọn một cha cụ thể hoặc một mốc khác, xác định mã commit rõ ràng thay vì dựa vào ký hiệu tương đối.

### 8.3. Soft reset không chuyển sang nhánh khác

Tên `reset` đôi khi khiến người mới nhầm với thao tác chuyển nhánh. `git reset --soft` không dùng để chuyển sang một nhánh khác. Nó di chuyển HEAD hoặc nhánh hiện tại đến commit đích.

Muốn chuyển nhánh, dùng:

~~~bash
git switch main
~~~

Muốn di chuyển đầu nhánh hiện tại nhưng giữ index và working tree, dùng:

~~~bash
git reset --soft <commit>
~~~

Hai thao tác có mục đích khác nhau.

## 9. Ví dụ tổng hợp: gộp hai commit sửa lỗi

Giả sử bạn làm việc trên nhánh `bugfix/invoice-rounding` và đã tạo hai commit:

~~~text
a10f2c1 Fix decimal conversion
b21a3d4 Add rounding boundary case  (HEAD -> bugfix/invoice-rounding)
~~~

Bạn muốn gộp chúng thành một commit vì cả hai cùng giải quyết một lỗi làm tròn.

**Bước 1 — Kiểm tra lịch sử và trạng thái**

~~~bash
git status --short --branch
git log --oneline -5
git diff
git diff --cached
~~~

Xác nhận không có thay đổi ngoài dự kiến.

**Bước 2 — Tạo nhánh backup**

~~~bash
git branch backup/invoice-rounding-before-squash
~~~

**Bước 3 — Lùi HEAD hai commit nhưng giữ index**

~~~bash
git reset --soft HEAD~2
~~~

**Bước 4 — Kiểm tra nội dung sẽ đưa vào commit mới**

~~~bash
git status
git diff --cached
git diff
~~~

Index hiện giữ nội dung của hai commit trước đó. Nếu có thay đổi chưa staging từ trước, chúng vẫn nằm trong working tree và cần được xem xét riêng.

**Bước 5 — Tạo commit tổng hợp**

~~~bash
git commit -m "Fix invoice rounding boundaries"
~~~

**Bước 6 — Kiểm tra lịch sử mới**

~~~bash
git log --oneline --decorate -5
git status
~~~

Nhánh hiện tại có một commit tổng hợp thay cho hai commit cũ. Nhánh backup vẫn giữ mốc lịch sử ban đầu để có thể tham chiếu lại nếu cần.

Nếu hai commit cũ đã được push và người khác đang sử dụng nhánh, hãy phối hợp trước khi cập nhật lịch sử đã viết lại. Trong trường hợp không cần gộp lịch sử, có thể giữ hai commit và tiếp tục phát triển.

## 10. Những sai lầm thường gặp

- **Cho rằng soft reset xóa nội dung commit:** lệnh chỉ di chuyển HEAD hoặc nhánh; nội dung vẫn nằm trong index và working tree.
- **Cho rằng index không đổi thì git status cũng không đổi:** trạng thái staged được tính bằng cách so sánh index với HEAD, nên có thể xuất hiện thêm thay đổi staged sau reset.
- **Nhầm soft với mixed:** mixed cập nhật index theo commit đích, còn soft giữ nguyên index.
- **Dùng hard reset khi chỉ muốn bỏ commit:** có thể làm mất thay đổi chưa commit trên các tệp được theo dõi.
- **Reset nhầm số lượng commit:** `HEAD~2` lùi hai bước theo cha thứ nhất. Kiểm tra đồ thị và mã commit trước khi chạy.
- **Reset lịch sử đã chia sẻ mà không phối hợp:** làm các bản clone khác lệch lịch sử và có thể cần force push. Với nhánh dùng chung, cân nhắc revert.
- **Không kiểm tra staged changes trước commit mới:** có thể đưa thay đổi không liên quan vào cùng một commit.
- **Coi reflog là backup vĩnh viễn:** reflog có thời hạn lưu giữ. Tạo nhánh backup khi cần bảo toàn một mốc quan trọng.

## 11. Bảng tra cứu nhanh

| Mục tiêu | Lệnh |
| --- | --- |
| Xem HEAD và lịch sử | `git log --oneline --decorate -5` |
| Xem thay đổi chưa staging | `git diff` |
| Xem thay đổi đã staging | `git diff --cached` |
| Bỏ commit cuối, giữ staged changes | `git reset --soft HEAD~1` |
| Bỏ hai commit cuối, giữ staged changes | `git reset --soft HEAD~2` |
| Đưa HEAD về một commit cụ thể, giữ index | `git reset --soft <commit>` |
| Tạo nhánh backup trước reset | `git branch backup/before-soft-reset` |
| Xem lịch sử di chuyển HEAD | `git reflog` |
| Đưa commit ra khỏi lịch sử bằng commit đảo ngược | `git revert <commit>` |
| Đưa nội dung staged về HEAD hiện tại | `git restore --staged <file>` |

## 12. Tổng kết

`git reset --soft` là công cụ chỉnh lịch sử ở đầu nhánh bằng cách di chuyển HEAD hoặc tham chiếu nhánh đến một commit khác, đồng thời giữ nguyên index và working tree. Vì index không đổi, các nội dung đã có trước reset vẫn được giữ; tuy nhiên, khi HEAD lùi lại, phần chênh lệch giữa HEAD mới và index sẽ được hiển thị là staged changes.

Lệnh này phù hợp khi bỏ commit cuối nhưng muốn giữ nội dung để tạo lại, gộp nhiều commit hoặc chuẩn bị một commit mới có ý nghĩa rõ ràng. Trước khi dùng, hãy kiểm tra lịch sử, trạng thái staged và unstaged, cân nhắc tạo nhánh backup, rồi xác nhận lại bằng `git status`, `git diff --cached` và `git diff`.

Với lịch sử đã chia sẻ, cần cân nhắc tác động đến những người khác. Nếu mục tiêu là hoàn tác thay đổi trên nhánh dùng chung mà vẫn giữ lịch sử, `git revert` thường phù hợp hơn. Hiểu rõ phạm vi tác động của từng lệnh giúp bạn chỉnh sửa lịch sử có kiểm soát và giữ lại nội dung quan trọng.

