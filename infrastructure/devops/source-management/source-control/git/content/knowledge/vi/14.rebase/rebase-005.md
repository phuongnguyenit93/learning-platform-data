# Tạo fixup commit và sắp xếp tự động bằng `--autosquash`

Trong quá trình phát triển, đôi khi ta nhận ra một commit trước đó còn thiếu một dòng kiểm tra, có lỗi nhỏ hoặc cần cập nhật tài liệu. Ta có thể tạo thêm một commit để sửa, nhưng nếu nhánh chưa được chia sẻ và muốn lịch sử gọn gàng, thường nên gộp phần sửa đó vào commit ban đầu. Git hỗ trợ quy trình này bằng **fixup commit** và tùy chọn `--autosquash` của interactive rebase.

`git commit --fixup=<commit>` tạo một commit sửa đổi có tiêu đề được gắn tiền tố `fixup!` và chỉ rõ commit đích. Khi chạy `git rebase -i --autosquash <base>`, Git tự tìm commit đích, chuyển fixup commit đến ngay sau commit đó và đánh dấu hành động `fixup`. Sau khi rebase hoàn tất, phần thay đổi được gộp vào commit đích và commit fixup không còn xuất hiện riêng trong lịch sử.

Đây là cách tổ chức lịch sử hữu ích khi làm việc với nhánh tính năng, chuẩn bị pull request hoặc chỉnh sửa các commit trước khi chia sẻ. Vì rebase viết lại lịch sử, cần hiểu phạm vi commit bị thay mã định danh và thống nhất với nhóm trước khi áp dụng lên nhánh đã được người khác sử dụng.

## 1. Fixup commit giải quyết vấn đề gì?

Giả sử ta đã tạo commit `Add login validation`, sau đó phát hiện cần bổ sung một điều kiện kiểm tra đầu vào. Nếu tạo commit thông thường, lịch sử có thể thành:

```text
A --- B --- C --- D
      ^           ^
      |           HEAD
      commit cần sửa
```

Ta tạo thêm commit `Fix login validation` ở cuối nhánh. Lịch sử lúc này có thêm một commit sửa nằm xa commit gốc:

```text
A --- B --- C --- D --- F
      ^                   ^
      |                   HEAD
      commit cần sửa      commit sửa bổ sung
```

Về mặt nội dung, thay đổi trong `F` thuộc về công việc được thực hiện ở `B`. Nếu giữ nguyên lịch sử này, người review phải đọc thêm một commit nhỏ để hiểu một phần công việc đã có từ trước. Với một nhánh tính năng có nhiều lần chỉnh sửa, lịch sử dễ trở nên rời rạc.

Fixup commit giúp ghi nhận rõ commit đích ngay từ lúc tạo. Sau đó, autosquash sắp xếp fixup vào đúng vị trí để ta kiểm tra và gộp trong một lần rebase:

```text
Trước autosquash:
A --- B --- C --- D --- F
      ^                   ^
      commit đích         fixup! B

Sau rebase --autosquash:
A --- B' --- C' --- D'
      ^
      B' chứa cả thay đổi ban đầu và phần sửa từ F
```

Các commit sau `B` được tạo lại khi rebase, nên mã commit của chúng thay đổi dù nội dung có thể giữ nguyên. Commit mới `B'` chứa cả nội dung của `B` và phần sửa từ `F`; commit `F` không còn là một commit riêng.

## 2. Tạo fixup commit bằng `git commit --fixup`

Trước tiên, tìm commit cần sửa:

```bash
git log --oneline --decorate -10
```

Ví dụ kết quả:

```text
8c42d19 (HEAD -> feature/login) Add login error response
7b31a20 Add login validation
51d0a87 Create login endpoint
```

Ta muốn bổ sung điều kiện kiểm tra vào commit `7b31a20`. Sau khi chỉnh sửa file, stage đúng phần thay đổi rồi tạo fixup commit:

```bash
git add src/main/java/example/LoginValidator.java
git commit --fixup=7b31a20
```

Git tạo commit mới với tiêu đề dạng:

```text
fixup! Add login validation
```

Nội dung của fixup commit là phần thay đổi đang được stage. Git sử dụng commit được chỉ định để tạo tiêu đề có thể nhận diện tự động trong bước autosquash. Vì vậy, hãy truyền đúng commit đích, thường là mã commit hoặc một tham chiếu xác định duy nhất.

Kiểm tra kết quả:

```bash
git log --oneline --decorate -5
git show --stat --oneline HEAD
```

