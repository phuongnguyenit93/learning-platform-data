# So sánh đồ thị sau fast-forward, merge commit, squash và rebase

Khi tích hợp một branch tính năng vào branch chính, Git có nhiều cách tạo ra lịch sử khác nhau. Fast-forward chỉ di chuyển con trỏ branch khi lịch sử đã tuyến tính; merge commit tạo một commit có nhiều parent để ghi lại điểm hợp nhất; squash gom thay đổi thành một commit mới; rebase phát lại commit trên base mới và tạo mã commit mới. Các cách này có thể cho ra nội dung tệp giống nhau nhưng đồ thị commit, khả năng truy vết và cách các lần merge sau được xử lý sẽ khác nhau.

Để chọn đúng chiến lược, cần nhìn cả nội dung lẫn quan hệ ancestry. `git log --graph`, `git show`, `git merge-base` và `git rev-list` giúp đọc đồ thị thay vì chỉ nhìn danh sách commit theo thời gian. Bài thực hành này dùng cùng một tình huống để so sánh bốn kết quả và xác định khi nào mỗi cách phù hợp.

## 1. Bối cảnh chung và ký hiệu đồ thị

Giả sử repository bắt đầu từ commit `A`, sau đó tạo commit chung `B`. Từ `B`, nhóm phát triển tách hai nhánh:

- `main` tiếp tục nhận hai commit `M1` và `M2`.
- `feature/payment` có hai commit `F1` và `F2`.

Đồ thị trước khi tích hợp:

```text
             M1---M2  (main)
            /
A---B------+
     \
      F1---F2  (feature/payment)
```

Trong thực tế, nhánh có thể có nhiều commit hơn và các commit có thể chứa thay đổi ở nhiều tệp. Điều quan trọng là `main` và `feature/payment` đã phân kỳ sau `B`: `M2` không phải ancestor của `F2`, và `F2` cũng không phải ancestor của `M2`.

Một số khái niệm cần nhớ:

- **Parent:** commit cha được ghi bên trong commit hiện tại.
- **Ancestor:** commit có thể đi tới bằng cách lần theo các parent từ một commit khác.
- **Merge base:** ancestor chung tốt nhất Git dùng làm điểm cơ sở khi hợp nhất hai lịch sử.
- **Ref:** tên như `main` hoặc `feature/payment` trỏ đến một commit.
- **Reachability:** quan hệ có thể đi tới một commit từ ref hoặc commit gốc đã chọn.

Các phương pháp dưới đây có thể tạo cùng nội dung cuối cùng trên `main`, nhưng không nhất thiết tạo cùng parent hoặc cùng lịch sử.

## 2. Fast-forward: di chuyển ref, không tạo commit hợp nhất

Fast-forward chỉ khả thi khi tip của branch hiện tại là ancestor của branch được tích hợp. Khi đó, Git chỉ cần di chuyển ref của branch hiện tại tiến đến commit mới hơn; không cần tạo commit mới.

### Trường hợp fast-forward khả thi

Giả sử `feature/payment` được tạo từ `main` tại `B`, và trong lúc phát triển không có commit mới nào được thêm vào `main`:

```text
A---B  (main)
     \
      F1---F2  (feature/payment)
```

Vì `B` là ancestor của `F2`, `main` có thể tiến thẳng đến `F2`:

```text
A---B---F1---F2  (main, feature/payment)
```

Không có commit merge mới. Các commit `F1` và `F2` được giữ nguyên OID, parent và nội dung.

### Thực hiện fast-forward

Đứng trên `main` và chạy:

```bash
git switch main
git merge --ff-only feature/payment
```

`--ff-only` yêu cầu Git chỉ tích hợp nếu có thể fast-forward. Nếu lịch sử đã phân kỳ, lệnh bị từ chối thay vì tự tạo merge commit. Tùy chọn này hữu ích khi nhóm muốn lịch sử tuyến tính và muốn phát hiện sớm branch đã cũ so với `main`.

### Xác minh

```bash
git log --oneline --graph --decorate --all
git show -s --format="%H%n%P%n%s" main
```

Commit tip sau fast-forward vẫn là `F2`, và danh sách parent của nó không thay đổi. Fast-forward không có một commit hợp nhất riêng để đánh dấu thời điểm tích hợp.

### Khi nào phù hợp?

- Branch đích chưa có commit mới kể từ lúc branch tính năng được tạo.
- Nhóm muốn lịch sử tuyến tính, ít commit merge.
- Thay đổi đã được review ở nơi khác và không cần một merge commit để ghi lại điểm tích hợp.

