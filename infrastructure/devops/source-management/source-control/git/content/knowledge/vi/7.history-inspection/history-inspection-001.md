# Đọc lịch sử bằng git log và đồ thị nhánh

Git lưu lịch sử dưới dạng một đồ thị có hướng không chu trình (DAG). Mỗi commit ghi lại một snapshot và tham chiếu đến commit cha của nó; branch và tag là các ref trỏ đến những commit cụ thể. Lệnh `git log` giúp đọc các commit theo phạm vi bạn chọn, còn tùy chọn `--graph` biểu diễn quan hệ cha-con để bạn thấy các nhánh được tách ra và hợp nhất như thế nào.

Khi đọc lịch sử, đừng chỉ nhìn ngày tháng hoặc dòng thông điệp. Hãy xác định commit nào là cha của commit nào, branch/ref nào đang trỏ tới đâu, commit nào chỉ có trên một nhánh và commit nào là điểm hợp nhất. Kết hợp `git log`, `git branch`, `git merge-base` và các bộ lọc phù hợp sẽ giúp bạn hiểu tiến trình phát triển, chuẩn bị merge/rebase và điều tra thay đổi.

## 1. Commit và lịch sử là một đồ thị

Một commit chứa OID của tree đại diện snapshot, thông tin tác giả/committer, thông điệp và một hoặc nhiều parent commit. Commit thông thường có một parent; commit đầu tiên của repository không có parent; merge commit thường có từ hai parent trở lên.

Ví dụ lịch sử tuyến tính:

```text
A---B---C---D  main
```

Mỗi commit mới trỏ về commit trước đó. Nếu tạo branch `feature` từ B rồi tiếp tục commit song song:

```text
      C1---C2  feature
     /
A---B---D---E  main
```

Branch không phải một bản sao thư mục hay một chuỗi commit riêng biệt. Branch là một ref có tên, trỏ đến commit đầu nhánh. Hai branch có thể cùng trỏ đến những commit có chung tổ tiên, sau đó phát triển theo các hướng khác nhau.

Khi merge `feature` vào `main`, Git có thể tạo merge commit có hai parent:

```text
      C1---C2------+
     /             \
A---B---D---E-------M  main
```

Đồ thị commit giúp trả lời những câu hỏi như: nhánh nào được tạo từ đâu, commit nào đã được tích hợp, nhánh nào còn commit chưa đưa vào nhánh chính và merge commit kết nối những lịch sử nào.

## 2. Xem lịch sử cơ bản bằng git log

Lệnh cơ bản:

```bash
git log
```

Mặc định, Git hiển thị lịch sử reachable từ `HEAD`, thường là branch hiện tại. Mỗi mục có mã commit, tác giả, ngày tác giả, thông tin commit và thông điệp. Dùng `q` để thoát trình xem (pager) khi Git mở kết quả trong terminal.

Để xem ngắn gọn:

```bash
git log --oneline
```

Mỗi commit được hiển thị trên một dòng với mã rút gọn và subject. Cách này phù hợp khi bạn cần quét nhanh lịch sử gần đây.

Xem thêm tên branch/tag đang trỏ đến commit:

```bash
git log --oneline --decorate
```

`--decorate` hiển thị các ref như `HEAD -> main`, `origin/main` hoặc tag. Các nhãn này giúp nhận ra commit nào đang là đầu branch, tag phát hành hoặc vị trí remote-tracking branch.

Giới hạn số commit gần nhất:

```bash
git log -5 --oneline --decorate
```

Số `5` chỉ giới hạn số commit được hiển thị; nó không thay đổi lịch sử.

## 3. Vẽ đồ thị nhánh bằng --graph

Lệnh thường dùng để xem toàn bộ đồ thị nhánh trong clone:

```bash
git log --graph --oneline --decorate --all
```

Ý nghĩa các tùy chọn:

- `--graph`: vẽ các đường nối giữa commit và parent commit bằng ký tự ASCII.
- `--oneline`: rút gọn mỗi commit thành một dòng.
- `--decorate`: gắn tên branch, tag và ref lên commit tương ứng.
- `--all`: duyệt lịch sử reachable từ các ref local mà Git biết, thay vì chỉ từ `HEAD`.

Ví dụ đầu ra minh họa:

