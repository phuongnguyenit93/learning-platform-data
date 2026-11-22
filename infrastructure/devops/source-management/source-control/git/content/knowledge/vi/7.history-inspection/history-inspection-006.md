# Tập commit A..B và A...B trong lệnh duyệt lịch sử

Khi so sánh hai branch, câu hỏi thường gặp là: commit nào có trên `feature` nhưng chưa có trên `main`, và commit nào chỉ tồn tại ở một trong hai nhánh? Git dùng cú pháp revision range để chọn tập commit cần duyệt. Trong `git log`, `A..B` lấy commit reachable từ B nhưng không reachable từ A; `A...B` lấy commit chỉ reachable từ một phía, loại phần lịch sử chung của cả hai.

Hai cú pháp trông gần giống nhau nhưng trả lời hai câu hỏi khác nhau. Hiểu tập commit mà mỗi range chọn sẽ giúp bạn review pull request, kiểm tra branch đã phân kỳ, chuẩn bị merge/rebase và tránh nhầm cú pháp của `git log` với `git diff`.

## 1. Git duyệt lịch sử theo khả năng reachable

Git không lưu branch thành một danh sách commit độc lập. Mỗi branch là một ref trỏ đến một commit; từ commit đó Git lần theo các parent để đi ngược lịch sử. Một commit được xem là **reachable** từ revision nếu có thể đi từ revision đó qua các liên kết parent để đến commit ấy.

Ví dụ hai branch có chung lịch sử rồi phân kỳ:

```text
             C1---C2  feature
            /
A---B---M1---M2      main
```

Trong sơ đồ này:

- `A`, `B` là lịch sử chung.
- `M1`, `M2` chỉ reachable từ `main` (nếu chưa có nhánh nào khác giữ chúng).
- `C1`, `C2` chỉ reachable từ `feature`.
- `B` là merge base trong ví dụ đơn giản này.

Nếu chạy `git log main`, Git duyệt các commit reachable từ `main`. Nếu chạy `git log feature`, Git duyệt các commit reachable từ `feature`. Revision range tạo tập hợp từ hai vùng reachable đó bằng cách bao gồm hoặc loại trừ một phía.

## 2. Range A..B: lấy commit của B mà A chưa có

Cú pháp:

```bash
git log A..B
```

Trong `git log`, `A..B` có nghĩa:

> Bao gồm các commit reachable từ B, sau đó loại mọi commit reachable từ A.

Có thể viết tương đương bằng cú pháp loại trừ:

```bash
git log B ^A
```

Vì vậy, `A..B` là range có hướng. Đổi vị trí A và B sẽ đổi tập kết quả.

Với sơ đồ ở phần trước:

```bash
git log --oneline main..feature
```

Kết quả gồm `C1` và `C2`: những commit có trong `feature` nhưng chưa reachable từ `main`. Các commit `A`, `B` bị loại vì chúng cũng reachable từ `main`.

Đổi chiều:

```bash
git log --oneline feature..main
```

Kết quả gồm `M1` và `M2`: commit có trên `main` mà `feature` chưa có.

### Khi nào dùng A..B?

- Xem commit cần được đưa từ feature branch vào main.
- Xem branch local đang thiếu những commit nào so với upstream.
- Xem commit mới trên remote-tracking branch mà local chưa tích hợp.
- Kiểm tra phạm vi thay đổi trước khi tạo pull request hoặc merge.

Ví dụ kiểm tra commit local chưa push:

```bash
git log --oneline origin/main..main
```

Lệnh liệt kê commit reachable từ `main` nhưng chưa reachable từ `origin/main`, theo trạng thái remote-tracking ref hiện có trong clone. Muốn kết quả phản ánh remote mới nhất, fetch trước:

```bash
git fetch origin
git log --oneline origin/main..main
```

Remote-tracking ref chỉ được cập nhật khi fetch; `git log` không tự hỏi server.