Nếu `main` đã có `M1` và `M2` như đồ thị ban đầu, fast-forward trực tiếp từ `main` đến `F2` là không thể vì `M2` không phải ancestor của `F2`.

## 3. Merge commit: ghi lại điểm hợp nhất với hai parent

Khi hai branch đã phân kỳ, merge thông thường có thể tạo một merge commit. Commit này có hai parent: parent thứ nhất là tip branch hiện tại, parent thứ hai là tip branch được merge vào.

Từ đồ thị ban đầu:

```text
A---B---M1---M2---X  (main)
     \          /
      F1---F2---/    (feature/payment)
```

`X` là merge commit mới. Nó nối hai nhánh lịch sử, giữ nguyên các commit `M1`, `M2`, `F1`, `F2` và ghi lại rõ ràng rằng hai nhánh đã được hợp nhất.

### Thực hiện merge commit

```bash
git switch main
git merge --no-ff feature/payment
```

`--no-ff` yêu cầu tạo merge commit ngay cả khi Git có thể fast-forward. Trong tình huống hai branch đã phân kỳ, merge thông thường vốn cần merge commit; `--no-ff` làm ý định tạo điểm hợp nhất rõ ràng hơn trong trường hợp fast-forward cũng có thể xảy ra.

Nếu có conflict, Git dừng lại để bạn giải quyết. Sau khi sửa các tệp và stage kết quả:

```bash
git status
git add <resolved-paths>
git merge --continue
```

Hoặc hủy merge đang diễn ra nếu chưa muốn tiếp tục:

```bash
git merge --abort
```

Chỉ dùng `--abort` khi merge vẫn đang ở trạng thái chưa hoàn tất. Sau khi merge commit đã được tạo, đây không còn là cách quay lại.

### Xác minh parent

```bash
git show -s --format="commit: %H%nparents: %P%nsubject: %s" HEAD
```

Với merge commit thông thường, trường `parents` có hai OID. Xem đồ thị:

```bash
git log --oneline --graph --decorate --all
```

### Khi nào phù hợp?

- Cần giữ nguyên lịch sử branch và commit gốc.
- Muốn biết chính xác thời điểm một nhánh được tích hợp.
- Nhóm dùng merge commit làm mốc review, audit hoặc release.
- Cần giữ cấu trúc phân nhánh để hiểu các nhánh phát triển song song.

Đổi lại, lịch sử có thêm commit merge và đồ thị không tuyến tính. Nếu merge thường xuyên nhiều branch ngắn hạn, đồ thị có thể dày hơn.

## 4. Squash: gom thay đổi thành một commit mới

Squash merge lấy kết quả thay đổi của branch tính năng so với merge base, áp dụng vào branch đích và chuẩn bị một commit mới. Commit mới thường có một parent là tip hiện tại của branch đích. Các commit riêng lẻ trên branch tính năng không trở thành ancestor của commit squash.

Đồ thị sau squash có dạng:

```text
             M1---M2---S  (main)
            /
A---B------+
     \
      F1---F2  (feature/payment)
```

`S` là commit squash. Nội dung của `S` có thể tương đương với kết quả tích hợp `F1` và `F2`, nhưng `S` là object mới, có OID mới và chỉ có parent `M2`. Branch `feature/payment` vẫn trỏ đến `F2` nếu chưa xóa hoặc di chuyển ref.

### Thực hiện squash merge

```bash
git switch main
git merge --squash feature/payment
git status
git diff --cached
git commit -m "feat: add payment workflow"
```

`git merge --squash` chuẩn bị thay đổi trong index và working tree như kết quả merge, nhưng không tạo merge commit và không di chuyển `HEAD`. Bạn phải tạo commit riêng bằng `git commit`.

Nếu có conflict trong quá trình squash, giải quyết nội dung rồi stage các tệp đã xử lý. Sau đó kiểm tra staged diff và commit. Vì không có merge commit được tạo, `git merge --continue` không phải bước kết thúc squash như merge thông thường; hãy dùng `git commit` sau khi kết quả đã sẵn sàng.

### Xác minh parent và nội dung

```bash
git show -s --format="commit: %H%nparents: %P%nsubject: %s" HEAD
git show --stat --oneline HEAD
```

Commit `S` thường chỉ có một parent là `M2`. Để kiểm tra thay đổi mà feature đóng góp so với base, hãy so sánh base chung với tip feature trước khi tích hợp:

```bash
git diff B feature/payment
```

Trong lệnh thực tế, thay `B` bằng OID hoặc ref trỏ đến commit base đã ghi lại. Diff nội dung cho biết thay đổi của feature, còn parent của `S` cho biết quan hệ ancestry đã được lưu như thế nào.

