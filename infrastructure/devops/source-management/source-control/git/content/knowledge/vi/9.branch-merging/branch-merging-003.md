# Hợp nhất có merge commit và lựa chọn `--ff-only`, `--no-ff`

Khi tích hợp một branch vào branch hiện tại, Git có thể **di chuyển ref theo kiểu fast-forward** hoặc **tạo merge commit** để ghi nhận điểm hợp nhất của hai dòng lịch sử. Cách Git chọn phụ thuộc vào quan hệ giữa hai tip và chính sách bạn yêu cầu bằng `--ff`, `--ff-only` hoặc `--no-ff`.

Ba lựa chọn này quyết định hình dạng lịch sử, không quyết định nội dung code nào đúng. Dù chọn cách nào, bạn vẫn cần kiểm tra branch nguồn, trạng thái working tree, kết quả merge và các conflict nếu có.

Bài này thuộc chương **Hợp nhất nhánh** của SOURCE_CONTROL_GIT. Nội dung tập trung vào điều kiện fast-forward, cấu trúc merge commit, sự khác nhau giữa ba tùy chọn, cấu hình mặc định và quy trình chọn chính sách phù hợp cho từng branch.

## 1. Hai cách Git có thể tích hợp branch

Giả sử `main` và `feature/login` cùng xuất phát từ commit `B`. Branch feature có thêm hai commit `C`, `D`; trong lúc đó `main` chưa có commit mới:

```text
A---B---C---D  feature/login
    ^
    main
```

Tip của `main` là tổ tiên của tip `feature/login`. Git có thể cập nhật `main` từ `B` lên `D` mà không cần tạo commit mới. Đây là **fast-forward**.

Nếu `main` cũng có commit riêng:

```text
      E---F  main
     /
A---B
     \
      C---D  feature/login
```

Hai branch đã phân kỳ. Không thể chỉ di chuyển `main` tới `D` mà vẫn giữ commit `E`, `F` trên lịch sử. Git cần tạo merge commit (hoặc người dùng chọn một quy trình khác như rebase).

### 1.1. Fast-forward

Fast-forward chỉ di chuyển branch ref tới một commit đã tồn tại:

```text
Trước:
A---B---C---D  feature/login
    ^
    main

Sau:
A---B---C---D  main, feature/login
```

Không có commit mới. OID của `D` không thay đổi; chỉ ref `main` được cập nhật từ `B` sang `D`.

### 1.2. Merge commit

Khi hai branch phân kỳ, Git kết hợp hai dòng lịch sử bằng một commit mới:

```text
      E---F------M  main
     /          /
A---B          /
     \        /
      C---D---   feature/login
```

Commit `M` là merge commit có hai parent:

1. Parent thứ nhất là tip của branch đang checkout trước khi merge (`F` trên `main`).
2. Parent thứ hai là tip branch được merge vào (`D` trên `feature/login`).

Tree của `M` là snapshot kết quả hợp nhất. Nó có thể chứa thay đổi từ cả hai branch và cả phần bạn chỉnh khi giải quyết conflict.

## 2. Điều kiện để fast-forward

Một merge có thể fast-forward khi tip của branch hiện tại là tổ tiên của tip branch nguồn. Nếu đang ở `main` và muốn merge `feature/login`, điều kiện là:

```bash
git merge-base --is-ancestor HEAD feature/login
```

Exit status `0` nghĩa là `HEAD` là tổ tiên của `feature/login`, vì vậy fast-forward có thể thực hiện. Exit status `1` nghĩa là không có quan hệ tổ tiên theo chiều đó; merge không thể fast-forward theo hướng này. Các mã khác có thể báo lỗi phân giải revision hoặc repository.

Kiểm tra chiều ngược lại để biết branch nguồn đã nằm trong lịch sử hiện tại chưa:

```bash
git merge-base --is-ancestor feature/login HEAD
```

Nếu lệnh này trả `0`, `feature/login` đã là tổ tiên của `HEAD`; thường không còn gì mới cần tích hợp và Git sẽ báo `Already up to date`.

### 2.1. Xem số commit riêng của mỗi bên

```bash
git rev-list --left-right --count HEAD...feature/login
```