## 3. Range A...B: lấy phần khác nhau của cả hai phía

Trong `git log`, cú pháp ba dấu chấm:

```bash
git log A...B
```

lấy **symmetric difference** (hiệu đối xứng): các commit reachable từ A hoặc B, nhưng không reachable từ cả hai. Nói cách khác, Git loại lịch sử chung và giữ lại commit riêng của từng phía.

Với sơ đồ phân kỳ:

```text
             C1---C2  feature
            /
A---B---M1---M2      main
```

Lệnh:

```bash
git log --oneline main...feature
```

sẽ hiển thị `M1`, `M2`, `C1`, `C2`. Các commit `A`, `B` không xuất hiện vì chúng reachable từ cả hai branch.

Khác với `A..B`, range ba chấm có tính đối xứng về tập commit:

```bash
git log A...B
git log B...A
```

Hai lệnh chọn cùng một tập commit, dù thứ tự hiển thị có thể khác. `A...B` hữu ích khi bạn muốn nhìn toàn bộ phần hai branch đã phát triển riêng kể từ lịch sử chung.

### Dùng --left-right để biết commit thuộc phía nào

Kết quả symmetric difference có thể trộn commit của cả hai phía. Thêm `--left-right` để đánh dấu nguồn:

```bash
git log --left-right --oneline main...feature
```

- `<` đánh dấu commit chỉ thuộc phía trái (`main`).
- `>` đánh dấu commit chỉ thuộc phía phải (`feature`).

Ví dụ:

```text
< 91ab230 Update deployment settings
< 3c4d510 Fix checkout timeout
> 7ef812a Add payment retry
> 5ab901c Add gateway metrics
```

Kết quả cho thấy `main` có hai commit riêng và `feature` có hai commit riêng. Nếu không có ký hiệu `>` thì feature không có commit riêng so với main; nếu không có ký hiệu `<` thì main không có commit riêng so với feature.

Có thể kết hợp đồ thị:

```bash
git log --graph --left-right --oneline --decorate main...feature
```

Lệnh này thường hữu ích nhất khi kiểm tra branch đã phân kỳ trước khi quyết định merge hoặc rebase.

## 4. Bảng so sánh A..B và A...B

| Cú pháp trong `git log` | Tập commit được chọn | Câu hỏi trả lời |
|---|---|---|
| `A..B` | Reachable từ B nhưng không reachable từ A | B có commit nào mà A chưa có? |
| `B..A` | Reachable từ A nhưng không reachable từ B | A có commit nào mà B chưa có? |
| `A...B` | Reachable từ A hoặc B, trừ commit reachable từ cả hai | Hai phía có những commit riêng nào? |

Minh họa bằng tập hợp:

```text
Reachable(A) = {common, a1, a2}
Reachable(B) = {common, b1, b2}

A..B   = {b1, b2}
B..A   = {a1, a2}
A...B  = {a1, a2, b1, b2}
```

`A..B` là phép trừ có hướng. `A...B` là phép hiệu đối xứng, lấy phần riêng của cả hai phía. Phần giao nhau (`common`) bị loại trong cả hai range.

## 5. Cú pháp loại trừ bằng ^ và --not

Range hai chấm là cách viết ngắn của việc kết hợp revision dương và revision bị loại trừ.

Ví dụ:

```bash
git log B ^A
```

`B` là revision dương: duyệt commit reachable từ B. `^A` là revision âm: loại các commit reachable từ A.

Có thể dùng `--not` để đảo ý nghĩa các revision theo vị trí trong danh sách đối số:

```bash
git log B --not A
```

Với nhiều revision, cách viết tường minh có thể dễ đọc hơn:

```bash
git log main feature ^release/1.x
```

Lệnh lấy commit reachable từ `main` hoặc `feature`, rồi loại commit reachable từ `release/1.x`. Có thể kết hợp nhiều revision âm:

```bash
git log main feature ^release/1.x ^archive/legacy
```