### Hệ quả với các lần merge sau

Vì `F2` không trở thành ancestor của `S`, Git không ghi nhận branch feature đã được hợp nhất theo quan hệ ancestry. Nếu tiếp tục phát triển trên `feature/payment` rồi merge lại, Git có thể xem các commit `F1` và `F2` vẫn nằm ngoài lịch sử `main`, và tính toán thay đổi dựa trên merge base cũ. Các thay đổi đã squash có thể xuất hiện lại trong diff hoặc gây conflict, tùy nội dung và lịch sử tiếp theo.

Với workflow squash, nhóm thường xóa branch feature sau khi tích hợp hoặc tạo branch mới từ `main` cho công việc tiếp theo. Không nên tiếp tục tái sử dụng branch cũ mà không hiểu hệ quả ancestry.

### Khi nào phù hợp?

- Branch tính năng có nhiều commit thử nghiệm, sửa nhỏ hoặc commit trung gian.
- Nhóm muốn một commit rõ mục đích trên branch chính.
- Pull request/merge request đã lưu lịch sử review và thảo luận ở hosting.
- Chính sách dự án ưu tiên lịch sử `main` gọn và dễ đọc.

Squash làm mất cấu trúc ancestry của các commit feature trong branch đích. Nếu cần audit từng commit hoặc giữ quan hệ branch, merge commit phù hợp hơn.

## 5. Rebase: phát lại commit trên base mới

Rebase lấy các commit của branch tính năng chưa có trong base mới, rồi phát lại chúng trên tip của base đó. Mỗi commit được tạo lại có thể có OID mới vì parent thay đổi; metadata như committer và thời gian cũng có thể khác.

Từ đồ thị ban đầu, rebase `feature/payment` lên `main`:

```bash
git switch feature/payment
git rebase main
```

Đồ thị sau rebase:

```text
A---B---M1---M2---F1'---F2'  (feature/payment)
            (main)
```

`F1'` và `F2'` là commit mới được tạo lại trên `M2`. Commit gốc `F1` và `F2` không còn nằm trên branch feature sau rebase, nhưng có thể vẫn được tìm thấy qua reflog trong một thời gian. Nội dung thay đổi có thể tương đương, nhưng OID và quan hệ parent khác.

### Tích hợp sau rebase

Sau khi rebase thành công, `main` là ancestor của `F2'`, nên có thể fast-forward:

```bash
git switch main
git merge --ff-only feature/payment
```

Kết quả trên `main` là lịch sử tuyến tính:

```text
A---B---M1---M2---F1'---F2'  (main, feature/payment)
```

Rebase không tự tích hợp branch vào `main`; nó di chuyển lịch sử branch feature. Lệnh merge fast-forward sau đó mới di chuyển `main` đến tip mới.

### Xử lý conflict trong rebase

Nếu một commit phát lại bị conflict, Git tạm dừng:

```bash
git status
```

Sửa các tệp conflict, stage kết quả và tiếp tục:

```bash
git add <resolved-paths>
git rebase --continue
```

Nếu muốn bỏ toàn bộ lần rebase đang diễn ra và quay về trạng thái trước khi bắt đầu:

```bash
git rebase --abort
```

Không dùng `--abort` sau khi rebase đã hoàn tất. Nếu cần quay lại commit trước rebase sau khi hoàn tất, tra reflog và tạo branch cứu hộ trước khi di chuyển ref.

### Khi nào phù hợp?

- Muốn cập nhật branch feature trên base mới trước khi tích hợp.
- Muốn lịch sử tuyến tính và dễ đọc.
- Nhánh feature chưa chia sẻ rộng hoặc nhóm thống nhất cho phép viết lại lịch sử.
- Muốn giải quyết conflict theo từng commit thay vì một lần merge lớn.

Không rebase tùy tiện branch đã được nhiều người khác dựa vào. Vì OID thay đổi, việc push lại thường cần cập nhật cưỡng bức có kiểm soát và có thể làm ảnh hưởng clone của cộng tác viên.

## 6. So sánh bốn đồ thị trên cùng một tình huống

Với hai branch đã phân kỳ tại `B`, kết quả có thể tóm tắt:

| Phương pháp | Kết quả trên branch đích | Parent của commit tích hợp mới | Giữ OID commit feature? | Ghi nhận ancestry feature? |
|---|---|---:|---|---|
| Fast-forward | Di chuyển ref đến tip feature khi tip hiện tại là ancestor | Không tạo commit mới | Có | Có, vì các commit feature nằm trên lịch sử đích |
| Merge commit | Tạo merge commit nối hai lịch sử | Hai parent | Có | Có, branch feature trở thành ancestor qua merge commit |
| Squash | Tạo commit mới chứa kết quả thay đổi | Thường một parent | Không đưa các commit feature vào lịch sử đích | Không ghi nhận ancestry của các commit feature |
| Rebase rồi fast-forward | Tạo lại commit feature trên base mới, sau đó di chuyển ref đích | Các commit được replay thường có một parent; không cần merge commit | Không, OID commit replay thay đổi | Có, các commit mới nằm trên lịch sử đích sau fast-forward |

Điểm cần phân biệt: **fast-forward là cách cập nhật ref**, còn **merge commit và squash là cách tạo kết quả tích hợp**. Rebase là thao tác viết lại commit trên branch nguồn; sau đó thường kết hợp fast-forward để cập nhật branch đích.

## 7. Kiểm tra ancestry bằng merge-base và rev-list

Để xác định hai branch có phân kỳ không, xem merge base:

```bash
git merge-base main feature/payment
```

Lệnh trả về OID của ancestor chung tốt nhất. Nếu `main` tip chính là merge base, `main` là ancestor của feature và có thể fast-forward từ `main` sang feature (nếu không có điều kiện khác ngăn cản).

Kiểm tra quan hệ ancestor trực tiếp:

```bash
git merge-base --is-ancestor main feature/payment
```

Exit code `0` nghĩa là `main` là ancestor của `feature/payment`; exit code khác `0` nghĩa là không có quan hệ ancestor theo chiều đó hoặc có lỗi cần kiểm tra. Có thể đảo thứ tự để kiểm tra chiều ngược lại.

Đếm commit chỉ có ở mỗi phía:

```bash
git rev-list --left-right --count main...feature/payment
```

Output có hai số: số commit chỉ reachable từ `main` và số commit chỉ reachable từ `feature/payment` so với merge base. Với đồ thị ban đầu, cả hai phía đều có commit riêng.

Xem commit nào thuộc bên nào:

```bash
git log --left-right --oneline main...feature/payment
```

Các commit có dấu `<` chỉ ở phía `main`; dấu `>` chỉ ở phía `feature/payment`. Đây là cách hữu ích để kiểm kê trước khi quyết định merge, squash hay rebase.

## 8. Xác minh số parent và đồ thị commit

Một commit bình thường thường có một parent; commit root không có parent; merge commit thông thường có từ hai parent trở lên. Dùng:

```bash
git show -s --format="%H%n%P%n%s" <commit>
```

Trong đó `%H` là OID đầy đủ của commit, `%P` là danh sách OID parent và `%s` là subject.

Để xem toàn bộ đồ thị branch/tag:

```bash
git log --oneline --graph --decorate --all
```

Để so sánh hai dải commit trước và sau rebase:

```bash
git range-diff <old-base>..<old-tip> <new-base>..feature/payment
```

`git range-diff` giúp ghép các commit tương ứng và chỉ ra commit nào được giữ tương tự, thay đổi hoặc không còn tương ứng sau rebase. Hãy lưu OID/base cũ trước khi rebase để so sánh có ý nghĩa.

Để so sánh nội dung cuối cùng giữa hai branch:

```bash
git diff main feature/payment
```

Diff nội dung không cho biết đầy đủ cấu trúc ancestry. Hai branch có thể có tree giống nhau nhưng đồ thị commit khác nhau. Vì vậy, hãy kết hợp `git diff` với `git log --graph`, `git show` và `git merge-base`.

## 9. Thực hành trong repository thử nghiệm

Để quan sát bốn kết quả mà không làm thay đổi repository dự án, tạo một repository thực hành riêng. Ví dụ dưới đây dùng shell kiểu Bash:

```bash
mkdir git-merge-strategies
cd git-merge-strategies
git init -b main
git config user.name "Git Practice"
git config user.email "git-practice@example.com"

echo "base" > README.md
git add README.md
git commit -m "chore: create base"
```

Để tạo đúng đồ thị phân kỳ, tạo branch feature ngay tại commit base trước khi thêm commit riêng cho main:

```bash
git switch -c feature/payment
echo "payment module" > payment.txt
git add payment.txt
git commit -m "feat: add payment module"

echo "retry handling" >> payment.txt
git add payment.txt
git commit -m "feat: add payment retry"

git switch main
echo "operations notes" > operations.txt
git add operations.txt
git commit -m "docs: add operations notes"

echo "deployment notes" >> operations.txt
git add operations.txt
git commit -m "docs: add deployment notes"
```