```text
*   8ac31e2 (HEAD -> main) Merge feature/payment
|\
| * 71c09ad (feature/payment) Add payment retry
| * 52d7a11 Add payment gateway client
* | 3a4b2f0 Fix checkout validation
|/
* 2f91c44 (tag: v1.2.0) Add checkout flow
* 0d8b6e1 Initial commit
```

Đọc từ trên xuống dưới thường là từ commit mới về commit cũ. Dòng `*` biểu diễn một commit; các nhánh `|`, `/`, `\` thể hiện đường đi trong đồ thị về các parent. Trong ví dụ, `main` chứa merge commit `8ac31e2`, còn `feature/payment` trỏ đến commit `71c09ad` trên nhánh được hợp nhất.

Đồ thị là cách trình bày lịch sử, không phải sơ đồ chính xác về thời gian làm việc của từng người. Một commit có thể có author date cũ hơn hoặc mới hơn commit khác do cherry-pick, rebase, sửa metadata hoặc đồng hồ máy không đồng bộ.

### Chỉ xem một vài nhánh hoặc nhóm ref

`--all` hữu ích để xem nhiều ref, nhưng đôi khi đồ thị quá dày. Bạn có thể chỉ định các revision cụ thể:

```bash
git log --graph --oneline --decorate main feature/payment
```

Hoặc chỉ xem branch local:

```bash
git log --graph --oneline --decorate --branches
```

Chỉ xem remote-tracking refs:

```bash
git log --graph --oneline --decorate --remotes
```

Chỉ xem tag:

```bash
git log --graph --oneline --decorate --tags
```

`--all` không có nghĩa là Git truy cập mọi branch trên máy chủ. Nó chỉ sử dụng các ref hiện có trong clone local. Nếu remote có branch mới hoặc vừa thay đổi, cần fetch để cập nhật remote-tracking refs trước khi phân tích trạng thái mới nhất.

## 4. Hiểu các nhãn ref trong đồ thị

Khi dùng `--decorate`, bạn có thể gặp các nhãn sau:

| Nhãn thường thấy | Ý nghĩa |
|---|---|
| `HEAD -> main` | `HEAD` đang trỏ theo branch `main`; commit này là đầu branch hiện tại |
| `feature/search` | Branch local có tên `feature/search` trỏ tới commit này |
| `origin/main` | Remote-tracking ref ghi nhận vị trí `main` lần gần nhất được fetch từ remote `origin` |
| `tag: v2.0.0` | Tag `v2.0.0` trỏ tới commit hoặc tag object tương ứng |
| `HEAD` không có mũi tên branch | Có thể đang ở detached HEAD tại commit đó |

Remote-tracking ref như `origin/main` là thông tin local về trạng thái remote ở lần fetch gần nhất; nó không tự cập nhật theo hoạt động trên server. Xem các remote và URL:

```bash
git remote -v
git branch -vv
```

`git branch -vv` hiển thị branch local cùng upstream và trạng thái ahead/behind theo dữ liệu tracking hiện có. Để cập nhật thông tin từ remote trước khi so sánh:

```bash
git fetch --all --prune
```

Fetch cập nhật object và remote-tracking refs; `--prune` dọn các remote-tracking ref tương ứng với branch đã bị xóa trên remote. Lệnh này không tự merge hoặc rebase branch đang làm việc.

## 5. Chọn thứ tự hiển thị commit

Đồ thị phân nhánh có thể được hiển thị theo các thứ tự khác nhau. Hai tùy chọn thường gặp:

```bash
git log --graph --oneline --all --topo-order
git log --graph --oneline --all --date-order
```

- `--topo-order` ưu tiên thứ tự tô-pô: commit con được hiển thị trước commit cha và cố gắng không trộn các dòng phát triển song song quá sớm.
- `--date-order` cũng giữ quy tắc không hiển thị parent trước child, nhưng ưu tiên thứ tự ngày commit khi có thể.

`--graph` mặc định kéo theo thứ tự topo nếu bạn không chỉ định thứ tự khác. Với lịch sử nhiều nhánh, `--topo-order` thường giúp nhìn từng dòng phát triển rõ hơn. `--date-order` hữu ích khi muốn thứ tự gần với thời gian commit hơn mà vẫn giữ ràng buộc cha-con.

Ngày commit không phải lúc nào cũng phản ánh thứ tự tích hợp. Rebase tạo commit mới với committer date mới; cherry-pick cũng tạo commit mới; commit có thể được tạo trên máy có đồng hồ lệch. Khi cần xác định quan hệ lịch sử, ưu tiên parent graph và ref thay vì chỉ dựa vào timestamp.

## 6. Xem lịch sử theo một branch hoặc commit

`git log` nhận revision làm đối số. Ví dụ:

```bash
git log --oneline main
git log --oneline feature/payment
git log --oneline v2.0.0
```

Mỗi lệnh hiển thị các commit reachable từ revision đó. So sánh hai branch bằng đồ thị:

```bash
git log --graph --oneline --decorate main feature/payment
```

Nếu chỉ muốn biết commit nào nằm trên một branch mà chưa có ở branch kia, hãy dùng revision range.

### Range A..B

```bash
git log --oneline main..feature/payment
```

`A..B` hiển thị các commit reachable từ B nhưng không reachable từ A. Trong ví dụ, lệnh liệt kê commit có trên `feature/payment` mà chưa có trong `main`.

Chiều ngược lại:

```bash
git log --oneline feature/payment..main
```

Lệnh hiển thị commit có trên `main` nhưng chưa có trong `feature/payment`.

Đây là cách nhanh để xem branch nào có commit riêng trước khi merge hoặc rebase. Kết quả phụ thuộc đồ thị tổ tiên, không chỉ dựa vào so sánh tên hoặc ngày commit.

### Range A...B

```bash
git log --oneline --left-right main...feature/payment
```

`A...B` lấy các commit reachable từ một trong hai phía nhưng không reachable từ cả hai; tức phần khác nhau của hai lịch sử sau khi loại tổ tiên chung. `--left-right` đánh dấu commit thuộc phía trái bằng `<` và phía phải bằng `>`.

Ví dụ:

```text
< 2a1b3c4 Fix checkout timeout
< 7d8e9f0 Update deployment config
> 4c5d6e7 Add payment retry
> 8f9a0b1 Add gateway metrics
```

Các dấu này giúp nhận biết commit riêng của mỗi branch. Có thể kết hợp `--graph` để thấy quan hệ nhánh:

```bash
git log --graph --oneline --left-right main...feature/payment
```

### Tìm tổ tiên chung

Để tìm merge base của hai branch:

```bash
git merge-base main feature/payment
```

Merge base là tổ tiên chung phù hợp mà Git dùng làm điểm tham chiếu cho nhiều thao tác merge ba chiều. Kết hợp với log giúp hiểu hai nhánh bắt đầu khác nhau từ đâu.

## 7. Xem đồ thị tập trung vào nhánh chính

Khi repository dùng merge commit để tích hợp feature, lịch sử có thể chứa nhiều commit bên trong nhánh phụ. Nếu chỉ muốn đọc dòng tích hợp chính, dùng `--first-parent`:

```bash
git log --first-parent --graph --oneline --decorate main
```

Tùy chọn này đi theo parent thứ nhất của mỗi commit merge. Nó tạo một góc nhìn tuyến tính hơn về các commit đã được đưa vào branch chính, thường hữu ích với workflow merge commit.

So sánh:

```bash
git log --graph --oneline main
git log --first-parent --graph --oneline main
```

Lệnh đầu có thể hiển thị commit từ các nhánh phụ. Lệnh thứ hai tập trung vào chuỗi tích hợp chính và bỏ qua lịch sử nội bộ của parent phụ. Vì vậy, `--first-parent` phù hợp để xem tiến trình release hoặc mainline, nhưng không phù hợp nếu bạn cần kiểm tra toàn bộ commit bên trong một feature branch.

Lọc merge commit:

```bash
git log --merges --oneline main
```

Chỉ xem commit không phải merge:

```bash
git log --no-merges --oneline main
```

Bạn có thể kết hợp với `--first-parent` để xem các merge được đưa vào mainline:

```bash
git log --first-parent --merges --oneline main
```

## 8. Đọc nội dung thay đổi trong lịch sử

`git log` mặc định tập trung vào metadata commit. Để xem nội dung file thay đổi, dùng `-p`:

```bash
git log -p -3 -- src/payment.js
```

Lệnh hiển thị patch của ba commit gần nhất có liên quan đến đường dẫn `src/payment.js` theo lịch sử được duyệt.

Nếu chỉ cần tóm tắt file thay đổi:

```bash
git log --stat --oneline -5
git log --name-status --oneline -5
```

- `--stat` hiển thị số dòng thêm/xóa theo file.
- `--name-status` liệt kê tên file cùng trạng thái như thêm (`A`), sửa (`M`), xóa (`D`) hoặc rename (`R`).
- `--summary` hiển thị thông tin tóm tắt như create/delete mode hoặc rename được nhận diện.

Ví dụ:

```bash
git log --summary --find-renames -5
```

Những tùy chọn này giúp chọn mức chi tiết phù hợp: dùng `--oneline` để quét nhanh, `--stat` để xác định phạm vi, rồi `-p` để đọc từng dòng thay đổi.

## 9. Lọc lịch sử theo người, thời gian và thông điệp

Khi repository có nhiều commit, bạn có thể kết hợp bộ lọc để thu hẹp kết quả.

### Theo tác giả hoặc người commit

```bash
git log --author="An Nguyen" --oneline
git log --committer="Build Bot" --oneline
```

`--author` lọc theo trường author; `--committer` lọc theo trường committer. Hai trường có thể khác nhau, chẳng hạn khi một người tạo commit rồi người khác cherry-pick hoặc áp dụng thay đổi.

### Theo thời gian

```bash
git log --since="2026-01-01" --oneline
git log --after="2 weeks ago" --oneline
git log --until="2026-03-31" --oneline
```

`--since`/`--after` đặt mốc sớm nhất; `--until`/`--before` đặt mốc muộn nhất. Có thể kết hợp cả hai để xem một khoảng thời gian. Bộ lọc thời gian dựa trên timestamp của commit theo quy tắc Git; nếu commit được tạo lại bằng rebase/cherry-pick, ngày có thể không trùng thời điểm thay đổi ban đầu.

### Theo thông điệp commit

```bash
git log --grep="payment" --oneline
git log --grep="fix.*timeout" --regexp-ignore-case --oneline
```

`--grep` tìm trong thông điệp commit. Có thể dùng `--all-match` khi chỉ định nhiều mẫu và muốn một commit khớp tất cả điều kiện grep thay vì chỉ cần khớp một mẫu.

Ví dụ kết hợp:

```bash
git log --author="An Nguyen" --since="1 month ago" --grep="payment" --oneline
```

## 10. Tìm commit làm thay đổi một giá trị hoặc đoạn mã

Đôi khi bạn không biết thông điệp commit hoặc file chính xác, nhưng biết một chuỗi đã được thêm, xóa hoặc thay đổi.

### Tìm khi số lần xuất hiện của chuỗi thay đổi bằng -S

```bash
git log -S"calculateTotal" --oneline -- src/
```

`-S<string>` tìm commit mà số lần xuất hiện chính xác của chuỗi thay đổi trong diff. Đây là lựa chọn tốt khi bạn muốn biết lúc một tên hàm hoặc literal được thêm vào hay xóa đi.

### Tìm theo biểu thức chính quy bằng -G

```bash
git log -G"return .*total" --oneline -- src/payment.js
```

`-G<regex>` tìm commit có dòng được thêm hoặc xóa khớp biểu thức chính quy. Khác biệt chính là `-S` theo dõi số lần xuất hiện của chuỗi, còn `-G` tìm dòng trong patch khớp regex.

Khi tìm thấy commit ứng viên, xem patch:

```bash
git show <COMMIT_ID>
```

Không nên kết luận commit đó gây lỗi chỉ vì nó có chứa chuỗi cần tìm. Hãy đối chiếu thay đổi với test tái hiện hoặc hành vi thực tế.

## 11. Theo dõi lịch sử của một file qua rename

Xem các commit có tác động đến một đường dẫn:

```bash
git log --oneline -- src/payment.js
```

Nếu file từng được đổi tên, dùng `--follow` để Git cố lần ngược lịch sử qua rename được nhận diện:

```bash
git log --follow --oneline -- src/payment.js
```

`--follow` được thiết kế cho một đường dẫn file và có giới hạn, đặc biệt trong lịch sử merge phức tạp. Git nhận diện rename dựa trên độ tương đồng nội dung khi tạo diff; commit không lưu một bản ghi rename độc lập.

Xem nội dung file tại một commit:

```bash
git show <COMMIT_ID>:src/payment.js
```

Tìm commit xóa file:

```bash
git log --all --diff-filter=D --summary -- src/legacy-payment.js
```

Nếu đường dẫn được đổi tên nhiều lần, hãy kết hợp `--follow`, `--name-status` và `git show` để xác định các tên cũ/mới.

## 12. Tùy chỉnh định dạng log

`--pretty` hoặc `--format` cho phép chọn trường cần hiển thị:

```bash
git log --pretty=format:"%h %ad %an <%ae> %s" --date=short -10
```

Các placeholder phổ biến:

| Placeholder | Nội dung |
|---|---|
| `%H` | OID đầy đủ của commit |
| `%h` | OID rút gọn |
| `%T` / `%t` | OID tree đầy đủ / rút gọn |
| `%P` / `%p` | OID parent đầy đủ / rút gọn |
| `%an` / `%ae` | Tên / email author |
| `%cn` / `%ce` | Tên / email committer |
| `%ad` / `%cd` | Ngày author / committer theo định dạng được chọn |
| `%s` | Subject của commit message |
| `%b` | Phần body của commit message |
| `%d` | Các decoration như branch/tag |

Ví dụ xem cả author date và committer date:

```bash
git log --pretty=format:"%h | author %ad | committer %cd | %s" --date=iso-strict -10
```

Một số preset có sẵn:

```bash
git log --pretty=short
git log --pretty=fuller
git log --pretty=oneline
```

`--pretty=fuller` hiển thị rõ cả author và committer cùng thời gian. Điều này hữu ích khi điều tra commit được cherry-pick, rebase hoặc tạo lại bởi người khác.

## 13. Đọc đồ thị khi chuẩn bị merge hoặc rebase

Trước khi tích hợp branch `feature/payment` vào `main`, hãy xem hai đầu nhánh và commit riêng:

```bash
git fetch origin
git log --graph --oneline --decorate --all
git log --oneline main..feature/payment
git log --oneline feature/payment..main
git merge-base main feature/payment
```

Những lệnh này giúp trả lời:

1. `main` và `feature/payment` đang trỏ đến commit nào?
2. Feature có những commit nào mà main chưa có?
3. Main có commit nào mà feature chưa có?
4. Tổ tiên chung gần nhất của hai branch là commit nào?

Nếu `main..feature/payment` không có kết quả, feature không có commit riêng nào chưa nằm trong main theo quan hệ tổ tiên. Nếu cả hai chiều đều có kết quả, hai branch đã phân kỳ. Đồ thị giúp bạn chọn merge, rebase hoặc cập nhật branch theo quy trình nhóm.

Không nên chỉ dựa vào đồ thị để quyết định có thể fast-forward hay không. Có thể kiểm tra cụ thể:

```bash
git merge-base --is-ancestor main feature/payment
```

Mã thoát `0` nghĩa là `main` là tổ tiên của `feature/payment`; khi đó main có thể fast-forward tới feature nếu không có ràng buộc khác. Mã thoát khác `0` nghĩa là quan hệ tổ tiên đó không đúng.

## 14. Một số tùy chọn giúp đơn giản hóa đồ thị

Với repository lâu năm, đồ thị `--all` có thể quá dài. Có thể chỉ hiển thị commit gắn với ref hoặc tag:

```bash
git log --graph --oneline --decorate --all --simplify-by-decoration
```

`--simplify-by-decoration` lược bớt nhiều commit không có decoration để làm rõ các mốc branch/tag. Nó hữu ích để xem tổng quan nhưng không thay thế đồ thị đầy đủ khi điều tra một thay đổi cụ thể.

Giới hạn độ sâu hiển thị:

```bash
git log --graph --oneline --decorate --all -30
```

Chỉ xem commit trên đường đi ancestry giữa hai mốc:

```bash
git log --ancestry-path base..feature/payment --oneline
```

`--ancestry-path` giới hạn kết quả vào các commit nằm trên đường tổ tiên giữa phạm vi, hữu ích khi branch có nhiều nhánh phụ và bạn chỉ quan tâm chuỗi liên quan đến một mốc cụ thể.

## 15. Những giới hạn cần nhớ khi đọc lịch sử

- **`--all` chỉ thấy refs local hiện có.** Branch chưa fetch hoặc refs bị server ẩn sẽ không xuất hiện.
- **Remote-tracking branch có thể cũ.** Chạy fetch trước khi kết luận remote đã hoặc chưa nhận commit.
- **Ngày commit không phải thứ tự cha-con.** Dùng graph/topological order để hiểu quan hệ lịch sử.
- **Rebase và cherry-pick tạo commit mới.** Nội dung patch có thể giống nhau nhưng OID và parent khác.
- **Rename được suy luận từ nội dung.** Ngưỡng similarity và lịch sử merge có thể làm cách hiển thị rename thay đổi.
- **Shallow clone có lịch sử bị giới hạn.** Đồ thị chỉ phản ánh phần commit đã có trong clone.
- **Reflog khác git log.** `git log` xem commit reachable từ revision/ref được chọn; `git reflog` ghi lại các lần ref local di chuyển và có thể giúp tìm commit không còn reachable từ branch.
- **Đồ thị không chứng minh chất lượng commit.** Nó mô tả quan hệ lịch sử, không cho biết test đã pass hay thay đổi có đúng hay không.

Nếu cần tìm commit đã bị bỏ khỏi branch sau reset, thử:

```bash
git reflog --all --date=local
```

Sau khi tìm được commit cần giữ, tạo branch cứu hộ để nó tiếp tục reachable:

```bash
git branch rescue/important-commit <COMMIT_ID>
```

## 16. Quy trình đọc lịch sử trong công việc hằng ngày

Khi nhận một branch mới hoặc chuẩn bị review pull request, bạn có thể đi theo trình tự:

**Bước 1: Xác định trạng thái hiện tại**

```bash
git status --short
git branch -vv
git remote -v
```

**Bước 2: Cập nhật thông tin remote nếu cần**

```bash
git fetch --all --prune
```

**Bước 3: Xem đồ thị tổng quan**

```bash
git log --graph --oneline --decorate --all --topo-order -40
```

**Bước 4: So sánh branch**

```bash
git log --left-right --oneline main...feature/payment
git merge-base main feature/payment
```

**Bước 5: Đọc commit và patch liên quan**

```bash
git log --stat --oneline main..feature/payment
git log -p main..feature/payment -- src/payment.js
```

**Bước 6: Ghi nhận kết luận**

Nêu rõ commit nào chỉ có trên feature, commit nào chỉ có trên main, merge base là gì và có merge commit hay không. Khi review, trỏ đến OID cụ thể thay vì chỉ mô tả “commit mới nhất”.

## 17. Bài tập thực hành

Trong một repository thử nghiệm, tạo lịch sử có branch `main`, branch `feature/search`, ít nhất ba commit trên mỗi nhánh và một merge commit.

1. Chạy `git log` và `git log --oneline --decorate` để so sánh mức thông tin.
2. Chạy `git log --graph --oneline --decorate --all` và xác định commit tách nhánh, commit đầu nhánh feature và merge commit.
3. Dùng `git branch -vv` để đối chiếu branch local với upstream nếu repository có remote.
4. So sánh `git log main..feature/search` với `git log feature/search..main`.
5. Chạy `git log --left-right --graph --oneline main...feature/search` và giải thích dấu `<`, `>`.
6. Dùng `git log --first-parent --graph --oneline main` để so sánh góc nhìn mainline với đồ thị đầy đủ.
7. Lọc lịch sử bằng `--author`, `--since`, `--grep` và `-S` hoặc `-G`.
8. Đổi tên một file trong repository, commit rồi dùng `git log --follow --oneline -- <path>` để xem lịch sử qua rename.
9. Tạo một commit mới trên branch, fetch remote và giải thích vì sao `origin/main` chỉ cập nhật sau khi fetch.

Bạn hoàn thành bài tập khi đọc được đồ thị commit, xác định được quan hệ giữa branch và merge, phân biệt được commit riêng của từng nhánh và chọn được bộ lọc `git log` phù hợp cho câu hỏi điều tra.