Hãy nhớ `^A` ở đầu một revision là cú pháp loại trừ revision trong tập duyệt; nó khác với `A^` ở cuối revision, dùng để chỉ commit cha thứ nhất của A.

## 6. Phân biệt A^, A~ và ^A

Các ký hiệu trông gần giống nhau nhưng ý nghĩa khác nhau:

| Cú pháp | Ý nghĩa |
|---|---|
| `A^` | Parent thứ nhất của commit A |
| `A^2` | Parent thứ hai của A; thường dùng với merge commit |
| `A~1` | Parent thứ nhất của A, tương đương `A^` |
| `A~3` | Đi ngược ba lần theo chuỗi parent thứ nhất |
| `^A` | Loại mọi commit reachable từ A khỏi tập kết quả duyệt |

Ví dụ với merge commit M có hai parent:

```text
      F1---F2---+
     /          \
A---B---M--------
        ^1       ^2
```

`M^1` là parent thứ nhất, thường là branch được checkout khi tạo merge; `M^2` là parent thứ hai, thường là branch được merge vào. Thứ tự parent phụ thuộc cách tạo merge và không nên đoán nếu chưa kiểm tra.

Xem parent của một commit:

```bash
git show -s --format="%H%n%P" M
```

Hoặc đọc commit object:

```bash
git cat-file -p M
```

Đừng nhầm `git log A^..B` với `git log ^A B`. Lệnh đầu dùng parent thứ nhất của A làm mốc loại trừ; lệnh sau loại toàn bộ lịch sử reachable từ A.

## 7. Xác định merge base trước khi so sánh

Merge base là tổ tiên chung tốt nhất của hai commit, thường được dùng làm điểm xuất phát cho merge ba chiều. Tìm merge base:

```bash
git merge-base main feature
```

Với lịch sử đơn giản, merge base là commit cuối cùng chung trước khi hai branch tách nhau. Bạn có thể xem các commit chung và riêng bằng:

```bash
git log --oneline main
git log --oneline feature
git log --oneline main..feature
git log --oneline feature..main
git log --oneline --left-right main...feature
```

Một số đồ thị phức tạp có thể có nhiều merge base tốt nhất. Để xem tất cả:

```bash
git merge-base --all main feature
```

Trong trường hợp có nhiều merge base, đừng tự giả định chỉ có một commit chung duy nhất. Git có thể tạo một kết quả merge base ảo khi thực hiện merge phức tạp. Cần xem toàn bộ đồ thị và hiểu lịch sử merge nếu range hoặc kết quả tích hợp không giống ví dụ tuyến tính.

Kiểm tra quan hệ tổ tiên trực tiếp:

```bash
git merge-base --is-ancestor main feature
```

Mã thoát `0` nghĩa là `main` là tổ tiên của `feature`; mã thoát khác `0` nghĩa là không có quan hệ tổ tiên đó. Nếu A là tổ tiên của B, `A..B` có thể liệt kê các commit phát triển sau A trên B, còn `B..A` sẽ rỗng.

## 8. Range trong workflow review pull request

Giả sử bạn đang review branch `feature/search` trước khi merge vào `main`.

**Xem các commit chỉ có trên feature:**

```bash
git log --oneline main..feature/search
```

Đây thường là danh sách commit mà feature mang thêm vào main.

**Xem các commit chỉ có trên main:**

```bash
git log --oneline feature/search..main
```

Nếu có kết quả, main đã tiến lên kể từ khi feature phân nhánh hoặc kể từ lần feature đồng bộ gần nhất.

**Xem cả hai phía:**

```bash
git log --graph --left-right --oneline main...feature/search
```

Lệnh này cho thấy branch nào có commit riêng, giúp xác định chúng đã phân kỳ đến mức nào.

**Xem patch của các commit feature chưa có trên main:**

```bash
git log -p main..feature/search
```

**Đếm số commit riêng:**