Lệnh trả hai con số:

- Số commit chỉ có ở phía trái (`HEAD`).
- Số commit chỉ có ở phía phải (`feature/login`).

Ví dụ `0  3` cho biết `HEAD` không có commit riêng so với feature và feature có ba commit chưa nằm trong `HEAD`; đây là tình huống fast-forward có thể xảy ra nếu không có ràng buộc khác. Kết quả `2  3` cho thấy hai bên đều có commit riêng, tức đã phân kỳ.

### 2.2. Cập nhật thông tin remote trước khi quyết định

Nếu branch nguồn nằm trên remote, fetch trước để remote-tracking ref phản ánh trạng thái mới nhất mà máy local vừa nhận được:

```bash
git fetch origin
git log --graph --oneline --decorate --all
```

Ví dụ merge `origin/feature/login` vào `main`:

```bash
git switch main
git merge --ff-only origin/feature/login
```

`origin/feature/login` là ref local được cập nhật bởi lần fetch gần nhất; nó không tự truy vấn server tại thời điểm gọi `git merge`.

## 3. Hành vi mặc định và tùy chọn `--ff`

Tùy chọn `--ff` cho phép fast-forward khi có thể. Nếu hai branch đã phân kỳ, Git tạo merge commit theo quy trình merge thông thường.

```bash
git switch main
git merge --ff feature/login
```

Đây là hành vi mặc định phổ biến khi `merge.ff` chưa được cấu hình khác:

- Nếu `HEAD` là tổ tiên của branch nguồn, di chuyển ref (fast-forward).
- Nếu hai branch phân kỳ, tạo merge commit sau khi hợp nhất nội dung.
- Nếu branch nguồn đã được tích hợp, không tạo commit mới.

`--ff` không có nghĩa là “chỉ cho phép fast-forward”. Nếu không thể fast-forward, Git vẫn có thể tạo merge commit. Muốn từ chối khi hai branch phân kỳ, dùng `--ff-only`.

## 4. Chỉ cho phép fast-forward bằng `--ff-only`

`--ff-only` yêu cầu Git chỉ cập nhật branch nếu có thể fast-forward. Nếu hai branch phân kỳ, Git dừng và báo không thể fast-forward; nó không tự tạo merge commit và cũng không tự rebase.

```bash
git switch main
git merge --ff-only feature/login
```

### 4.1. Khi fast-forward thành công

Trước:

```text
A---B---C  feature/login
    ^
    main
```

Sau `git merge --ff-only feature/login`:

```text
A---B---C  main, feature/login
```

`main` di chuyển tới `C`. Không có merge commit mới.

### 4.2. Khi hai branch phân kỳ

```text
      E---F  main
     /
A---B
     \
      C---D  feature/login
```

Lệnh:

```bash
git merge --ff-only feature/login
```

sẽ bị từ chối vì `main` có commit `E`, `F` không nằm trong lịch sử của `feature/login`. Git giữ nguyên branch và yêu cầu bạn xử lý quan hệ lịch sử trước.

Các lựa chọn tiếp theo có thể là:

- Fetch và xem lại lịch sử, sau đó dùng merge commit nếu chính sách cho phép.
- Rebase branch feature lên nền mới rồi thử fast-forward.
- Yêu cầu nhóm cập nhật branch theo quy trình tích hợp đã thống nhất.

Không nên dùng `reset --hard` hoặc force push chỉ để làm cho `--ff-only` chạy được. Trước tiên cần hiểu commit nào đang có ở mỗi phía.

### 4.3. Khi nào nên dùng `--ff-only`?

`--ff-only` phù hợp khi nhóm muốn branch đích có lịch sử tuyến tính và mọi thay đổi tích hợp phải được chuẩn bị trước để có thể tiến tới tip mới mà không tạo merge commit. Ví dụ:

- Cập nhật branch local từ một branch upstream đã được tổ chức tuyến tính.
- Đồng bộ branch triển khai mà chính sách không cho phép merge commit.
- Kiểm tra branch có thể tiến tới một tip mới mà không cần giải quyết lịch sử phân kỳ.
- Dùng trong script để tránh tự động tạo merge commit ngoài ý muốn.

