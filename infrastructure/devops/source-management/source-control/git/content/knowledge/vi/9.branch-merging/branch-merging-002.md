# Hợp nhất fast-forward và trường hợp không tạo merge commit

Khi bạn merge một branch vào branch hiện tại, Git không phải lúc nào cũng tạo merge commit. Nếu tip của branch hiện tại là tổ tiên của branch được merge, Git có thể **fast-forward**: chỉ di chuyển ref của branch hiện tại đến commit mới hơn. Lịch sử vẫn giữ nguyên các commit đã có, nhưng không có commit hợp nhất mới.

Ngoài fast-forward, còn có những tình huống không tạo merge commit: branch hiện tại đã chứa toàn bộ lịch sử của branch được merge (đã up-to-date), hoặc bạn dùng `git merge --squash` để chuẩn bị một snapshot rồi tự tạo commit thường. Các tùy chọn `--ff`, `--ff-only` và `--no-ff` cho phép kiểm soát chính sách tích hợp, còn `--no-commit` có giới hạn quan trọng khi fast-forward.

## 1. Hiểu fast-forward bằng quan hệ tổ tiên

Branch trong Git là một ref trỏ đến commit. Giả sử `main` đang trỏ đến commit B và `feature/search` đã tạo thêm hai commit C, D từ B:

```text
A---B---C---D  feature/search
     ^
    main
```

Commit mà `main` trỏ tới là tổ tiên của commit mà `feature/search` trỏ tới. Nếu bạn đang đứng trên `main` và chạy:

```bash
git switch main
git merge feature/search
```

Git có thể di chuyển ref `main` từ B thẳng đến D. Không cần tạo commit mới vì lịch sử của `main` đã nằm hoàn toàn trong lịch sử của `feature/search`.

Sau thao tác:

```text
A---B---C---D  main, feature/search
```

Các commit C và D vẫn là những commit ban đầu. Git chỉ cập nhật vị trí branch `main`; OID của C và D không đổi và không có merge commit mới.

### Điều kiện để fast-forward

Fast-forward có thể xảy ra khi tip của branch hiện tại là tổ tiên của tip branch được merge. Kiểm tra bằng:

```bash
git merge-base --is-ancestor main feature/search
```

Nếu lệnh trả mã thoát `0`, tip commit của `main` là tổ tiên của tip commit `feature/search`, vì vậy `main` có thể fast-forward đến `feature/search` nếu không có tùy chọn hoặc chính sách ngăn điều đó. Mã thoát khác `0` nghĩa là điều kiện tổ tiên này không đúng.

Bạn cũng có thể xem đồ thị:

```bash
git log --graph --oneline --decorate --all
```

Fast-forward không phải là “gộp nội dung file theo cách đơn giản”. Đây là thao tác cập nhật ref vì không có lịch sử riêng ở branch hiện tại cần kết hợp. Nếu hai branch đã phát triển độc lập kể từ tổ tiên chung, Git cần một phép merge thực sự hoặc phải từ chối nếu bạn yêu cầu fast-forward only.

## 2. Fast-forward không tạo merge commit

Merge commit là một commit mới có tree kết quả và thường có hai parent: tip branch hiện tại trước merge và tip branch được merge. Fast-forward không tạo object commit mới; branch đích chỉ chuyển tới một commit đã tồn tại.

So sánh hai trường hợp:

Trước merge:

```text
A---B---C---D  feature
     ^
    main
```

Sau fast-forward:

```text
A---B---C---D  main, feature
```

Nếu muốn lưu một mốc tích hợp riêng trong lịch sử dù fast-forward có thể thực hiện, dùng `--no-ff` để buộc tạo merge commit (phần sau sẽ giải thích).

Fast-forward vẫn là một lần merge về mặt thao tác tích hợp branch, nhưng không tạo merge commit. Các commit của feature trở thành một phần lịch sử reachable từ branch đích vì ref đích đã di chuyển tới commit cuối của feature.

## 3. Dùng --ff, --ff-only và --no-ff

Ba tùy chọn có ý nghĩa khác nhau:

| Tùy chọn | Khi fast-forward có thể thực hiện | Khi hai branch đã phân kỳ |
|---|---|---|
| `--ff` | Cho phép fast-forward | Thực hiện merge và tạo merge commit nếu merge thành công |
| `--ff-only` | Chỉ fast-forward | Từ chối, không tạo merge commit |
| `--no-ff` | Không fast-forward; tạo merge commit | Thực hiện merge ba chiều và tạo merge commit nếu thành công |