```bash
git rev-list --count main..feature/search
git rev-list --count feature/search..main
```

Hai con số cho biết mỗi phía có bao nhiêu commit reachable riêng. Đây là số commit, không phải số file hoặc số dòng thay đổi.

Trước khi đưa ra kết luận, fetch remote để bảo đảm `main` và `feature/search` là các ref bạn định so sánh. Nếu branch chỉ tồn tại trên remote, dùng tên remote-tracking ref như `origin/main` hoặc `origin/feature/search`.

## 9. Range khi kiểm tra branch local và upstream

Git thường thiết lập upstream cho branch local. Ví dụ branch local `feature/search` theo dõi `origin/feature/search`.

Xem upstream:

```bash
git branch -vv
```

Commit local chưa có trên upstream:

```bash
git log --oneline "@{upstream}"..HEAD
```

Commit upstream chưa có trong branch local:

```bash
git log --oneline HEAD.."@{upstream}"
```

Các biểu thức `@{upstream}` và `@{u}` phân giải đến upstream của branch hiện tại nếu đã cấu hình. Đặt chúng trong dấu nháy giúp shell chuyển nguyên revision expression cho Git, đặc biệt hữu ích trong PowerShell. Nếu branch chưa có upstream, Git sẽ báo không thể phân giải revision này. Có thể thay bằng ref cụ thể:

```bash
git log --oneline origin/feature/search..feature/search
```

Trước khi so sánh, cập nhật remote-tracking refs:

```bash
git fetch origin
```

Range chỉ so sánh các object và ref có trong clone. Nó không tự kiểm tra branch đang tồn tại trên server nếu bạn chưa fetch hoặc chưa lấy ref đó về.

## 10. Kết hợp range với các bộ lọc git log

Revision range chọn tập commit trước; các tùy chọn khác tiếp tục lọc hoặc định dạng tập đó.

Chỉ xem merge commit của feature chưa có trên main:

```bash
git log --merges --oneline main..feature
```

Chỉ xem commit của tác giả cụ thể:

```bash
git log --author="An Nguyen" --oneline main..feature
```

Tìm commit có thông điệp liên quan đến cache:

```bash
git log --grep="cache" --oneline main..feature
```

Xem thống kê file thay đổi:

```bash
git log --stat --oneline main..feature
```

Xem đồ thị và đánh dấu hai phía:

```bash
git log --graph --left-right --decorate --oneline main...feature
```

Các bộ lọc path cũng có thể được dùng sau dấu `--`:

```bash
git log --oneline main..feature -- src/search/
```

Lệnh chỉ hiển thị commit trong range có liên quan đến đường dẫn `src/search/`. Khi dùng path limitation, Git có thể đơn giản hóa lịch sử theo cách khác so với đồ thị đầy đủ; nếu đang phân tích quan hệ branch, hãy xem cả lệnh không giới hạn path.

## 11. --cherry-pick và commit tương đương patch

Hai branch có thể chứa các commit khác OID nhưng mang thay đổi tương đương, chẳng hạn một commit được cherry-pick sang branch khác hoặc được tạo lại sau rebase.

Khi dùng:

```bash
git log --left-right --cherry-pick --oneline A...B
```

Git loại khỏi kết quả các commit có patch tương đương ở phía đối diện, giúp tập trung vào thay đổi chưa có bản tương đương trên branch kia. Đây là phép so sánh patch, không phải so sánh OID hoặc quan hệ tổ tiên.

Để đánh dấu các commit có patch tương đương thay vì loại chúng:

```bash
git log --left-right --cherry-mark --oneline A...B
```

Các commit tương đương patch được đánh dấu bằng `=`; commit chỉ có ở một phía được đánh dấu `<` hoặc `>`. Tùy chọn này hữu ích khi muốn kiểm tra branch đã nhận một thay đổi qua cherry-pick dù commit hash khác nhau.

