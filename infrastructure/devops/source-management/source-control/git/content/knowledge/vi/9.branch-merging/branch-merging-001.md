# Tổ tiên chung và nguyên lý hợp nhất ba chiều

Khi hai branch phát triển song song, Git cần xác định phần lịch sử chung trước khi kết hợp thay đổi của chúng. Commit chung tốt nhất đó được gọi là **merge base** (tổ tiên chung). Trong một merge ba chiều (three-way merge), Git xem ba phiên bản: snapshot tại merge base, snapshot của branch hiện tại và snapshot của branch được merge vào. Từ hai tập thay đổi kể từ base, Git tạo kết quả kết hợp; nếu hai phía sửa cùng một vùng theo cách không thể tự động hòa giải, Git đánh dấu xung đột để người dùng giải quyết.

Hiểu vai trò của merge base giúp bạn dự đoán kết quả merge, phân tích vì sao có conflict và đọc đúng quan hệ giữa `ours`, `theirs` và `base`. Đây cũng là nền tảng để hiểu tại sao fast-forward không cần merge ba chiều, vì sao merge commit có hai parent và vì sao một số lịch sử phức tạp có thể có nhiều merge base.

## 1. Branch phát triển song song từ một commit chung

Giả sử branch `main` và `feature/payment` cùng bắt đầu từ commit `B`. Sau đó mỗi branch tạo commit riêng:

```text
          C1---C2  feature/payment
         /
A---B---M1---M2  main
```

`B` là commit chung gần nhất trong đồ thị đơn giản này. `main` đã phát triển thêm `M1`, `M2`; `feature/payment` phát triển thêm `C1`, `C2`.

Khi muốn merge feature vào main, Git cần kết hợp hai dòng thay đổi:

- Những gì `main` đã thay đổi kể từ `B`.
- Những gì `feature/payment` đã thay đổi kể từ `B`.

Git không chỉ lấy toàn bộ file từ branch mới hơn rồi ghi đè lên branch còn lại. Cách làm đó sẽ làm mất thay đổi của một phía. Thay vào đó, Git dùng snapshot chung làm điểm xuất phát để so sánh hai phía và tạo kết quả kết hợp.

## 2. Merge base là gì?

**Merge base** là một tổ tiên chung tốt nhất (best common ancestor) của hai commit. Một commit là tổ tiên chung nếu nó có thể được đi tới từ cả hai commit bằng cách lần theo các parent. Trong các tổ tiên chung, merge base là tổ tiên chung không bị một tổ tiên chung khác nằm giữa nó và hai đầu nhánh thay thế.

Trong lịch sử tuyến tính phân nhánh thông thường, merge base chính là commit tại điểm hai branch tách ra. Tuy nhiên, với lịch sử có nhiều merge chéo, có thể có nhiều merge base tốt nhất; vì vậy, không nên định nghĩa merge base đơn giản là “commit chung mới nhất theo ngày”.

Tìm merge base:

```bash
git merge-base main feature/payment
```

Git in ra OID của một merge base phù hợp. Dùng `--all` để xem tất cả merge base tốt nhất nếu có:

```bash
git merge-base --all main feature/payment
```

Kiểm tra một commit có phải tổ tiên của commit khác:

```bash
git merge-base --is-ancestor <older-commit> <newer-commit>
```

Mã thoát `0` nghĩa là commit đầu là tổ tiên của commit thứ hai. Mã thoát khác `0` nghĩa là quan hệ tổ tiên đó không đúng (hoặc có lỗi cần điều tra).

### Merge base không phải branch và không di chuyển HEAD

Merge base chỉ là commit được xác định từ đồ thị lịch sử. Lệnh `git merge-base` không tạo commit, không di chuyển branch và không thay đổi working tree. Nó là phép tra cứu để bạn hoặc các lệnh merge dùng làm mốc so sánh.

Bạn có thể xem snapshot tại merge base:

```bash
git show --stat <BASE>
git show <BASE>:src/payment.js
```