### --ff

```bash
git switch main
git merge --ff feature/search
```

`--ff` cho phép Git fast-forward nếu quan hệ tổ tiên phù hợp. Nếu hai branch đã phân kỳ, Git thực hiện merge bình thường và tạo merge commit sau khi kết hợp thay đổi thành công. Tùy chọn này có thể dùng để yêu cầu cho phép fast-forward ngay cả khi cấu hình `merge.ff` đang tắt.

### --ff-only

```bash
git switch main
git merge --ff-only feature/search
```

`--ff-only` yêu cầu thao tác chỉ thành công nếu có thể fast-forward. Nếu branch hiện tại và branch được merge đã phân kỳ, Git từ chối thay vì tự tạo merge commit. Đây là lựa chọn hữu ích khi nhóm muốn lịch sử tuyến tính và muốn xử lý việc phân kỳ một cách tường minh bằng cách cập nhật branch trước.

Ví dụ thông báo có thể gặp:

```text
fatal: Not possible to fast-forward, aborting.
```

Khi đó, hãy fetch và xem các commit riêng của hai phía trước khi quyết định rebase hoặc merge theo quy trình của nhóm.

### --no-ff

```bash
git switch main
git merge --no-ff feature/search
```

`--no-ff` ngăn Git dùng fast-forward ngay cả khi branch hiện tại là tổ tiên của branch được merge. Git tạo merge commit để đánh dấu lần tích hợp. Lịch sử thể hiện rõ nhánh feature đã được hợp nhất như một đơn vị.

Ví dụ:

```text
      C---D------+
     /           \
A---B-------------M  main
```

Commit M có parent thứ nhất là B (tip `main` trước merge) và parent thứ hai là D (tip `feature/search`).

## 4. Trường hợp Already up to date

Một trường hợp khác không tạo merge commit là branch hiện tại đã chứa toàn bộ lịch sử của branch được merge.

Ví dụ:

```text
A---B---C---D  main
         ^
        feature
```

Nếu bạn đang ở `main` và chạy:

```bash
git merge feature
```

Git báo:

```text
Already up to date.
```

Không có ref nào cần di chuyển và không có merge commit mới. Tip của `feature` đã reachable từ `main`.

Kiểm tra quan hệ này:

```bash
git merge-base --is-ancestor feature main
```

Nếu trả mã thoát `0`, tip `feature` là tổ tiên của `main`; vì vậy merge `feature` vào `main` không cần thêm thay đổi. Điều này khác với fast-forward: fast-forward di chuyển branch đích về phía trước, còn already up-to-date là branch đích đã ở vị trí chứa commit cần merge.

`--no-ff` cũng không tạo merge commit trong trường hợp đã up-to-date, vì không có commit hoặc thay đổi mới nào cần tích hợp. `--no-ff` buộc merge commit khi có lịch sử mới từ phía được merge và bình thường Git có thể fast-forward; nó không tạo một merge commit rỗng chỉ để ghi lại việc chạy lệnh.

## 5. Đồ thị so sánh ba trạng thái

| Tình huống | Trước thao tác | Kết quả |
|---|---|---|
| Fast-forward | `main` là tổ tiên của `feature` | `main` di chuyển tới tip `feature`; không có merge commit |
| Already up to date | `feature` là tổ tiên của `main` | Không đổi ref; không có merge commit |
| Hai branch phân kỳ | Mỗi branch có commit riêng | Merge ba chiều; thường tạo merge commit |
| `--no-ff` khi có commit mới từ feature | `main` là tổ tiên của `feature` | Tạo merge commit dù có thể fast-forward |
| `--ff-only` khi hai branch phân kỳ | Không có quan hệ fast-forward phù hợp | Từ chối; không tạo merge commit |

Phân biệt được các trường hợp này giúp bạn đọc thông báo của Git chính xác. Không phải lần chạy `git merge` nào cũng tạo ra một commit mới.

## 6. Khi hai branch đã phân kỳ

Nếu cả hai branch đều có commit riêng sau tổ tiên chung, fast-forward không thể cập nhật branch đích mà vẫn giữ cả hai dòng lịch sử.

```text
      C---D  feature/search
     /
A---B---E---F  main
```