Ta sẽ thấy commit `fixup! ...` ở đầu lịch sử. Ở thời điểm này, thay đổi vẫn là một commit độc lập; nó chỉ được gộp khi thực hiện rebase autosquash.

### Chỉ đưa phần sửa cần thiết vào fixup

Nếu working tree có nhiều thay đổi thuộc các mục đích khác nhau, không nên stage tất cả một cách máy móc. Có thể chọn từng file:

```bash
git add src/main/java/example/LoginValidator.java
```

Hoặc chọn từng phần trong file:

```bash
git add -p
```

Sau đó kiểm tra nội dung đã stage trước khi commit:

```bash
git diff --cached
git status --short
```

`git commit --fixup` chỉ tạo commit từ nội dung đã stage như một commit thông thường. Nếu stage nhầm file hoặc đưa vào cả phần việc chưa hoàn chỉnh, fixup commit sẽ mang theo những thay đổi đó và có thể làm hỏng kết quả sau khi gộp.

## 3. Tự động sắp xếp bằng `git rebase -i --autosquash`

Sau khi tạo một hoặc nhiều fixup commit, chạy interactive rebase với commit nền nằm trước commit đích:

```bash
git rebase -i --autosquash <base>
```

`<base>` là commit mà ta muốn dùng làm điểm bắt đầu để phát lại lịch sử; các commit sau `<base>` thuộc phạm vi rebase. Nếu commit đích là `7b31a20` và commit cha của nó là `51d0a87`, có thể chạy:

```bash
git rebase -i --autosquash 51d0a87
```

Điểm quan trọng là `<base>` phải nằm trước commit đích. Nếu chọn chính commit đích làm upstream, Git sẽ không đưa commit đó vào danh sách rebase và không thể gộp fixup vào nó.

Trước khi autosquash, lịch sử có thể là:

```text
51d0a87 --- 7b31a20 --- 8c42d19 --- f93e0b1
              ^                         ^
              commit đích               fixup commit ở HEAD
```

Trong todo list của interactive rebase, Git tự chuyển fixup đến ngay sau commit đích và đổi lệnh của nó thành `fixup`:

```text
pick 7b31a20 Add login validation
fixup a12bc34 fixup! Add login validation
pick 8c42d19 Add login error response
pick f93e0b1 Update login endpoint documentation
```

Ý nghĩa:

- `pick`: áp dụng commit như một commit riêng.
- `fixup`: áp dụng thay đổi của commit hiện tại vào commit trước đó và bỏ thông điệp commit hiện tại.
- `squash`: gộp thay đổi vào commit trước đó và cho phép kết hợp thông điệp commit.

Với `--autosquash`, ta vẫn có thể đọc và chỉnh todo list trước khi lưu, thoát editor để bắt đầu rebase. Nếu có nhiều fixup commit cho cùng một commit đích, Git sắp xếp chúng cạnh commit đó để các phần sửa được áp dụng lần lượt.

Sau khi rebase thành công, lịch sử trở thành:

```text
51d0a87 --- b6e4c91 --- 9a2f7d0 --- 4c0e1b3
              ^                         ^
              commit đã gộp fixup       HEAD mới
```

Các mã commit mới chỉ là ví dụ. Commit đích và các commit phía sau được tạo lại; fixup commit được hấp thụ vào commit đích và không còn xuất hiện như một mục riêng.

## 4. Quy trình hoàn chỉnh từ sửa lỗi đến kiểm tra lịch sử

Thực hiện trong một nhánh tính năng riêng, với các commit đã tạo nhưng chưa cần giữ nguyên mã định danh cũ.

### Bước 1: Xác định commit cần chỉnh sửa

```bash
git status -sb
git log --oneline --decorate --graph -10
```

Đảm bảo ta đang ở đúng nhánh và nhận diện chính xác commit cần sửa. Có thể xem đầy đủ commit để xác nhận nội dung và thông điệp:

```bash
git show --stat 7b31a20
git show 7b31a20
```

### Bước 2: Sửa nội dung và stage phần thay đổi

Chỉnh sửa mã nguồn, kiểm tra diff rồi stage:

```bash
git diff
git add -p
git diff --cached
```

Đảm bảo phần đã stage chỉ thuộc về commit đích. Nếu có nhiều thay đổi độc lập, tạo fixup riêng cho từng commit tương ứng để lịch sử sau khi autosquash vẫn rõ ràng.

### Bước 3: Tạo fixup commit

```bash
git commit --fixup=7b31a20
```