Lệnh thứ hai đọc nội dung file tại snapshot của base. Thay `<BASE>` bằng OID hoặc revision mà `git merge-base` trả về.

## 3. Ba phiên bản trong merge ba chiều

Một merge ba chiều dùng ba đầu vào logic:

| Phiên bản | Ý nghĩa | Trong merge `main` với `feature/payment` |
|---|---|---|
| Base | Snapshot tại merge base | Nội dung chung trước khi hai branch tách ra |
| Ours | Snapshot của branch hiện tại | `main` nếu bạn đang đứng trên `main` và chạy merge feature |
| Theirs | Snapshot của branch được merge vào | `feature/payment` trong ví dụ |

Git tính thay đổi từ base đến ours và từ base đến theirs, sau đó kết hợp các thay đổi tương thích.

```text
                 Merge base (B)
                   /       \
                  /         \
       thay đổi phía ours   thay đổi phía theirs
                /             \
             main           feature/payment
                \             /
                 \           /
                  Kết quả merge
```

Tên `ours` và `theirs` phụ thuộc hướng thao tác. Nếu bạn checkout `feature/payment` rồi merge `main`, `ours` là feature và `theirs` là main. Khi giải quyết conflict, hãy dựa vào branch hiện tại và branch được merge, đừng gắn cố định `ours = main` hoặc `theirs = feature`.

Trong một merge commit hai parent thông thường, parent thứ nhất là commit mà bạn đang đứng khi bắt đầu merge (ours); parent thứ hai là tip của branch được merge vào (theirs).

## 4. Git kết hợp hai tập thay đổi như thế nào?

Hãy tưởng tượng file `src/payment.js` tại merge base có nội dung:

```javascript
function calculateTotal(order) {
  const subtotal = order.subtotal;
  return subtotal;
}
```

Trên `main`, nhóm thêm kiểm tra dữ liệu:

```javascript
function calculateTotal(order) {
  if (!order) throw new Error("Order is required");
  const subtotal = order.subtotal;
  return subtotal;
}
```

Trên `feature/payment`, nhóm thêm phí giao dịch:

```javascript
function calculateTotal(order) {
  const subtotal = order.subtotal;
  const fee = order.fee ?? 0;
  return subtotal + fee;
}
```

Hai phía sửa các vùng khác nhau: main thêm kiểm tra đầu hàm, feature thêm phép tính phí ở cuối. Git thường có thể kết hợp thành:

```javascript
function calculateTotal(order) {
  if (!order) throw new Error("Order is required");
  const subtotal = order.subtotal;
  const fee = order.fee ?? 0;
  return subtotal + fee;
}
```

Không cần người dùng chọn toàn bộ file từ một phía vì các thay đổi không mâu thuẫn. Git sử dụng ngữ cảnh và thuật toán hợp nhất nội dung để tạo kết quả.

## 5. Những trường hợp merge tự động thành công

Khi so sánh hai phía với base, một số tình huống thường được giải quyết tự động:

| Thay đổi từ base đến ours | Thay đổi từ base đến theirs | Kết quả thường gặp |
|---|---|---|
| Không đổi một dòng | Sửa dòng đó | Lấy thay đổi từ theirs |
| Sửa dòng đó | Không đổi | Giữ thay đổi từ ours |
| Sửa vùng đầu file | Sửa vùng cuối file độc lập | Kết hợp cả hai |
| Cùng sửa theo cách tạo ra nội dung giống nhau | Cùng sửa giống nhau | Giữ một kết quả chung, không cần conflict nội dung |
| Thêm hai file ở đường dẫn khác nhau | Thêm hai file ở đường dẫn khác nhau | Thường giữ cả hai file |

“Tự động thành công” chỉ nói rằng Git có thể tạo kết quả theo quy tắc merge. Nó không đảm bảo logic ứng dụng đúng. Hai thay đổi ở hai vùng riêng biệt vẫn có thể gây lỗi logic khi kết hợp, ví dụ một nhánh đổi đơn vị tiền tệ còn nhánh kia thêm phép cộng phí nhưng không cập nhật quy đổi.

