# Chia một thay đổi lớn thành các commit rõ mục đích bằng chọn từng phần

Trong lúc làm một tính năng, bạn có thể sửa nhiều file và vô tình kết hợp nhiều loại công việc trong cùng working tree: sửa lỗi, đổi tên hàm, bổ sung kiểm thử, cập nhật tài liệu và thêm hành vi mới. Nếu stage tất cả rồi commit một lần, lịch sử sẽ khó review và khó hoàn tác từng phần.

Git cho phép chọn từng phần thay đổi vào **index** bằng `git add -p` (patch mode). Bạn có thể stage một số hunk hoặc một số dòng, tạo commit cho một mục đích, rồi tiếp tục stage phần còn lại để tạo commit tiếp theo. Kỹ thuật này giúp chia một thay đổi lớn thành các commit nhỏ, dễ hiểu và có thể kiểm tra độc lập.

## 1. Mục tiêu của bài thực hành

Bạn sẽ thực hành với một working tree có nhiều thay đổi đan xen và tạo ra các commit theo mục đích. Ví dụ, trong một lần làm việc với luồng thanh toán, bạn đã:

- Tách logic kiểm tra dữ liệu khỏi hàm xử lý lớn để mã dễ đọc hơn.
- Sửa lỗi kiểm tra số tiền âm.
- Bổ sung kiểm thử cho trường hợp số tiền không hợp lệ.
- Thêm quy tắc kiểm tra thuế cho tính năng mới.
- Cập nhật tài liệu API.

Những thay đổi này có thể nằm trong cùng một file hoặc trải trên nhiều file. Mục tiêu là tạo các commit có phạm vi rõ ràng, chẳng hạn:

1. `Refactor payment validation` — chỉ tái cấu trúc logic, giữ nguyên hành vi.
2. `Fix negative payment amount` — sửa lỗi và kiểm thử hồi quy tương ứng.
3. `Add tax validation` — thêm hành vi mới, kiểm thử và tài liệu liên quan.

Không nhất thiết phải tạo đúng ba commit trong mọi dự án. Hãy nhóm theo mục đích và quan hệ phụ thuộc: một commit nên giải thích được nó thay đổi điều gì và vì sao.

## 2. Hiểu hai vùng diff trước khi chọn từng phần

Git có ba trạng thái cần theo dõi khi bạn chuẩn bị commit:

- `HEAD`: snapshot của commit hiện tại.
- Index: nội dung đã stage, sẽ đi vào commit tiếp theo.
- Working tree: nội dung hiện tại trên đĩa.

Hai lệnh diff quan trọng:

```bash
# Thay đổi chưa stage: working tree so với index
git diff

# Thay đổi đã stage: index so với HEAD
git diff --cached
```

Ví dụ, nếu một file đã có cả phần sửa được stage và phần sửa chưa stage, `git diff --cached` chỉ hiển thị phần dự định đưa vào commit tiếp theo; `git diff` hiển thị phần còn lại so với index.

Kiểm tra tổng quan trước khi thao tác:

```bash
git status --short
git diff --stat
git diff
git diff --cached
```

Đừng bắt đầu stage từng phần khi chưa hiểu working tree đang chứa những thay đổi nào. Nếu có thay đổi từ công việc trước, commit hoặc lưu riêng chúng để tránh trộn vào nhóm commit hiện tại.

## 3. Tạo thay đổi thử nghiệm có nhiều mục đích

Giả sử repository có các file:

```text
src/payment.js
tests/payment.test.js
docs/payment-api.md
```

Trong `src/payment.js`, bạn vừa đổi tên một biến và tách hàm kiểm tra, đồng thời thêm nhánh kiểm tra thuế. Trong file test, bạn thêm cả test cho lỗi số tiền âm lẫn test cho quy tắc thuế. Tài liệu API chỉ liên quan đến tính năng thuế.

Xem toàn bộ thay đổi:

```bash
git status
git diff -- src/payment.js
git diff -- tests/payment.test.js
git diff -- docs/payment-api.md
```

Nếu các thay đổi còn nằm trong cùng file, đừng stage cả file bằng `git add src/payment.js`, vì thao tác đó sẽ đưa tất cả thay đổi của file vào index. Hãy dùng patch mode để chọn phần cần thiết.

## 4. Chọn hunk bằng git add -p

Cú pháp:

```bash
git add -p [<pathspec>...]
```

Không chỉ định đường dẫn thì Git duyệt các thay đổi phù hợp trong working tree. Chỉ định đường dẫn giúp tập trung vào một số file:

```bash
git add -p -- src/payment.js tests/payment.test.js
```

Git hiển thị từng hunk (nhóm dòng khác biệt) và hỏi bạn có muốn stage hunk đó không. Bạn chọn `y` để stage hunk, `n` để bỏ qua và tiếp tục xem hunk kế tiếp.