Nếu chính sách yêu cầu merge commit cho mọi lần tích hợp feature, `--ff-only` không phù hợp.

## 5. Buộc tạo merge commit bằng `--no-ff`

`--no-ff` yêu cầu tạo merge commit ngay cả khi Git có thể fast-forward. Điều này lưu lại một mốc tích hợp riêng và giữ ranh giới giữa branch đích với branch feature trong đồ thị commit.

```bash
git switch main
git merge --no-ff feature/login
```

### 5.1. Khi fast-forward có thể xảy ra

Trước:

```text
A---B---C---D  feature/login
    ^
    main
```

Với `--no-ff`, Git tạo merge commit `M`:

```text
A---B---------M  main
     \       /
      C---D     feature/login
```

`M` có hai parent: `B` và `D`. Tree của `M` thường giống tree của `D` trong trường hợp không có thay đổi bổ sung hoặc conflict cần chỉnh sửa, nhưng OID của `M` khác vì nó có hai parent và metadata riêng.

### 5.2. Khi hai branch đã phân kỳ

Nếu hai branch đã có commit riêng, merge thông thường vốn đã cần tạo merge commit. Trong tình huống đó, `--no-ff` không làm thay đổi bản chất kết quả so với `--ff` mặc định: Git vẫn tạo merge commit sau khi kết hợp hai dòng lịch sử.

Điểm khác biệt quan trọng của `--no-ff` xuất hiện khi fast-forward có thể xảy ra. Nó yêu cầu ghi một merge commit thay vì chỉ di chuyển ref.

### 5.3. Khi branch nguồn đã được tích hợp

Nếu tip branch nguồn đã là tổ tiên của `HEAD`, Git báo `Already up to date`. `--no-ff` không tạo merge commit mới chỉ để ghi lại một lần merge không có thay đổi mới.

### 5.4. Vì sao nhóm chọn `--no-ff`?

Một số lợi ích:

- Lịch sử thể hiện rõ feature branch đã được tích hợp tại đâu.
- Có thể đọc lịch sử tích hợp bằng `git log --first-parent`.
- Một nhóm commit feature có thể được nhìn như một đơn vị tích hợp.
- Việc revert một lần tích hợp có thể được tổ chức theo merge commit, nếu hiểu đúng mainline parent.
- Audit hoặc release review có thể dễ nhận diện ranh giới feature.

Đổi lại, lịch sử có thêm merge commit và đồ thị nhiều nhánh hơn. Với feature nhỏ hoặc nhóm muốn lịch sử tuyến tính, việc tạo merge commit cho mọi lần tích hợp có thể làm log dài và khó quét hơn.

## 6. So sánh `--ff`, `--ff-only` và `--no-ff`

| Tùy chọn | Nếu fast-forward được | Nếu hai branch phân kỳ | Nếu branch nguồn đã nằm trong HEAD |
|---|---|---|---|
| `--ff` | Fast-forward, không tạo commit mới. | Tạo merge commit. | Không làm gì (`Already up to date`). |
| `--ff-only` | Fast-forward, không tạo commit mới. | Từ chối, không tạo merge commit. | Không làm gì (`Already up to date`). |
| `--no-ff` | Tạo merge commit. | Tạo merge commit. | Không tạo commit mới. |

Tóm tắt:

- Muốn Git tự chọn fast-forward nếu có thể và merge commit nếu cần: dùng `--ff` (thường là mặc định).
- Muốn chỉ cho phép fast-forward, nếu không được thì dừng: dùng `--ff-only`.
- Muốn giữ merge commit cho một lần tích hợp ngay cả khi có thể fast-forward: dùng `--no-ff`.

## 7. Cấu hình mặc định bằng `merge.ff`

Bạn có thể cấu hình hành vi merge mặc định trong Git config:

```bash
git config --get merge.ff
```

Các giá trị thường dùng:

| Giá trị | Hành vi tương đương |
|---|---|
| `true` | Cho phép fast-forward khi có thể; nếu phân kỳ thì tạo merge commit. |
| `false` | Tương đương `--no-ff`. |
| `only` | Tương đương `--ff-only`. |

Đặt cho repository hiện tại:

```bash
git config --local merge.ff only
```

Đặt cho mọi repository của người dùng:

```bash
git config --global merge.ff false
```

Xem nguồn cấu hình:

```bash
git config --show-origin --show-scope --get merge.ff
```

Nếu cấu hình không có giá trị, hành vi mặc định là cho phép fast-forward khi có thể. Tùy chọn ghi trực tiếp trên dòng lệnh như `--ff`, `--ff-only` hoặc `--no-ff` cho phép chọn hành vi cho một lần merge và ghi đè cấu hình mặc định.

### 7.1. Chọn scope phù hợp

- `--local`: chỉ ảnh hưởng repository hiện tại.
- `--global`: ảnh hưởng các repository của người dùng, trừ khi cấu hình cấp khác ghi đè.
- `--system`: ảnh hưởng toàn hệ thống và thường cần quyền quản trị.

Chính sách merge khác nhau giữa branch cá nhân, branch tích hợp và branch phát hành. Cấu hình local thường phù hợp hơn nếu chỉ một repository có yêu cầu riêng.

### 7.2. `merge.ff` và `pull.ff`

`git merge` sử dụng `merge.ff`. `git pull` có thể có cấu hình riêng `pull.ff` để điều khiển hành vi fast-forward của bước tích hợp sau fetch. Nếu bạn thấy `git merge` và `git pull` có hành vi khác nhau, kiểm tra cả hai cấu hình:

```bash
git config --show-origin --get merge.ff
git config --show-origin --get pull.ff
```

Đừng giả định mọi thiết lập `merge.ff` đều là cấu hình duy nhất tác động đến `git pull`.

## 8. Review merge trước khi tạo commit

Trong một số workflow, nhóm muốn kiểm tra snapshot hợp nhất và chạy test trước khi ghi merge commit. Dùng:

```bash
git merge --no-commit --no-ff feature/login
```

`--no-commit` yêu cầu dừng trước bước tạo merge commit. Kết hợp `--no-ff` để bảo đảm Git không fast-forward; fast-forward không tạo commit nên không có điểm dừng trước commit.

Sau khi merge chuẩn bị xong:

```bash
git status
git diff --cached --stat
git diff --cached
git diff
```

Chạy test và kiểm tra snapshot. Nếu kết quả đúng, hoàn tất:

```bash
git commit
```

Nếu cần hủy merge đang dừng:

```bash
git merge --abort
```

Trước khi merge, nên bảo toàn các sửa đổi local. Thay đổi chưa commit có thể làm quá trình merge bị từ chối hoặc khiến việc quay lại trạng thái ban đầu phức tạp hơn.

## 9. Xử lý conflict khi tạo merge commit

Khi hai branch sửa cùng vùng nội dung theo cách Git không thể tự kết hợp, merge dừng để bạn giải quyết conflict. Chính sách `--ff`, `--ff-only` và `--no-ff` không tự giải quyết conflict; chúng quyết định cách cập nhật lịch sử khi merge có thể hoàn tất.

Kiểm tra trạng thái:

```bash
git status
git ls-files -u
```

Mở tệp conflict, chọn hoặc kết hợp nội dung mong muốn, rồi stage kết quả:

```bash
git add -- src/login.js
```

Khi tất cả conflict đã được giải quyết:

```bash
git diff --cached
git merge --continue
```

Nếu phiên bản Git hoặc trạng thái merge yêu cầu hoàn tất trực tiếp bằng commit, `git commit` cũng có thể dùng để ghi merge commit. Không tạo commit cho tới khi mọi đường dẫn conflict đã được xử lý và stage.

Muốn hủy merge:

```bash
git merge --abort
```

## 10. Xác minh loại merge sau khi hoàn tất

### 10.1. Xem đồ thị lịch sử

```bash
git log --graph --oneline --decorate --all
```

Fast-forward làm branch ref tiến tới commit đã tồn tại; không có nút merge mới. Merge commit tạo một nút mới nối hai dòng lịch sử.

### 10.2. Kiểm tra parent của HEAD

```bash
git rev-list --parents -n 1 HEAD
```

Kết quả gồm OID commit đầu tiên và các OID parent sau đó:

- Một parent: commit thông thường (hoặc commit rỗng về nội dung).
- Hai parent: merge commit thông thường.
- Ba parent trở lên: octopus merge hoặc merge nhiều đầu vào.
- Không có parent: root commit.

### 10.3. Xem raw merge commit

```bash
git show --no-patch --pretty=raw HEAD
```

Kiểm tra các dòng `parent` để xác định parent thứ nhất và thứ hai. Parent thứ nhất thường là tip branch đích trước merge; parent thứ hai là tip branch nguồn.

### 10.4. Đọc lịch sử tích hợp theo first-parent

```bash
git log --first-parent --oneline --decorate main
```

Nếu nhóm dùng `--no-ff`, first-parent history giúp xem các mốc merge commit trên branch chính mà không đi sâu vào toàn bộ commit bên trong feature branch.

### 10.5. So sánh kết quả merge với từng parent

```bash
git diff HEAD^1 HEAD
git diff HEAD^2 HEAD
```

Lệnh thứ nhất cho biết kết quả merge khác branch đích trước merge ra sao. Lệnh thứ hai cho biết kết quả khác branch nguồn ra sao. Với fast-forward, không có merge commit mới để kiểm tra hai parent; hãy xem ref đang trỏ tới commit nào.

## 11. Merge commit và hoàn tác

Merge commit có nhiều parent nên khi revert cần chọn mainline parent. Ví dụ muốn hoàn tác nội dung tích hợp vào `main`:

```bash
git revert -m 1 <merge-commit>
```

`-m 1` chọn parent thứ nhất làm mainline. Git tạo commit mới đảo ngược thay đổi của merge so với parent đó; nó không xóa merge commit khỏi lịch sử.

Nếu chọn nhầm parent, nội dung bị đảo ngược có thể không đúng ý định. Trước khi revert, xem:

```bash
git show --no-patch --pretty=raw <merge-commit>
git diff <merge-commit>^1 <merge-commit>
git diff <merge-commit>^2 <merge-commit>
```

Fast-forward không tạo merge commit, nên không có một merge node riêng để revert bằng `-m`. Nếu cần hoàn tác các commit đã fast-forward, thường phải revert các commit liên quan hoặc tạo một commit sửa đổi phù hợp.

## 12. Chọn chính sách theo quy trình nhóm

| Tình huống | Lựa chọn gợi ý | Lý do |
|---|---|---|
| Muốn lịch sử tuyến tính và dừng nếu branch phân kỳ | `--ff-only` | Không tự tạo merge commit ngoài dự kiến. |
| Muốn Git fast-forward khi có thể, merge commit khi cần | `--ff` | Linh hoạt, là hành vi mặc định phổ biến. |
| Muốn mỗi feature integration có mốc riêng | `--no-ff` | Giữ merge node và ranh giới feature. |
| Branch chính chỉ nhận commit đã được rebase lên tip mới | `--ff-only` | Xác nhận branch đích có thể tiến thẳng tới tip feature. |
| Cần audit theo từng lần tích hợp | `--no-ff` | Dễ lọc merge commit và first-parent history. |
| Script chỉ được phép cập nhật tuyến tính | `--ff-only` | Từ chối khi lịch sử bất ngờ phân kỳ. |

Không có chính sách duy nhất phù hợp cho mọi repository. Hãy thống nhất quy tắc với nhóm và áp dụng nhất quán trên branch tích hợp/phát hành.

## 13. Quy trình thực hành: tích hợp feature vào main

Giả sử `feature/login` đã hoàn thành và cần tích hợp vào `main` bằng merge commit để giữ ranh giới feature.

**Bước 1: Bảo đảm trạng thái local rõ ràng**

```bash
git status --short --branch
```

Commit hoặc stash các thay đổi cần giữ trước khi merge.

**Bước 2: Cập nhật branch nguồn từ remote nếu cần**

```bash
git fetch origin
git log --graph --oneline --decorate --all
```

**Bước 3: Chuyển sang branch đích**

```bash
git switch main
```

**Bước 4: Kiểm tra quan hệ lịch sử**

```bash
git rev-list --left-right --count HEAD...feature/login
git merge-base HEAD feature/login
```