Sau merge không có conflict, bạn vẫn cần đọc diff và chạy kiểm thử phù hợp.

## 6. Khi nào xuất hiện conflict?

Conflict xảy ra khi Git không thể tự quyết định kết quả hợp nhất một cách an toàn. Trường hợp phổ biến là hai phía cùng sửa một vùng dòng dựa trên cùng nội dung base nhưng đưa ra kết quả khác nhau.

Ví dụ, base có:

```javascript
return subtotal;
```

Ours đổi thành:

```javascript
return subtotal - discount;
```

Theirs đổi thành:

```javascript
return subtotal + fee;
```

Git không thể biết quy tắc nghiệp vụ đúng là trừ discount, cộng fee hay kết hợp cả hai theo thứ tự nào. Nó đánh dấu conflict để người phát triển quyết định.

Các trường hợp khác có thể gây conflict:

- Một phía sửa file, phía kia xóa file (modify/delete).
- Hai phía đổi tên cùng một file sang hai đường dẫn khác nhau (rename/rename).
- Một phía đổi tên file, phía kia sửa nội dung file cũ (rename/modify).
- Hai phía thêm file cùng tên nhưng nội dung khác nhau (add/add).
- Thay đổi cấu trúc thư mục dẫn đến xung đột file/thư mục.
- Một file nhị phân được thay đổi ở cả hai phía; Git thường không thể hòa giải nội dung theo dòng.

Conflict không nhất thiết có nghĩa một branch sai. Nó chỉ cho biết cần quyết định cách kết hợp hai ý định thay đổi.

## 7. Hiểu ours, theirs và base trong index khi conflict

Khi xảy ra conflict trong một đường dẫn, index có thể lưu nhiều phiên bản tạm thời (unmerged stages):

| Stage | Tên thường gọi | Nội dung |
|---:|---|---|
| 1 | Base | Phiên bản tại merge base |
| 2 | Ours | Phiên bản từ branch hiện tại |
| 3 | Theirs | Phiên bản từ branch được merge vào |

Kiểm tra các entry chưa hợp nhất:

```bash
git ls-files -u
```

Đọc từng phiên bản của một file đang conflict:

```bash
git show :1:src/payment.js
git show :2:src/payment.js
git show :3:src/payment.js
```

Một stage có thể không tồn tại trong các tình huống add/delete đặc biệt. Ví dụ file chỉ được thêm ở một phía có thể không có bản base. Các stage này là dữ liệu tạm trong index; sau khi giải quyết và chạy `git add <path>`, Git thay chúng bằng một entry stage 0 cho kết quả đã giải quyết.

## 8. Thực hiện merge để quan sát ba chiều

Giả sử branch `main` và `feature/payment` đã phân kỳ. Chuyển sang branch đích rồi merge:

```bash
git switch main
git merge feature/payment
```

Git tìm merge base giữa `main` và `feature/payment`, so sánh hai đầu nhánh với base, rồi tạo kết quả. Nếu có thể fast-forward, Git có thể chỉ di chuyển ref `main`; nếu hai branch đã phân kỳ, Git thường tạo merge commit sau khi kết hợp thành công.

Để chủ động yêu cầu tạo merge commit kể cả khi có thể fast-forward:

```bash
git merge --no-ff feature/payment
```

`--no-ff` điều khiển cách ghi lịch sử (tạo merge commit thay vì chỉ fast-forward). Nó không phải tùy chọn bật/tắt thuật toán ba chiều. Nếu hai branch đã phân kỳ, Git vẫn cần kết hợp thay đổi dựa trên merge base.

### Fast-forward khác merge ba chiều

Nếu tip của branch hiện tại là tổ tiên của branch được merge, Git có thể fast-forward:

```text
A---B---C  feature
     ^
    main
```