Ở đây `main` đã có E và F, còn feature có C và D. Tip `main` không phải tổ tiên của tip feature, và tip feature cũng không phải tổ tiên của main. Kiểm tra:

```bash
git merge-base --is-ancestor main feature/search
git merge-base --is-ancestor feature/search main
git merge-base main feature/search
```

Hai lệnh `--is-ancestor` đều không thành công nếu hai nhánh đã phân kỳ như sơ đồ. Lệnh `git merge-base` cuối cùng cho biết tổ tiên chung để Git thực hiện merge ba chiều.

Trong tình huống này:

- `git merge --ff-only feature/search` sẽ từ chối.
- `git merge --ff feature/search` sẽ thực hiện merge và tạo merge commit nếu không có lỗi/conflict.
- `git merge --no-ff feature/search` cũng tạo merge commit; `--no-ff` không làm thay đổi sự cần thiết của việc kết hợp hai phía.

## 7. Chính sách fast-forward trong cấu hình

Bạn có thể cấu hình cách `git merge` xử lý fast-forward mặc định.

Xem giá trị hiện tại:

```bash
git config --show-origin --get merge.ff
```

Các giá trị thường gặp:

| Giá trị | Hành vi mặc định |
|---|---|
| `true` | Cho phép fast-forward khi có thể (hành vi mặc định thông thường) |
| `false` | Luôn tạo merge commit khi có lịch sử mới cần merge, kể cả khi có thể fast-forward |
| `only` | Chỉ cho phép fast-forward; từ chối nếu branch đã phân kỳ |

Thiết lập trong repository hiện tại:

```bash
git config --local merge.ff only
```

Thiết lập cho mọi repository của người dùng:

```bash
git config --global merge.ff false
```

Chọn phạm vi cấu hình phù hợp với workflow. Cấu hình local chỉ ảnh hưởng repository hiện tại; global ảnh hưởng các repository của người dùng trừ khi có cấu hình cấp cao hơn ghi đè.

Tùy chọn dòng lệnh có thể ghi đè chính sách mặc định cho một lần merge:

```bash
git merge --ff feature/search
git merge --ff-only feature/search
git merge --no-ff feature/search
```

## 8. Fast-forward trong git pull

`git pull` về cơ bản fetch rồi tích hợp thay đổi từ upstream vào branch hiện tại bằng merge hoặc rebase tùy cấu hình và tùy chọn. Chính sách fast-forward của phần merge có thể được điều khiển bằng `pull.ff`.

Xem cấu hình:

```bash
git config --show-origin --get pull.ff
git config --show-origin --get pull.rebase
```

Các giá trị thường dùng cho `pull.ff`:

- `true`: cho phép fast-forward khi có thể.
- `false`: yêu cầu merge commit thay vì fast-forward khi merge được thực hiện.
- `only`: chỉ chấp nhận fast-forward; nếu branch phân kỳ, pull dừng lại.

Ví dụ:

```bash
git pull --ff-only
```

Lệnh này phù hợp khi bạn muốn cập nhật branch local chỉ bằng cách tiến ref tới commit upstream. Nếu local có commit riêng và remote cũng có commit riêng, Git từ chối để bạn quyết định cách tích hợp.

Đừng nhầm `pull.ff` với `pull.rebase`. `pull.rebase` quyết định pull dùng rebase hay merge; `pull.ff` điều khiển chính sách fast-forward khi thao tác merge được dùng. Hãy kiểm tra cấu hình hiệu lực trước khi dùng `git pull` trong repository có chính sách nhóm.

## 9. Vì sao --no-commit không dừng được fast-forward?

`--no-commit` yêu cầu Git dừng trước khi tạo merge commit để bạn xem kết quả. Nhưng fast-forward không tạo merge commit; Git chỉ di chuyển ref branch đến commit đã tồn tại. Vì không có merge commit để tạm dừng, `git merge --no-commit` không thể ngăn một fast-forward.

Nếu muốn xem xét kết quả trước khi tạo merge commit, kết hợp:

```bash
git merge --no-ff --no-commit feature/search
```

`--no-ff` bảo đảm Git chuẩn bị một merge commit; `--no-commit` dừng trước khi commit được tạo. Bạn có thể kiểm tra:

```bash
git status
git diff --cached
git diff --check
```

Sau khi xác nhận kết quả, hoàn tất:

```bash
git commit
```

Hoặc hủy merge đang dừng:

```bash
git merge --abort
```