Các phím thường dùng trong chế độ tương tác:

| Phím | Ý nghĩa |
|---|---|
| `y` | Stage hunk đang hiển thị vào index |
| `n` | Không stage hunk này, chuyển sang hunk tiếp theo |
| `q` | Thoát, giữ các hunk đã chọn trước đó |
| `a` | Stage hunk hiện tại và các hunk còn lại của file hiện tại |
| `d` | Bỏ qua hunk hiện tại và các hunk còn lại của file hiện tại |
| `s` | Chia hunk thành các hunk nhỏ hơn nếu có thể |
| `e` | Mở patch để chỉnh sửa thủ công |
| `?` | Hiển thị trợ giúp các lựa chọn |

Tùy phiên bản Git và chế độ tương tác, còn có các phím điều hướng hoặc tìm kiếm hunk. Nhập `?` ngay tại dấu nhắc để xem danh sách chính xác mà phiên bản của bạn hỗ trợ.

### Chọn thay đổi theo mục đích

Ví dụ, lần đầu bạn muốn tạo commit tái cấu trúc. Chạy:

```bash
git add -p -- src/payment.js tests/payment.test.js
```

Ở từng hunk, chỉ chọn các dòng phục vụ việc tách hàm và đổi tên biến. Bỏ qua hunk thêm quy tắc thuế. Trong file test, chọn các thay đổi chỉ hỗ trợ tái cấu trúc nếu chúng cần thiết để xác nhận hành vi cũ vẫn được giữ nguyên; bỏ qua test thuế vì nó thuộc commit tính năng sau.

Sau khi chọn xong, xem lại index:

```bash
git diff --cached
git diff
```

Đọc `git diff --cached` như bản nháp của commit đầu tiên. Nếu nó chứa cả logic thuế hoặc tài liệu API, quay lại bỏ staging phần không thuộc mục đích đó.

## 5. Chia một hunk lớn bằng phím s

Git gom các dòng gần nhau thành một hunk để cung cấp đủ ngữ cảnh. Một hunk có thể chứa nhiều thay đổi độc lập. Nếu Git hiển thị:

```text
@@ -20,5 +20,6 @@ function calculatePayment(order) {
-  const subtotal = getSubtotal(order);
-  if (subtotal < 0) throw new Error("Invalid subtotal");
+  const amount = getSubtotal(order);
+  if (amount < 0) throw new Error("Invalid subtotal");
   const fee = calculateFee(order);
-  return subtotal + fee;
+  const tax = calculateTax(order);
+  return amount + fee + tax;
 }
```

Hunk này có thể trộn tái cấu trúc và tính năng thuế. Tại dấu nhắc patch, nhập:

```text
s
```

Git sẽ cố chia hunk thành các phần nhỏ hơn dựa trên khoảng cách giữa các thay đổi. Sau đó bạn có thể chọn phần đổi tên/chuẩn hóa riêng và để phần thuế lại cho commit sau.

Không phải hunk nào cũng chia được. Nếu các dòng thay đổi nằm sát nhau hoặc phụ thuộc vào nhau, Git có thể thông báo không thể split. Khi đó, hãy cân nhắc chỉnh sửa patch thủ công bằng `e`, hoặc tách thay đổi trong working tree thành các bước dễ stage hơn.

## 6. Chỉnh sửa patch thủ công bằng e

Khi `s` không chia được hunk theo cách mong muốn, phím `e` mở patch trong editor để bạn chọn dòng cụ thể. Cách này mạnh nhưng đòi hỏi hiểu định dạng unified diff.

Trong patch:

- Dòng bắt đầu bằng dấu cách là ngữ cảnh, dùng để xác định vị trí áp dụng.
- Dòng bắt đầu bằng `-` là nội dung cũ bị thay thế hoặc xóa.
- Dòng bắt đầu bằng `+` là nội dung mới được thêm vào.
- Dòng `@@ ... @@` là header mô tả phạm vi hunk.

Khi chỉnh sửa, giữ các dòng ngữ cảnh cần thiết và chỉ giữ phần thay đổi bạn muốn stage. Với một thay đổi thay thế, cần bảo đảm phần dòng cũ và dòng mới trong patch mô tả một phép biến đổi hợp lệ. Nếu patch sai định dạng hoặc không áp dụng được, Git có thể từ chối phần đó; kiểm tra lại index và working tree sau khi thoát editor.

Vì chỉnh sửa patch dễ tạo ra một phiên bản trung gian không hợp lệ, hãy ưu tiên `s` khi có thể. Sau khi dùng `e`, luôn xem:

```bash
git diff --cached
git diff
```