`main` chỉ cần di chuyển từ B đến C. Không có hai nhánh cùng tạo thay đổi riêng kể từ base, nên không cần kết hợp hai tập thay đổi và không tạo merge commit mặc định.

Khi hai branch đã phân kỳ:

```text
      C1---C2  feature
     /
A---B---M1---M2  main
```

Git phải kết hợp thay đổi từ hai phía dựa trên base B. Nếu thành công, một merge commit có thể được tạo với hai parent.

## 9. Merge commit ghi lại kết quả như thế nào?

Một merge commit hai parent chứa tree của kết quả hợp nhất và hai parent commit. Ví dụ:

```text
      C1---C2------+
     /             \
A---B---M1---M2-----M  main
```

Merge commit `M` có:

- Tree: snapshot sau khi hợp nhất.
- Parent thứ nhất: `M2`, tip của branch hiện tại trước merge.
- Parent thứ hai: `C2`, tip của branch được merge vào.
- Author/committer và thông điệp commit.

Xem thông tin parent:

```bash
git show -s --format="%H%n%P%n%s" HEAD
```

Nếu commit hiện tại là merge commit, dòng `%P` có hai OID parent (hoặc nhiều hơn trong merge nhiều head). Có thể xem nội dung merge:

```bash
git show --cc HEAD
git log --graph --oneline --decorate -10
```

Merge commit giữ lại quan hệ rằng hai lịch sử đã được kết hợp. Điều này khác với squash merge, vốn có thể tạo một commit đơn chứa kết quả thay đổi nhưng không ghi các commit feature làm parent.

## 10. Xem riêng thay đổi của hai phía so với merge base

Khi cần hiểu tại sao conflict xảy ra, hãy xem từng phía so với base.

Trước tiên tìm base:

```bash
BASE=$(git merge-base main feature/payment)
```

Sau đó so sánh base với main:

```bash
git diff "$BASE" main -- src/payment.js
```

Và so sánh base với feature:

```bash
git diff "$BASE" feature/payment -- src/payment.js
```

Hai diff cho thấy mỗi phía đã làm gì kể từ điểm chung. Trên PowerShell, có thể gán biến bằng:

```powershell
$base = git merge-base main feature/payment
git diff $base main -- src/payment.js
git diff $base feature/payment -- src/payment.js
```

Bạn cũng có thể đọc snapshot của từng phía:

```bash
git show "$BASE:src/payment.js"
git show "main:src/payment.js"
git show "feature/payment:src/payment.js"
```

Nếu tên branch hoặc path có ký tự đặc biệt, hãy đặt revision trong dấu nháy phù hợp với shell. Các lệnh này chỉ đọc dữ liệu, không thay đổi branch hay index.

## 11. Giải quyết conflict theo ba phiên bản

Khi merge dừng vì conflict, kiểm tra:

```bash
git status
git diff --cc
git ls-files -u
```

Với conflict nội dung văn bản, working tree thường chứa marker:

```text
<<<<<<< HEAD
return subtotal - discount;
=======
return subtotal + fee;
>>>>>>> feature/payment
```

Phần phía trên `=======` là nội dung ours; phần phía dưới là theirs trong merge đang thực hiện. Hãy đọc cả hai thay đổi cùng yêu cầu nghiệp vụ, sau đó chỉnh file thành kết quả đúng. Không chỉ xóa marker rồi giữ ngẫu nhiên một phía.

Khi cần xem ba phiên bản đầy đủ, dùng stage 1/2/3 như phần trước. Với merge conflict, bạn cũng có thể dùng:

```bash
git checkout --ours -- src/payment.js
git checkout --theirs -- src/payment.js
```

Hai lệnh trên chọn toàn bộ phiên bản của một phía cho file; chúng thường không phù hợp nếu cần kết hợp logic từ cả hai. Sau khi chỉnh xong:

```bash
git add src/payment.js
git status
```