Nếu chỉ dùng `--no-commit` và Git fast-forward được, branch vẫn có thể được cập nhật ngay. Đây là lý do cần thêm `--no-ff` khi mục tiêu là review snapshot trước merge commit.

## 10. --squash: có kết quả tích hợp nhưng không có merge commit

`git merge --squash <branch>` lấy kết quả thay đổi của branch được chỉ định so với lịch sử hiện tại và chuẩn bị nội dung trong working tree/index, nhưng không tạo merge commit và không ghi nhận quan hệ parent của branch được merge.

Ví dụ:

```bash
git switch main
git merge --squash feature/search
git status
git diff --cached
git commit -m "Add search feature"
```

Commit do bạn tạo sau đó là commit thường, thường có một parent là tip `main` trước khi squash. Nó chứa snapshot kết quả nhưng không có tip của `feature/search` làm parent thứ hai. Vì vậy, Git không xem các commit gốc của feature là tổ tiên của main chỉ nhờ squash commit này.

Đồ thị khái quát:

```text
      C---D  feature/search
     /
A---B---S    main
```

S là commit thường chứa thay đổi được squash. Nhánh feature vẫn tồn tại và có thể vẫn bị `git branch -d` từ chối vì các commit C, D không reachable từ main.

Khác biệt giữa `--squash` và `--no-ff`:

| Lệnh | Kết quả |
|---|---|
| `git merge --no-ff feature` | Tạo merge commit có hai parent khi có thay đổi cần tích hợp |
| `git merge --squash feature` | Chuẩn bị thay đổi trong index/working tree; người dùng tạo commit thường, không có merge parent |

Chọn squash khi nhóm muốn gộp thay đổi thành một commit đơn và chấp nhận không giữ quan hệ ancestry của các commit feature trong branch đích. Chọn merge commit khi muốn lưu rõ lịch sử hai nhánh được kết hợp.

## 11. Những trường hợp không tạo merge commit: tổng hợp

Có nhiều lý do khiến một lệnh merge không sinh merge commit:

1. **Fast-forward:** branch đích là tổ tiên của branch được merge; Git di chuyển ref tới commit có sẵn.
2. **Already up to date:** branch đích đã chứa tip của branch được merge; không có gì cần tích hợp.
3. **Squash merge:** Git chuẩn bị snapshot kết hợp nhưng không tạo merge commit; người dùng tạo một commit thường nếu muốn lưu kết quả.
4. **Merge bị hủy hoặc thất bại trước khi hoàn tất:** conflict hoặc lỗi có thể khiến Git dừng mà chưa tạo merge commit. Sau khi giải quyết conflict, người dùng mới hoàn tất bằng commit; hoặc dùng `git merge --abort` để hủy.

Hãy phân biệt “không có merge commit” với “không có commit nào được tạo”. Fast-forward có thể làm branch trỏ tới commit đã tồn tại; already up to date không thay đổi lịch sử; squash cho phép bạn tạo một commit thường; merge đang conflict chưa hoàn tất có thể chưa tạo commit.

## 12. Kiểm tra kết quả sau khi merge

Sau khi merge thành công, hãy kiểm tra cả đồ thị và nội dung:

```bash
git status --short
git log --graph --oneline --decorate --all -12
git show -s --format="%H%n%P%n%s" HEAD
```

Nếu là fast-forward, `HEAD` sẽ trỏ tới commit đã có trong branch được merge; không có commit mới với hai parent. Nếu là merge commit, dòng `%P` thường hiển thị hai parent. Nếu là squash, commit được tạo sau đó chỉ có một parent.

Kiểm tra quan hệ tổ tiên:

```bash
git merge-base --is-ancestor feature/search main
```

Sau fast-forward, lệnh thường trả `0` vì tip feature đã trở thành tổ tiên hoặc chính là tip main. Sau merge commit, tip feature cũng reachable từ main qua parent thứ hai. Sau squash merge, lệnh có thể trả khác `0` vì các commit gốc của feature không trở thành tổ tiên của main.

Đọc diff của commit tích hợp:

```bash
git show --stat HEAD
git diff HEAD^1 HEAD
```

Với merge commit, `HEAD^1` là parent thứ nhất; diff này cho biết snapshot merge khác parent thứ nhất như thế nào. Với squash commit thường, parent thứ nhất là commit trước squash. Luôn chạy test cần thiết vì Git không đánh giá tính đúng đắn nghiệp vụ.