Kiểm tra tiêu đề fixup và nội dung:

```bash
git log --oneline -5
git show --stat HEAD
```

### Bước 4: Xác định commit nền

Tìm commit cha của commit đích:

```bash
git rev-parse 7b31a20^
```

Nếu kết quả là `51d0a87`, đây là điểm bắt đầu có thể dùng trong ví dụ này. Với commit gốc đầu tiên của repository, không có commit cha; khi cần viết lại từ commit gốc có thể dùng `--root`, nhưng cần cân nhắc kỹ phạm vi lịch sử bị tạo lại.

### Bước 5: Chạy autosquash

```bash
git rebase -i --autosquash 51d0a87
```

Kiểm tra todo list do Git sắp xếp. Xác nhận mỗi dòng `fixup!` nằm ngay sau commit đích mong muốn, rồi lưu và đóng editor để tiếp tục.

### Bước 6: Xác minh sau rebase

```bash
git status -sb
git log --oneline --decorate --graph -10
git show --stat HEAD
```

Kiểm tra commit đích đã chứa phần sửa, fixup commit không còn tồn tại riêng trong phạm vi lịch sử mới và working tree không có thay đổi ngoài dự kiến. Chạy lại test hoặc kiểm tra liên quan đến phần mã vừa sửa.

Nếu đang chỉnh sửa một chuỗi commit dài, có thể dùng `git range-diff` để so sánh chuỗi commit trước và sau rebase. Công cụ này giúp nhận ra patch nào thay đổi ngoài dự kiến khi commit được tạo lại.

## 5. Phân biệt `fixup`, `squash` và `autosquash`

Các khái niệm này liên quan nhưng không đồng nghĩa:

| Cơ chế | Cách hoạt động | Thông điệp commit sau khi gộp |
| --- | --- | --- |
| `fixup` trong todo list | Gộp thay đổi vào commit ngay trước đó | Giữ thông điệp của commit trước, bỏ thông điệp fixup |
| `squash` trong todo list | Gộp thay đổi vào commit ngay trước đó | Kết hợp thông điệp các commit, cho phép chỉnh sửa |
| `--autosquash` | Tự tìm và sắp xếp các commit `fixup!`/`squash!` cạnh commit đích trong interactive rebase | Hành động cuối cùng phụ thuộc tiền tố và todo list |

`--autosquash` không tự tạo fixup commit. Nó chỉ sắp xếp các commit đã được đánh dấu bằng tiêu đề tương ứng khi chạy interactive rebase. Ngược lại, `git commit --fixup=<commit>` tạo commit có dấu hiệu để autosquash nhận diện, nhưng không tự thực hiện rebase.

Nếu muốn kết hợp cả thông điệp, có thể dùng `git commit --squash=<commit>` để tạo commit có tiền tố `squash!`. Khi autosquash, Git đánh dấu commit đó bằng hành động `squash` thay vì `fixup`.

## 6. Các biến thể `--fixup=amend` và `--fixup=reword`

Ngoài fixup thông thường, các phiên bản Git hỗ trợ thêm biến thể để cập nhật cả thông điệp commit đích.

### `--fixup=amend:<commit>`

```bash
git commit --fixup=amend:7b31a20
```

Biến thể này tạo commit có tiêu đề `amend! ...`. Khi autosquash, Git dùng hành động `fixup -C`: thay đổi nội dung được gộp vào commit đích và thông điệp của commit đích được thay bằng thông điệp từ commit amend. Đây là lựa chọn phù hợp khi phần sửa cần đi kèm việc viết lại thông điệp commit ban đầu cho chính xác hơn.

### `--fixup=reword:<commit>`

```bash
git commit --fixup=reword:7b31a20
```

Biến thể này tạo một commit chỉ nhằm thay đổi thông điệp commit đích. Nó tương đương với `--fixup=amend:<commit> --only`, do đó các thay đổi đang stage không được đưa vào commit reword. Khi autosquash, nội dung của commit đích được giữ lại và thông điệp được thay bằng thông điệp mới.

Các biến thể `amend` và `reword` cần phiên bản Git có hỗ trợ. Nếu Git báo không nhận cú pháp, hãy kiểm tra `git --version` và tài liệu tương ứng với phiên bản đang cài. Với nhu cầu gộp thay đổi mã nguồn thông thường, `git commit --fixup=<commit>` vẫn là lựa chọn đơn giản.

## 7. Tự động bật autosquash trong interactive rebase