Đảm bảo index chứa đúng dòng cần commit và working tree vẫn giữ các dòng còn lại. Không chỉnh sửa header hoặc số dòng của hunk nếu bạn chưa hiểu tác động của chúng.

## 7. Tạo commit đầu tiên rồi tiếp tục stage phần còn lại

Sau khi đã chọn các hunk thuộc mục đích đầu tiên, kiểm tra nội dung và tạo commit:

```bash
git diff --cached --check
git diff --cached
git status --short
git commit -m "Refactor payment validation"
```

`git diff --cached --check` kiểm tra các lỗi whitespace phổ biến trong phần đã stage. `git commit` tạo commit từ index hiện tại; những thay đổi chưa stage trong working tree vẫn còn sau commit.

Kiểm tra trạng thái sau commit:

```bash
git show --stat --oneline HEAD
git status --short
git diff
git diff --cached
```

Nếu còn phần thay đổi cho lỗi số tiền âm và tính năng thuế, chúng vẫn ở working tree. Tiếp tục chọn phần phục vụ commit thứ hai:

```bash
git add -p -- src/payment.js tests/payment.test.js
git diff --cached
git diff
git diff --cached --check
git commit -m "Fix negative payment amount"
```

Cuối cùng, stage phần tính năng thuế và tài liệu:

```bash
git add -p -- src/payment.js tests/payment.test.js
git add docs/payment-api.md
git diff --cached
git diff --cached --check
git commit -m "Add tax validation"
```

Trong bước cuối, `git add docs/payment-api.md` phù hợp nếu toàn bộ thay đổi trong tài liệu thuộc tính năng thuế. Nếu file tài liệu cũng có nhiều mục đích đan xen, dùng `git add -p` cho file đó.

## 8. Khi nào dùng git add -p, git add -e và git add theo đường dẫn?

| Cách stage | Phù hợp khi | Hạn chế |
|---|---|---|
| `git add <path>` | Toàn bộ thay đổi của file thuộc cùng một commit | Stage cả phần thay đổi khác mục đích trong file |
| `git add -p` | Muốn chọn từng hunk trong một hoặc nhiều file | Hunk có thể chứa các thay đổi đan xen khó tách |
| `git add -e` | Cần chỉnh patch để chọn từng dòng trong hunk | Dễ làm patch không hợp lệ nếu sửa sai cấu trúc |
| `git add -A` | Muốn stage mọi thay đổi trong repository | Thường không phù hợp khi cần tách commit theo mục đích |

Có thể gọi chế độ edit trực tiếp:

```bash
git add -e -- src/payment.js
```

Lệnh này mở patch cho đường dẫn đã chọn để bạn chỉnh sửa nội dung patch. Nếu bạn chỉ cần chọn hunk, `git add -p` thường dễ kiểm soát hơn.

## 9. Bỏ staging một phần nếu chọn nhầm

Nếu đã stage nhầm một hunk, bạn có thể đưa riêng phần đó ra khỏi index bằng patch mode:

```bash
git restore --staged -p -- src/payment.js
```

Git hiển thị khác biệt giữa `HEAD` và index để bạn chọn hunk cần khôi phục. Chọn `y` cho hunk muốn bỏ staging. Working tree được giữ nguyên.

Cách tương đương truyền thống:

```bash
git reset -p -- src/payment.js
```

Hai lệnh trên chỉ điều chỉnh index theo các hunk được chọn, không xóa phần chỉnh sửa trên đĩa. Sau đó kiểm tra lại:

```bash
git diff --cached -- src/payment.js
git diff -- src/payment.js
```

Nếu muốn bỏ staging toàn bộ file, dùng:

```bash
git restore --staged -- src/payment.js
```

Đừng dùng `git restore --worktree` khi mục tiêu chỉ là bỏ staging; tùy chọn đó tác động lên nội dung file trong working tree.

## 10. Giữ commit độc lập và có thể kiểm thử

Chia commit theo từng phần không chỉ là làm lịch sử gọn. Mỗi commit nên ở trạng thái có thể hiểu và, nếu có thể, kiểm thử độc lập.

Ví dụ thứ tự hợp lý:

1. Tái cấu trúc hàm kiểm tra mà không đổi hành vi.
2. Sửa lỗi kiểm tra số tiền âm và thêm test hồi quy.
3. Bổ sung quy tắc thuế, test và tài liệu API.

Nếu tính năng mới phụ thuộc vào một refactor, commit refactor nên đứng trước commit tính năng. Nếu test chỉ chạy được sau khi có hành vi mới, hãy đặt test trong cùng commit với hành vi đó. Tránh tạo commit đầu tiên không biên dịch được hoặc để test đỏ mà không có lý do rõ ràng.

Sau mỗi commit, có thể kiểm tra:

```bash
git show --stat --oneline HEAD
git show --format=fuller --no-ext-diff HEAD
```