Đồ thị lúc này có hai commit riêng trên mỗi nhánh. Hai nhánh sửa các tệp khác nhau nên có thể tập trung quan sát cấu trúc merge mà không chủ động tạo conflict nội dung. Từ cùng một base, có thể tạo các bản sao lab riêng cho từng chiến lược để so sánh kết quả mà không phải reset lịch sử giữa các lần thử.

Trong mỗi lab, kiểm tra:

```bash
git log --oneline --graph --decorate --all
git show -s --format="%H %P %s" HEAD
git rev-list --left-right --count main...feature/payment
```

Không cần dùng repository thật để thử `reset --hard`, force-push hoặc thao tác viết lại lịch sử. Repository lab giúp bạn quan sát đồ thị và kiểm tra parent mà không ảnh hưởng công việc đang làm.

## 10. Chọn chiến lược theo yêu cầu nhóm

| Tiêu chí | Fast-forward | Merge commit | Squash | Rebase rồi FF |
|---|---|---|---|---|
| Lịch sử tuyến tính | Có | Không | Có trên branch đích | Có |
| Giữ commit feature gốc | Có | Có | Không trong ancestry đích | Không, tạo commit mới |
| Có điểm merge riêng | Không | Có | Không | Không |
| Hiển thị branch đã phân kỳ | Không, chỉ dùng khi không phân kỳ | Có | Không | Đồ thị đích được tuyến tính hóa |
| Phù hợp branch đã chia sẻ | Có | Có | Có thể, nhưng cần thống nhất cách tiếp tục branch | Cần thận trọng vì viết lại commit |
| Dễ truy vết từng commit feature | Có | Có | Ít hơn trên branch đích | Có qua commit mới, cần range-diff nếu so lịch sử cũ |

Gợi ý lựa chọn:

- Chọn **fast-forward** khi branch đích chưa tiến lên và nhóm muốn chỉ di chuyển ref.
- Chọn **merge commit** khi cần lưu dấu điểm tích hợp và giữ nguyên lịch sử hai nhánh.
- Chọn **squash** khi muốn một commit tổng hợp trên branch chính và không cần ancestry của từng commit feature ở branch đích.
- Chọn **rebase** khi muốn đặt lại các commit feature trên base mới, branch chưa chia sẻ rộng hoặc nhóm có quy ước rõ ràng về viết lại lịch sử.

Không có một chiến lược tốt nhất cho mọi dự án. Hãy chọn theo nhu cầu audit, cách review, tần suất tích hợp, quy mô cộng tác và chính sách branch.

## 11. Những lỗi suy luận thường gặp

| Nhận định sai | Điều cần kiểm tra |
|---|---|
| Fast-forward luôn tạo merge commit | Fast-forward chỉ di chuyển ref, không tạo commit mới |
| Merge commit làm thay đổi OID các commit branch | Merge commit giữ nguyên commit cũ và thêm một commit có nhiều parent |
| Squash tương đương merge commit vì nội dung cuối giống nhau | Squash tạo commit một parent và không ghi nhận ancestry của feature commits |
| Rebase chỉ đổi vị trí branch | Rebase replay commit và tạo OID mới vì parent/nội dung metadata thay đổi |
| Rebase tự đưa thay đổi vào main | Rebase cập nhật branch đang rebase; cần merge/fast-forward riêng để di chuyển branch đích |
| Hai branch có tree giống nhau nghĩa là lịch sử giống nhau | Nội dung snapshot có thể giống nhưng parent và ancestry khác |
| `git log --oneline` đủ để phân biệt mọi chiến lược | Cần `--graph`, `%P`, `merge-base` hoặc `rev-list` để xem cấu trúc |
| Có thể rebase an toàn branch mà nhiều người đang dựa vào | Rebase thay OID và có thể buộc cộng tác viên đồng bộ lại lịch sử |

## 12. Ghi nhớ

Fast-forward chỉ cập nhật ref khi tip hiện tại là ancestor của tip được tích hợp. Merge commit giữ nguyên hai lịch sử và thêm commit có hai parent. Squash tạo một commit mới chứa kết quả thay đổi nhưng không ghi nhận ancestry của các commit feature. Rebase phát lại commit trên base mới, tạo OID mới; sau đó thường dùng fast-forward để cập nhật branch đích.

Để đọc kết quả, dùng `git log --graph --decorate --all`, `git show -s --format="%H %P %s"`, `git merge-base`, `git merge-base --is-ancestor`, `git rev-list --left-right --count` và `git range-diff`. Luôn phân biệt nội dung cuối cùng với cấu trúc lịch sử: cùng một tree không có nghĩa là cùng đồ thị commit. Chọn chiến lược tích hợp dựa trên yêu cầu cộng tác và khả năng truy vết của nhóm.