Nếu thường xuyên dùng fixup commit, có thể bật cấu hình:

```bash
git config --global rebase.autoSquash true
```

Sau khi bật, các lần chạy interactive rebase sẽ tự áp dụng autosquash theo cấu hình, ví dụ:

```bash
git rebase -i <base>
```

Muốn xem giá trị đang có:

```bash
git config --show-origin --get rebase.autoSquash
```

Muốn tắt cấu hình toàn cục:

```bash
git config --global --unset rebase.autoSquash
```

Có thể chỉ định `--no-autosquash` cho một lần rebase nếu muốn giữ nguyên vị trí các commit đánh dấu. Cấu hình toàn cục ảnh hưởng tới mọi repository của người dùng, vì vậy chỉ bật khi quy trình làm việc thường xuyên cần hành vi này.

## 8. Xử lý xung đột trong quá trình autosquash

Fixup commit được áp dụng vào vị trí của commit đích. Nếu các commit ở giữa đã thay đổi cùng dòng mã, phần sửa có thể phát sinh xung đột khi Git phát lại lịch sử.

Khi rebase dừng, xem trạng thái:

```bash
git status
```

Mở các file xung đột, chọn nội dung đúng theo mục tiêu của commit đích, xóa dấu phân cách xung đột rồi stage kết quả:

```bash
git add src/main/java/example/LoginValidator.java
git rebase --continue
```

Git tiếp tục áp dụng các commit còn lại. Có thể lặp lại quy trình nếu một commit khác tiếp tục xung đột.

Nếu nhận ra đang sửa sai hoặc không muốn tiếp tục rebase:

```bash
git rebase --abort
```

Lệnh này hủy phiên rebase đang diễn ra và đưa nhánh về trạng thái trước khi bắt đầu rebase. `git rebase --skip` bỏ qua commit hiện tại; chỉ dùng khi đã xác nhận phần thay đổi đó không còn cần thiết hoặc đã được áp dụng theo cách khác. Bỏ qua một fixup có thể làm mất phần sửa mà ta định gộp.

Không nên giải quyết xung đột bằng cách chọn toàn bộ một phía theo thói quen. Hãy xác định nội dung cần giữ trong commit đích, đối chiếu thay đổi gốc và chạy lại kiểm tra liên quan sau khi rebase hoàn tất.

## 9. Giới hạn và lưu ý khi sử dụng autosquash

### Commit đích phải nằm trong phạm vi rebase

Autosquash chỉ có thể sắp xếp các commit nằm trong danh sách interactive rebase. Nếu `<base>` bằng hoặc nằm sau commit đích, commit đích không được phát lại nên fixup không thể gộp vào đó. Chọn commit cha của commit đích hoặc một base cũ hơn phù hợp.

### Tiêu đề commit nên đủ rõ để nhận diện

Git tạo tiền tố `fixup!` dựa trên tiêu đề commit đích. Nếu dự án có nhiều commit cùng tiêu đề, hãy xem kỹ todo list trước khi xác nhận. Dùng mã commit đúng khi tạo fixup và kiểm tra vị trí mà autosquash chọn để tránh gộp nhầm vào một commit trùng tiêu đề.

### Rebase viết lại lịch sử

Khi một commit được gộp hoặc chỉnh sửa, commit đó nhận mã mới. Các commit con phía sau cũng được tạo lại vì parent của chúng thay đổi. Điều này ảnh hưởng tới các nhánh hoặc bản sao khác đang dựa trên mã commit cũ.

Ưu tiên autosquash trước khi chia sẻ nhánh. Không tự ý rebase nhánh dùng chung hoặc các commit mà thành viên khác đã dựa vào, trừ khi nhóm thống nhất kế hoạch cập nhật lịch sử.

### Nếu nhánh đã được push

Sau khi rebase một nhánh đã có trên remote, lịch sử local không còn fast-forward với lịch sử remote cũ. Nếu nhóm cho phép cập nhật nhánh đã viết lại, hãy fetch trước, xác nhận không có commit mới của người khác và dùng `--force-with-lease` để giảm nguy cơ ghi đè thay đổi mới:

```bash
git fetch origin
git log --oneline --left-right origin/feature/login...feature/login
git push --force-with-lease origin feature/login
```

`--force-with-lease` kiểm tra remote ref vẫn ở giá trị mà local kỳ vọng trước khi cập nhật. Nó an toàn hơn `--force`, nhưng vẫn có thể ghi lại lịch sử của nhánh remote; cần tuân thủ quy trình review và phối hợp của nhóm. Không dùng force push trên nhánh được bảo vệ hoặc nhánh chia sẻ nếu chưa được cho phép.