Patch equivalence có giới hạn: thay đổi được chỉnh sửa thêm, chia thành nhiều commit hoặc gộp từ nhiều commit có thể không được nhận diện là tương đương. Hãy xem patch thực tế trước khi kết luận một thay đổi đã được tích hợp.

## 12. --boundary và commit ở ranh giới range

Mặc định, `git log A..B` không hiển thị commit reachable từ A vì chúng đã bị loại khỏi tập kết quả. Nếu muốn nhìn commit biên làm điểm nối với phần lịch sử bị loại, dùng `--boundary`:

```bash
git log --boundary --oneline A..B
```

Commit biên thường được đánh dấu bằng dấu `-` ở đầu dòng. Chúng giúp bạn thấy phần lịch sử phía trước range, nhưng không thuộc tập commit dương mà range đang yêu cầu duyệt.

Kết hợp với graph:

```bash
git log --graph --boundary --oneline A..B
```

Đây là cách hữu ích để xem các commit của feature cùng commit nền mà chúng phát triển từ đó.

## 13. Điểm khác biệt quan trọng: git diff A..B và git diff A...B

Không được áp dụng máy móc ý nghĩa revision range của `git log` cho `git diff`. `git diff` so sánh **tree snapshot**, không liệt kê tập commit.

### Hai dấu chấm trong git diff

```bash
git diff A..B
```

Trong `git diff`, cách viết này tương đương:

```bash
git diff A B
```

Nó so sánh trực tiếp tree của A với tree của B. Nó không có nghĩa “các commit trên B mà A chưa có” như `git log A..B`.

### Ba dấu chấm trong git diff

```bash
git diff A...B
```

Trong `git diff`, ba dấu chấm so sánh tree của merge base giữa A và B với tree của B. Nó thường trả lời: “B đã thay đổi những gì kể từ điểm chung với A?”

Để xem thay đổi phía A kể từ merge base, đảo thứ tự:

```bash
git diff B...A
```

### Bảng phân biệt

| Lệnh | Ý nghĩa |
|---|---|
| `git log A..B` | Commit reachable từ B nhưng không reachable từ A |
| `git log A...B` | Commit riêng của cả A và B, loại lịch sử chung |
| `git diff A..B` | So sánh tree A với tree B |
| `git diff A...B` | So sánh merge base(A, B) với tree B |

Ví dụ khi review feature:

```bash
# Danh sách commit feature chưa có trên main
git log --oneline main..feature

# Nội dung khác biệt giữa snapshot main và feature
git diff main..feature

# Nội dung feature thay đổi kể từ điểm chung với main
git diff main...feature
```

Ba lệnh này phục vụ các câu hỏi khác nhau. Nếu branch main đã có commit mới sau khi feature phân nhánh, `git diff main...feature` giúp tập trung vào phần feature đã phát triển từ merge base, còn `git diff main..feature` so sánh hai snapshot cuối hiện tại.

## 14. Trường hợp đặc biệt và giới hạn

### A là tổ tiên của B

Nếu A là tổ tiên của B, `A..B` chứa các commit đi sau A trên B. `B..A` rỗng. `A...B` cũng chỉ còn các commit riêng phía B, vì không có commit riêng phía A.

### Hai branch trỏ cùng commit

Nếu A và B trỏ cùng một commit, cả `A..B`, `B..A` và `A...B` đều rỗng.

### Hai branch không có tổ tiên chung

Nếu hai lịch sử không có merge base, `A...B` vẫn có thể chọn toàn bộ commit reachable riêng từ cả hai phía. Tuy nhiên, `git diff A...B` không thể dùng merge base thông thường nếu không tồn tại merge base; Git sẽ báo lỗi hoặc không thể thực hiện phép so sánh theo dạng đó.

### Nhiều merge base

Với lịch sử criss-cross merge, có thể tồn tại nhiều merge base tốt nhất. Revision range ba chấm trong `git log` loại các lịch sử chung theo các merge base phù hợp; kết quả không nhất thiết giống hình minh họa chỉ có một điểm phân nhánh. Dùng `git merge-base --all A B` và đồ thị đầy đủ để kiểm tra.