Stage file đã giải quyết sẽ đánh dấu conflict đó hoàn tất. Sau khi tất cả conflict được giải quyết, kiểm tra diff và test rồi hoàn tất merge bằng `git commit` nếu Git chưa tự tạo commit.

Nếu quyết định hủy merge đang diễn ra:

```bash
git merge --abort
```

Lệnh này cố gắng đưa working tree và index về trạng thái trước khi merge. Để việc khôi phục đáng tin cậy, hãy bắt đầu merge từ trạng thái sạch; thay đổi chưa commit trước đó có thể khiến quá trình abort khó khôi phục chính xác.

## 12. Merge base trong lịch sử phức tạp

Trong đồ thị thông thường, hai branch chỉ có một merge base. Nhưng với kiểu lịch sử **criss-cross merge**, hai nhánh có thể merge lẫn nhau theo các hướng khác nhau mà không tạo một merge base duy nhất tốt nhất.

Ví dụ minh họa:

```text
       A1------M2  branch-A
      /  \    /
O----+    M1-+
      \  /    \
       B1------M3  branch-B
```

Sơ đồ chỉ nhằm gợi ý rằng hai phía đã merge chéo nhiều lần; đồ thị thực tế có thể có nhiều merge base tốt nhất. Kiểm tra:

```bash
git merge-base --all branch-A branch-B
```

Khi có nhiều merge base, Git không thể luôn chọn một commit đơn giản làm base theo ví dụ tuyến tính. Merge strategy hiện đại có thể tạo một **virtual merge base** (merge base ảo) bằng cách hợp nhất các merge base tốt nhất, rồi dùng kết quả đó làm điểm xuất phát cho lần merge chính.

Điều này giúp tránh việc tùy tiện chọn một base và bỏ sót thay đổi đã được kết hợp trong lịch sử chéo. Tuy nhiên, nó cũng làm việc đọc conflict phức tạp hơn: phiên bản base mà thuật toán dùng có thể là kết quả tổng hợp, không trùng nguyên vẹn với một commit đơn lẻ bạn thấy trong `git log`.

## 13. Merge strategy và vai trò của thuật toán

Git hỗ trợ nhiều merge strategy. Với merge hai branch thông thường, strategy mặc định hiện đại là `ort` (được dùng làm mặc định từ Git 2.34). Các phiên bản cũ thường dùng strategy `recursive`. Strategy chịu trách nhiệm xử lý quan hệ cây thư mục, rename và hợp nhất nội dung dựa trên các base phù hợp.

Bạn có thể xem trợ giúp:

```bash
git merge -h
git help merge
```

Một số strategy khác có mục đích riêng:

- `ort`: strategy mặc định cho merge hai head trong Git hiện đại.
- `recursive`: strategy hai head cũ hơn, vẫn có thể được chỉ định trên phiên bản hỗ trợ.
- `octopus`: dùng cho merge nhiều head; phù hợp khi có thể hợp nhất nhiều branch mà không cần xử lý conflict phức tạp. Nếu phát sinh conflict khó, octopus thường từ chối.
- `ours`: chọn tree của branch hiện tại làm kết quả, bỏ qua nội dung thay đổi của các head còn lại; không nhầm với tùy chọn `-X ours`.

Tùy chọn chiến lược `-X ours` có nghĩa là khi có xung đột nội dung, ưu tiên phiên bản ours cho các phần conflict; những thay đổi không xung đột từ phía kia vẫn được kết hợp. Nó khác hoàn toàn strategy `-s ours`, vốn tạo kết quả tree giống ours và bỏ qua thay đổi nội dung của các branch được merge.

Không chọn strategy hoặc tùy chọn ưu tiên một phía chỉ để làm merge hết conflict. Hãy hiểu thay đổi nghiệp vụ và kiểm tra kết quả sau merge.

## 14. Những điểm cần lưu ý khi đọc kết quả merge