## 13. Chọn chính sách phù hợp với workflow

| Nhu cầu nhóm | Chính sách thường phù hợp | Lý do |
|---|---|---|
| Lịch sử tuyến tính, chỉ cập nhật khi branch chưa phân kỳ | `--ff-only` | Buộc người dùng xử lý divergence rõ ràng |
| Muốn ghi nhận mỗi lần tích hợp feature bằng merge commit | `--no-ff` | Giữ mốc merge và hai parent trong DAG |
| Cho phép fast-forward khi có thể, tạo merge commit khi đã phân kỳ | `--ff` hoặc mặc định | Hành vi linh hoạt và phổ biến |
| Muốn một commit tổng hợp thay đổi của feature | `--squash` | Lịch sử đích không giữ commit feature làm ancestry |
| Cần xem kết quả trước khi tạo merge commit | `--no-ff --no-commit` | Dừng ở trạng thái chuẩn bị merge commit |

Không có chính sách duy nhất đúng cho mọi nhóm. Hãy chọn theo quy ước review, khả năng truy vết, cách release và yêu cầu giữ lịch sử. Điều quan trọng là thành viên hiểu chính sách và không vô tình thay đổi cách ghi lịch sử giữa các lần tích hợp.

## 14. Quy trình thực hành fast-forward và các trường hợp không có merge commit

Trong repository thử nghiệm, tạo commit nền và branch feature:

```bash
git switch -c feature/search
```

Tạo một hoặc hai commit trên feature, sau đó quay lại main:

```bash
git switch main
git merge-base --is-ancestor main feature/search
```

Nếu điều kiện tổ tiên đúng, thử fast-forward:

```bash
git merge --ff-only feature/search
```

Quan sát đồ thị và parent của `HEAD`:

```bash
git log --graph --oneline --decorate --all
git show -s --format="%H %P %s" HEAD
```

Tiếp theo tạo branch thử nghiệm khác để quan sát `--no-ff`:

```bash
git switch -c feature/report
# Tạo commit trên feature/report
git switch main
git merge --no-ff feature/report
```

Xác nhận có merge commit với hai parent. Tạo một branch thử nghiệm thứ ba để quan sát squash:

```bash
git switch -c feature/cleanup
# Tạo commit trên feature/cleanup
git switch main
git merge --squash feature/cleanup
git status
git diff --cached
git commit -m "Apply cleanup changes"
```

Kiểm tra rằng commit squash là commit thường và các commit gốc của `feature/cleanup` không trở thành parent của nó. Dùng repository thử nghiệm riêng để tránh làm thay đổi lịch sử dự án thật.

## 15. Bài tập thực hành

Tạo một repository thử nghiệm có branch `main` và branch `feature/demo` từ cùng một commit nền.

1. Tạo hai commit trên `feature/demo` và không tạo commit mới trên `main`.
2. Chạy `git merge-base --is-ancestor main feature/demo` và giải thích kết quả.
3. Chạy `git merge --ff-only feature/demo`, sau đó xem đồ thị và xác nhận không có merge commit.
4. Tạo branch feature mới, tạo commit trên đó rồi merge bằng `--no-ff`; kiểm tra merge commit có hai parent.
5. Tạo branch feature khác và thử `git merge --ff-only`; trước đó tạo một commit riêng trên main để hai branch phân kỳ, quan sát Git từ chối.
6. Thử `git merge --no-commit` trong tình huống có thể fast-forward và giải thích vì sao tùy chọn này không ngăn ref di chuyển.
7. Thử `git merge --no-ff --no-commit`, xem index/working tree trước khi chạy `git commit`, rồi hoàn tất hoặc abort.
8. Thực hiện `git merge --squash`, tạo commit thường và so sánh parent với merge commit.
9. Tạo tình huống branch đã được merge hoàn toàn rồi chạy `git merge` lần nữa; quan sát thông báo `Already up to date` và xác nhận không có commit mới.
10. Thử cấu hình `merge.ff` thành `only` trong repository thử nghiệm, rồi kiểm tra cách lệnh merge phản ứng khi branch phân kỳ.

Bạn hoàn thành bài tập khi giải thích được điều kiện fast-forward, phân biệt fast-forward với already up to date, chọn đúng `--ff`, `--ff-only`, `--no-ff`, hiểu giới hạn của `--no-commit` và phân biệt merge commit với commit được tạo sau squash.