### Shallow clone hoặc ref chưa fetch

Nếu clone bị giới hạn lịch sử, Git có thể không có đủ parent để xác định chính xác quan hệ tổ tiên. Tương tự, nếu branch remote chưa fetch, range đang dùng có thể so sánh với ref cũ hoặc không tìm thấy ref. Kiểm tra:

```bash
git rev-parse --is-shallow-repository
git branch -a
git fetch --all --prune
```

### Commit tương đương patch nhưng khác OID

Cherry-pick và rebase tạo commit mới với parent hoặc metadata khác. `A..B` và `A...B` dựa trên reachability nên vẫn có thể hiển thị cả hai commit dù patch tương đương. Dùng `--cherry-pick` hoặc `--cherry-mark` để hỗ trợ nhận diện trường hợp này.

## 15. Quy trình chọn range khi điều tra branch

Khi được giao review `feature/reporting` trước khi tích hợp vào `main`, thực hiện:

**Bước 1: Cập nhật refs và xác nhận branch**

```bash
git fetch --all --prune
git branch -vv
```

**Bước 2: Xem commit chỉ có trên feature**

```bash
git log --oneline main..feature/reporting
```

**Bước 3: Kiểm tra main có tiến lên hay không**

```bash
git log --oneline feature/reporting..main
```

**Bước 4: Xem cả hai phía trên cùng đồ thị**

```bash
git log --graph --left-right --decorate --oneline main...feature/reporting
```

**Bước 5: Tìm merge base và xem patch**

```bash
git merge-base main feature/reporting
git diff main...feature/reporting
```

Lệnh cuối so sánh thay đổi của feature kể từ merge base với snapshot hiện tại của feature. Nếu muốn xem khác biệt trực tiếp giữa hai snapshot cuối, dùng `git diff main..feature/reporting`.

**Bước 6: Kiểm tra cherry-pick tương đương nếu branch đã đồng bộ thủ công**

```bash
git log --left-right --cherry-mark --oneline main...feature/reporting
```

Ghi nhận commit riêng của mỗi phía, merge base, thay đổi patch và các commit tương đương. Từ đó mới quyết định có cần cập nhật feature bằng merge/rebase hay có thể tích hợp.

## 16. Bài tập thực hành

Trong repository thử nghiệm, tạo branch `main` và `feature/demo` từ cùng một commit nền. Tạo hai commit riêng trên `main` và ba commit riêng trên `feature/demo`, sau đó chưa merge hai nhánh.

1. Chạy `git log --oneline main..feature/demo` và ghi lại các commit chỉ có trên feature.
2. Chạy `git log --oneline feature/demo..main` và ghi lại các commit chỉ có trên main.
3. Chạy `git log --left-right --graph --oneline main...feature/demo` để xác định phía của từng commit.
4. Dùng `git rev-list --count` với cả hai chiều để đếm commit riêng.
5. Dùng `git merge-base main feature/demo` để tìm tổ tiên chung.
6. Tạo một commit trên feature rồi cherry-pick thay đổi tương đương sang main; chạy `--cherry-mark` và `--cherry-pick` để quan sát cách nhận diện patch tương đương.
7. So sánh `git diff main..feature/demo` với `git diff main...feature/demo`; giải thích vì sao hai lệnh hiển thị khác nhau.
8. Thử `git log --boundary --oneline main..feature/demo` để quan sát commit ở ranh giới.
9. Sau khi merge feature vào main, chạy lại các range và giải thích vì sao tập commit riêng thay đổi.

Bạn hoàn thành bài tập khi giải thích được chính xác commit nào được chọn bởi `A..B` và `A...B` trong `git log`, xác định được phía của commit bằng `--left-right` và không nhầm ý nghĩa ba dấu chấm giữa `git log` với `git diff`.