- **Merge sạch không có nghĩa là đúng logic.** Git chỉ biết kết hợp nội dung, không hiểu quy tắc nghiệp vụ.
- **Ours/theirs thay đổi theo hướng merge.** Luôn xác định branch hiện tại và branch được merge.
- **Fast-forward không tạo merge commit mặc định.** Git chỉ di chuyển ref khi một đầu nhánh là tổ tiên của đầu kia.
- **`--no-ff` kiểm soát hình dạng lịch sử.** Nó không thay thế merge base hoặc thay đổi quy tắc hợp nhất ba chiều.
- **Rename detection là suy luận.** Git dùng độ tương đồng nội dung để nhận diện rename; kết quả có thể thay đổi theo ngưỡng và tình huống.
- **File nhị phân thường cần quyết định thủ công.** Git không thể hợp nhất các byte nhị phân theo ngữ nghĩa của ứng dụng.
- **Nhiều merge base làm base phức tạp hơn.** Dùng `git merge-base --all` nếu lịch sử có merge chéo.
- **Merge conflict có dữ liệu trong index.** `git ls-files -u` cho thấy các stage chưa giải quyết; `git add` ghi nhận kết quả đã giải quyết.
- **Kiểm tra trước khi commit.** Dùng `git diff`, `git diff --check`, chạy test và đọc lại các file đã hợp nhất.

## 15. Quy trình thực hành phân tích merge base và merge ba chiều

Trong repository thử nghiệm, tạo `main` và `feature/payment` từ một commit chung rồi sửa các vùng khác nhau trong cùng một file.

**Bước 1: Xác nhận hai branch và lịch sử**

```bash
git branch -vv
git log --graph --oneline --decorate --all
```

**Bước 2: Tìm merge base**

```bash
git merge-base main feature/payment
git merge-base --all main feature/payment
```

**Bước 3: Xem hai phía đã thay đổi gì so với base**

```bash
git diff <BASE> main
git diff <BASE> feature/payment
```

**Bước 4: Thực hiện merge**

```bash
git switch main
git merge --no-ff feature/payment
```

**Bước 5: Kiểm tra kết quả**

```bash
git status
git log --graph --oneline --decorate -10
git show -s --format="%H%n%P%n%s" HEAD
```

Nếu conflict, đọc ba phiên bản, chỉnh kết quả, stage file đã giải quyết và chạy test trước khi hoàn tất merge.

## 16. Bài tập thực hành

Tạo một repository thử nghiệm với commit nền `B`, sau đó tạo hai branch `main` và `feature/demo`.

1. Trên `main`, sửa phần kiểm tra đầu hàm trong `src/order.js`; trên `feature/demo`, thêm một phép tính độc lập ở cuối hàm.
2. Chạy `git merge-base main feature/demo` và xác định commit nền.
3. Dùng `git diff <BASE> main` và `git diff <BASE> feature/demo` để xem riêng thay đổi của hai phía.
4. Merge `feature/demo` vào `main`; xác nhận Git có thể tự kết hợp thay đổi không xung đột.
5. Tạo lại repository hoặc branch thử nghiệm khác, để cả hai phía sửa cùng một dòng theo hai cách khác nhau và quan sát conflict.
6. Dùng `git ls-files -u` và `git show :1:<path>`, `:2:<path>`, `:3:<path>` để đọc base, ours, theirs.
7. Giải quyết conflict bằng cách kết hợp logic của hai phía, chạy test, `git add` file và hoàn tất merge.
8. So sánh merge thường với fast-forward; dùng `--no-ff` để quan sát merge commit được tạo ngay cả khi có thể fast-forward.
9. Nếu có thể, tạo lịch sử merge chéo và chạy `git merge-base --all` để quan sát trường hợp có nhiều merge base.

Bạn hoàn thành bài tập khi giải thích được merge base là gì, Git dùng ba snapshot ra sao, vì sao thay đổi độc lập có thể tự kết hợp, khi nào xuất hiện conflict và cách xác định đúng base/ours/theirs trong index.