## 10. Một số lỗi và cách xử lý

| Tình huống | Nguyên nhân có thể có | Cách kiểm tra hoặc xử lý |
| --- | --- | --- |
| Autosquash không đưa fixup tới commit mong muốn | Chọn sai base hoặc tiêu đề commit trùng nhau | Kiểm tra todo list; chọn base trước commit đích và xác nhận commit được đánh dấu |
| Fixup vẫn xuất hiện như commit riêng | Rebase chưa chạy hoặc fixup nằm ngoài phạm vi rebase | Chạy interactive rebase với `--autosquash` và base phù hợp |
| Git báo không có thay đổi để commit | Phần sửa chưa được stage hoặc nội dung đã giống commit đích | Kiểm tra `git status`, `git diff` và `git diff --cached` |
| Rebase dừng vì conflict | Patch của fixup không áp dụng sạch trên commit đích | Giải quyết file, stage và chạy `git rebase --continue` |
| Push bị từ chối sau rebase | Lịch sử remote còn commit cũ | Fetch, so sánh hai phía và chỉ dùng `--force-with-lease` khi đã được nhóm cho phép |
| Commit sau rebase có mã khác | Rebase đã tạo lại commit | Đây là hành vi bình thường; kiểm tra nội dung bằng log, show và range-diff |

Một số lệnh hữu ích để điều tra:

```bash
git status
git log --oneline --decorate --graph --all -20
git log --oneline --grep='fixup!'
git show --stat <commit>
git diff <base>..<branch>
```

## 11. Thực hành

Thực hiện trên repository thử nghiệm hoặc nhánh cá nhân chưa được chia sẻ:

1. Tạo ba commit có nội dung khác nhau trên nhánh `feature/autosquash`.
2. Chọn commit thứ nhất hoặc thứ hai để bổ sung một thay đổi nhỏ.
3. Stage đúng file hoặc phần diff, sau đó chạy `git commit --fixup=<commit-id>`.
4. Dùng `git log --oneline --graph --decorate` để quan sát commit `fixup!` nằm ở đầu lịch sử.
5. Xác định commit cha của commit đích và chạy `git rebase -i --autosquash <parent-id>`.
6. Kiểm tra todo list để xác nhận fixup được đặt ngay sau commit đích với hành động `fixup`.
7. Hoàn tất rebase, kiểm tra log và nội dung commit sau khi gộp.
8. Chạy test liên quan và so sánh chuỗi commit trước/sau bằng `git range-diff` nếu cần.

Thử thêm một fixup cho commit khác, rồi tạo một commit `squash!` bằng `git commit --squash=<commit-id>` để so sánh cách Git xử lý thông điệp. Nếu phiên bản Git hỗ trợ, thử `--fixup=amend:` hoặc `--fixup=reword:` trong một nhánh thử nghiệm để quan sát cách cập nhật thông điệp.

## 12. Tự kiểm tra kiến thức

1. `git commit --fixup=<commit>` tạo ra commit có đặc điểm gì?
2. Vì sao phải chọn commit nền nằm trước commit đích khi chạy `git rebase -i --autosquash`?
3. Autosquash thay đổi todo list như thế nào đối với commit `fixup!`?
4. Hành động `fixup` khác `squash` ở cách xử lý thông điệp commit ra sao?
5. Điều gì xảy ra với mã commit của các commit phía sau commit được sửa?
6. Khi rebase dừng do xung đột, cần làm gì để tiếp tục hoặc hủy thao tác?
7. Vì sao nên hoàn thành autosquash trước khi chia sẻ nhánh với đồng đội?
8. Khi nhánh đã được push và nhóm cho phép viết lại lịch sử, vì sao `--force-with-lease` phù hợp hơn `--force`?

## Kết luận

Fixup commit giúp gắn phần sửa mới với commit gốc ngay khi tạo. `git rebase -i --autosquash` tự sắp xếp các commit `fixup!` hoặc `squash!` vào đúng vị trí trong todo list để ta gộp chúng có kiểm soát. Hãy chọn đúng commit đích và base, kiểm tra todo list, xử lý xung đột cẩn thận rồi xác minh lịch sử sau rebase. Vì rebase thay mã định danh commit, nên thực hiện trước khi chia sẻ nhánh hoặc phối hợp với nhóm trước khi cập nhật lịch sử đã push.