Nếu cần kiểm thử chính xác snapshot đã stage trước khi commit, có thể dùng `git stash push --keep-index` để tạm cất phần chưa stage, chạy test với index hiện tại, rồi khôi phục phần còn lại bằng `git stash pop`. Chỉ dùng khi hiểu trạng thái working tree và đã kiểm tra stash; không để các thay đổi chưa stage bị bỏ quên.

## 11. Những lỗi thường gặp khi chọn từng phần

### Stage cả file ngoài ý muốn

Bạn dùng `git add src/payment.js` sau khi đã chọn một số hunk. Lệnh này stage toàn bộ trạng thái hiện tại của file, bao gồm những thay đổi trước đó còn chưa stage. Hãy dùng `git add -p` cho lần chọn tiếp theo và kiểm tra `git diff --cached` trước commit.

### Hunk chứa nhiều mục đích và không thể split

Git không tách được bằng `s` vì các thay đổi quá gần nhau. Dùng `e` nếu hiểu patch, hoặc tách thao tác sửa code thành các bước độc lập trong working tree rồi chạy lại `git add -p`.

### Commit thiếu phần cần thiết

Bạn stage code nhưng quên stage test hoặc tài liệu cần thiết. Trước khi commit, đọc lại toàn bộ `git diff --cached` và kiểm tra danh sách file bằng `git status --short`. Nếu commit đã tạo nhưng chưa chia sẻ, có thể bổ sung bằng `git commit --amend`; nếu đã chia sẻ, cân nhắc tạo commit mới theo quy trình nhóm.

### Dùng git commit -a sau khi chọn patch

`git commit -a` tự stage các thay đổi của file tracked trước khi commit, vì vậy có thể đưa cả phần bạn cố ý để lại vào commit. Khi đang chia commit bằng patch mode, dùng `git commit` thông thường để commit đúng index hiện tại.

### File mới hoặc file nhị phân

Patch mode chủ yếu hữu ích cho diff văn bản của file tracked. File nhị phân không thể chia theo dòng như file text. Với file mới chưa được theo dõi, stage theo đường dẫn nếu toàn bộ file thuộc cùng một mục đích; nếu cần chia nội dung, hãy tạo nội dung hoặc file riêng theo cấu trúc phù hợp trước khi stage.

## 12. Quy trình kiểm tra trước mỗi commit

Trước mỗi lần commit, thực hiện một lượt kiểm tra nhất quán:

```bash
# Những gì sẽ vào commit
git diff --cached

# Những gì vẫn còn ở working tree, chưa stage
git diff

# Danh sách trạng thái file
git status --short

# Kiểm tra whitespace trong phần staged
git diff --cached --check
```

Tự trả lời ba câu hỏi:

1. Tất cả thay đổi trong index có cùng một mục đích không?
2. Commit này có chứa đủ code/test/tài liệu cần thiết để hiểu và kiểm tra thay đổi không?
3. Có file cấu hình local, secret, output build hoặc thay đổi không liên quan nào bị stage nhầm không?

Nếu câu trả lời chưa rõ, tiếp tục điều chỉnh index bằng `git add -p` hoặc `git restore --staged -p` trước khi commit.

## 13. Bài tập thực hành tổng hợp

Trong một repository thử nghiệm, tạo một commit nền rồi sửa ít nhất hai file text theo ba mục đích khác nhau: refactor, sửa lỗi và thêm tính năng. Để các thay đổi của ít nhất một file đan xen trong cùng một hunk.

1. Dùng `git status`, `git diff` và `git diff --stat` để khảo sát toàn bộ thay đổi.
2. Chạy `git add -p` và stage riêng các hunk phục vụ refactor.
3. Nếu một hunk chứa cả refactor và tính năng, thử `s`; nếu không thể split, dùng `e` trong editor để chọn phần phù hợp.
4. Dùng `git diff --cached` và `git diff` để xác nhận index và working tree chứa hai nhóm nội dung khác nhau.
5. Chạy `git diff --cached --check`, tạo commit refactor và xem bằng `git show --stat HEAD`.
6. Tiếp tục stage phần sửa lỗi cùng test hồi quy, tạo commit thứ hai.
7. Stage phần tính năng cùng test và tài liệu, tạo commit thứ ba.
8. Cố ý stage nhầm một hunk trong môi trường thử nghiệm, sau đó dùng `git restore --staged -p` để bỏ staging hunk đó mà vẫn giữ nội dung working tree.
9. Chạy `git log --oneline -3` và giải thích mục đích của từng commit.

Bạn hoàn thành bài tập khi tạo được các commit riêng biệt theo mục đích, không làm mất phần thay đổi còn lại trong working tree và có thể chứng minh nội dung mỗi commit bằng `git show` hoặc `git diff --cached` trước khi commit.