**Bước 5: Tạo merge commit ngay cả khi fast-forward được**

```bash
git merge --no-ff feature/login
```

Nếu có conflict, giải quyết từng tệp, stage kết quả và tiếp tục merge.

**Bước 6: Xác minh kết quả**

```bash
git log --graph --oneline --decorate -10
git rev-list --parents -n 1 HEAD
git show --stat --oneline HEAD
git status --short --branch
```

Nếu chính sách của nhóm yêu cầu tuyến tính, thay bước 5 bằng:

```bash
git merge --ff-only feature/login
```

Lệnh sẽ dừng nếu branch đã phân kỳ, để nhóm xử lý lịch sử trước khi tích hợp.

## 14. Các lỗi thường gặp

### 14.1. `--ff-only` bị từ chối

Hai branch đã phân kỳ hoặc tip hiện tại không phải tổ tiên của branch nguồn. Fetch, xem đồ thị và quyết định merge commit hay rebase theo chính sách. Không reset hoặc force push chỉ để bỏ qua cảnh báo.

### 14.2. Dùng `--ff` nhưng vẫn xuất hiện merge commit

Đây là hành vi bình thường nếu hai branch đã phân kỳ. `--ff` chỉ fast-forward khi có thể; nó không cấm merge commit.

### 14.3. Dùng `--no-ff` nhưng không thấy merge commit mới

Nếu branch nguồn đã nằm trong lịch sử HEAD, Git báo `Already up to date`. Không có thay đổi mới để tích hợp nên `--no-ff` không tạo commit rỗng.

### 14.4. Nghĩ `--no-commit` luôn dừng trước commit

Fast-forward không tạo commit nên `--no-commit` không thể dừng trước một commit không tồn tại. Dùng `--no-commit --no-ff` khi cần kiểm tra kết quả trong một merge commit.

### 14.5. Cấu hình global ghi đè kỳ vọng của repository

Kiểm tra `merge.ff` với `--show-origin` và `--show-scope`. Dùng tùy chọn command-line để chọn hành vi cho một lần merge, hoặc đặt cấu hình local cho repository cần chính sách riêng.

### 14.6. Nhầm merge commit với squash merge

Squash merge chuẩn bị thay đổi trong index/working tree để bạn tạo commit thông thường; commit đó không có parent trỏ tới tip feature. Nếu cần ghi nhận quan hệ hai dòng lịch sử, dùng merge commit.

## 15. Ghi nhớ

- Fast-forward chỉ di chuyển ref tới commit đã tồn tại; không tạo commit mới.
- Merge commit tạo commit mới có ít nhất hai parent, ghi nhận hai hoặc nhiều dòng lịch sử.
- `--ff` cho phép fast-forward khi có thể; nếu branch phân kỳ, Git tạo merge commit.
- `--ff-only` chỉ cho phép fast-forward; nếu branch phân kỳ, Git từ chối và không tự rebase.
- `--no-ff` tạo merge commit ngay cả khi fast-forward có thể xảy ra; nếu đã up-to-date thì không tạo commit mới.
- Parent thứ nhất của merge commit thường là tip branch đích trước merge; parent thứ hai là tip branch nguồn.
- `merge.ff=true`, `false`, `only` tương ứng với `--ff`, `--no-ff`, `--ff-only` làm hành vi mặc định.
- Tùy chọn trên dòng lệnh có thể ghi đè cấu hình; `git pull` còn có thể chịu ảnh hưởng của `pull.ff`.
- `--no-commit` cần kết hợp `--no-ff` nếu muốn chắc chắn dừng trước một merge commit.
- Dùng `git rev-list --parents`, `git show --pretty=raw` và `git log --graph` để xác minh lịch sử.
- Khi revert merge commit, phải chọn đúng mainline parent bằng `git revert -m`.

Hãy chọn `--ff-only` khi cần bảo vệ lịch sử tuyến tính, `--no-ff` khi cần lưu dấu mốc tích hợp và `--ff` khi muốn Git tự chọn cách phù hợp với quan hệ tổ tiên. Quan trọng nhất là kiểm tra đồ thị và hiểu commit nào sẽ được tạo trước khi cập nhật branch dùng chung.
