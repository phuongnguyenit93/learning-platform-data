# Git revert tạo commit đảo ngược trên lịch sử đã chia sẻ

Khi một commit đã được push lên nhánh dùng chung và cần hoàn tác, việc xóa hoặc viết lại commit cũ có thể làm lịch sử của đồng đội bị phân kỳ. `git revert` giải quyết tình huống này bằng cách tạo một commit mới chứa thay đổi đảo ngược commit được chọn. Commit cũ vẫn nằm trong lịch sử, còn thao tác hoàn tác được ghi nhận rõ ràng để mọi người có thể pull hoặc fetch như bình thường.

## 1. Revert là gì?

Git lưu lịch sử bằng các commit bất biến. Sau khi một commit đã được chia sẻ, bạn thường không nên di chuyển nhánh remote về một commit cũ chỉ để loại bỏ thay đổi. Thay vào đó, hãy tạo một commit mới để đưa nội dung dự án về trạng thái mong muốn.

Giả sử nhánh `main` có lịch sử:

```text
A---B---C---D  main, origin/main
```

Commit `D` đưa vào một thay đổi gây lỗi. Khi chạy:

```bash
git revert D
```

Git tạo commit mới `R` có nội dung đảo ngược thay đổi của `D`:

```text
A---B---C---D---R  main
```

`D` vẫn còn trong lịch sử. `R` là một commit bình thường, có parent là `D`, ghi lại việc hoàn tác. Nhánh tiến lên phía trước thay vì quay lại phía sau.

Revert phù hợp khi:

- Commit đã được push lên nhánh dùng chung.
- Nhóm muốn hoàn tác một thay đổi nhưng vẫn giữ dấu vết trong lịch sử.
- Cần tạo một thay đổi có thể review, kiểm thử và push theo quy trình thông thường.
- Muốn hoàn tác một commit cụ thể mà không viết lại các commit khác phía sau nó.

## 2. Revert khác reset như thế nào?

Hai lệnh đều có thể được dùng trong những tình huống người dùng gọi là “undo”, nhưng chúng tác động tới lịch sử theo cách khác nhau.

| Tiêu chí | `git revert` | `git reset` |
|---|---|---|
| Cách hoạt động | Tạo commit mới đảo ngược thay đổi đã chọn | Di chuyển nhánh hiện tại tới một commit khác và tùy tùy chọn cập nhật index/working tree |
| Commit cũ | Vẫn được giữ trong lịch sử | Có thể không còn được nhánh hiện tại tham chiếu |
| Phù hợp với | Hoàn tác thay đổi đã chia sẻ | Điều chỉnh lịch sử local chưa chia sẻ hoặc chuyển nhánh về trạng thái khác |
| Tác động tới nhánh remote | Có thể push bằng fast-forward thông thường | Nếu viết lại lịch sử đã push, thường cần force push và phối hợp với nhóm |

Ví dụ, nếu `D` đã được nhiều người lấy về, reset nhánh remote về `C` có thể khiến người khác vẫn giữ `D` trong lịch sử local. Khi họ đồng bộ, hai lịch sử không còn khớp. Revert tạo `R` trên `D`, nên mọi người tiếp tục chia sẻ cùng một dòng lịch sử.

`git revert` không phải lệnh xóa commit khỏi repository. Nó tạo một thay đổi mới nhằm đảo ngược tác động của commit cũ.

## 3. Cách Git tạo commit đảo ngược

Với một commit thông thường, Git so sánh nội dung commit đó với commit cha để xác định thay đổi mà commit đã đưa vào. Revert áp dụng thay đổi ngược lại lên trạng thái hiện tại.

Ví dụ commit `D` thêm dòng:

```java
boolean allowGuestCheckout = true;
```

Revert có thể tạo commit xóa dòng đó. Nếu commit `E` sau đó đã chỉnh sửa cùng khu vực, Git phải áp dụng thay đổi đảo ngược của `D` lên nội dung hiện tại sau `E`. Kết quả có thể không áp dụng tự động và cần bạn giải quyết xung đột.

Điểm quan trọng là revert không khôi phục nguyên xi cây thư mục tại commit cha của `D`. Nó áp dụng patch đảo ngược lên `HEAD` hiện tại. Các thay đổi khác được tạo sau `D` vẫn được giữ nếu không mâu thuẫn với patch đảo ngược.

## 4. Quy trình revert một commit đã chia sẻ

Trước tiên, kiểm tra repository và working tree:

```bash
git status -sb
git log --oneline --decorate -10
```

Đảm bảo bạn đang ở đúng nhánh và không có thay đổi chưa commit cần bảo toàn. Xác định chính xác commit cần hoàn tác bằng hash, thông điệp và nội dung thay đổi:

```bash
git show --stat --oneline <commit>
git show --format=fuller <commit>
```

Sau khi xác nhận commit đích, chạy:

```bash
git revert <commit>
```

Git áp dụng thay đổi đảo ngược và thường mở trình soạn thảo để bạn xác nhận thông điệp commit. Mặc định, thông điệp thường có dạng `Revert "..."` và nhắc tới commit gốc.

Kiểm tra commit mới và nội dung thay đổi:

```bash
git status
git show --stat --oneline HEAD
git show --format=fuller HEAD
```

Chạy test hoặc kiểm tra phù hợp để xác nhận lỗi đã được khắc phục và các chức năng liên quan vẫn hoạt động. Nếu kết quả đạt, push commit revert:

```bash
git push origin main
```

Thay `main` bằng nhánh thực tế. Vì commit revert được tạo trên tip hiện tại, push thông thường thường là fast-forward. Nếu có người khác push thêm commit trong lúc bạn xử lý, fetch và tích hợp thay đổi mới theo quy trình của nhóm trước khi push lại.

## 5. Khi revert gặp xung đột

Xung đột có thể xảy ra nếu các commit sau commit cần hoàn tác đã sửa cùng vùng nội dung. Git không thể tự xác định kết quả nào vừa đảo ngược thay đổi cũ vừa giữ các thay đổi mới.

Ví dụ:

- Commit `D` thêm cách tính phí cũ.
- Commit `E` sửa công thức và bổ sung một điều kiện mới dựa trên đoạn mã từ `D`.
- Bạn revert `D` ở trạng thái hiện tại đã bao gồm `E`.

Nếu xóa toàn bộ đoạn mã theo nội dung của `D`, bạn có thể vô tình xóa luôn điều kiện hợp lệ được `E` thêm vào. Hãy xem cả thay đổi ban đầu lẫn nội dung hiện tại trước khi sửa.

Khi Git báo xung đột:

```bash
git status
git diff
```

Sửa từng file để đạt kết quả đúng ý nghĩa, sau đó stage file đã giải quyết và tiếp tục:

```bash
git add path/to/resolved-file
git revert --continue
```

Nếu muốn hủy thao tác revert đang dừng:

```bash
git revert --abort
```

`--abort` đưa repository về trạng thái trước khi bắt đầu thao tác revert đang thực hiện. Trước khi dùng, hãy đọc trạng thái và bảo đảm các thay đổi chưa commit của bạn đã được lưu an toàn.

## 6. Revert nhiều commit

Bạn có thể cần đảo ngược nhiều commit, nhưng hãy xác định quan hệ phụ thuộc trước khi thực hiện. Nếu các commit nối tiếp nhau và commit sau dựa trên thay đổi của commit trước, thường cần hoàn tác từ commit mới hơn về commit cũ hơn để đảo ngược các phụ thuộc theo thứ tự ngược.

Ví dụ lịch sử:

```text
A---B---C---D---E  main
```

Nếu muốn đảo ngược cả `D` và `E`, có thể thực hiện từng lệnh theo thứ tự:

```bash
git revert E
git revert D
```

Sau mỗi lệnh, kiểm tra nội dung và chạy test cần thiết. Thứ tự thực tế cần dựa vào quan hệ giữa các thay đổi; với các commit độc lập, hãy xác nhận kết quả cuối cùng vẫn đúng.

Nếu muốn áp dụng nhiều thay đổi đảo ngược vào index và working tree rồi tạo một commit tổng hợp, có thể dùng `--no-commit`:

```bash
git revert --no-commit E
git revert --no-commit D
git diff
git diff --cached
```

Sau khi kiểm tra kỹ kết quả và test đạt, tạo commit thủ công:

```bash
git commit -m "Revert related changes"
```

`--no-commit` không tạo commit sau mỗi lần revert; các thay đổi được đưa vào index và working tree để bạn xem xét trước khi commit. Hãy kiểm tra trạng thái giữa các bước. Nếu một lần revert dừng vì xung đột, giải quyết và dùng `git revert --continue` theo thông báo của Git trước khi tiếp tục chuỗi.

Không nên revert một khoảng commit lớn chỉ vì muốn quay về một trạng thái cũ mà chưa hiểu những thay đổi trong khoảng đó. Nếu nhiều commit có phụ thuộc, hãy lập danh sách commit cần hoàn tác, kiểm tra diff từng commit và xác nhận kết quả cuối cùng với nhóm.

## 7. Revert một merge commit

Merge commit có từ hai parent trở lên. Vì vậy, Git cần biết bạn muốn xem parent nào là đường chính (*mainline*) khi tính thay đổi cần đảo ngược.

Kiểm tra parent của merge commit:

```bash
git show --no-patch --pretty=raw <merge-commit>
```

Kết quả có các dòng `parent` theo thứ tự. Với merge thông thường, parent thứ nhất thường là commit của nhánh đang checkout khi thực hiện merge; parent thứ hai thường là tip của nhánh được merge vào. Thứ tự này phải được xác nhận từ chính commit, không suy đoán chỉ bằng tên nhánh.

Để revert merge commit và chọn parent thứ nhất làm mainline:

```bash
git revert -m 1 <merge-commit>
```

`-m 1` có nghĩa là lấy parent số 1 làm đường chính khi xác định thay đổi cần đảo ngược. Nếu chọn parent số 2, kết quả đảo ngược sẽ được tính theo hướng khác. Chọn sai mainline có thể loại bỏ phần thay đổi không mong muốn khỏi cây mã.

### Hệ quả với lần merge sau

Revert một merge commit không xóa các commit của nhánh được merge khỏi đồ thị lịch sử. Nó tạo một commit mới đảo ngược phần thay đổi mà merge đã đưa vào cây nội dung.

Điều này có hệ quả quan trọng: nếu sau đó bạn merge lại chính nhánh đã được merge trước đó, Git biết các commit cũ của nhánh đó đã là tổ tiên trong lịch sử. Những thay đổi đã bị revert có thể không được đưa trở lại như một lần merge mới thông thường; lần merge sau chủ yếu mang vào các commit mới chưa có trong lịch sử chung.

Nếu nhóm muốn đưa các thay đổi của merge đã revert trở lại, có thể cần revert chính commit revert trước đó, hoặc tạo các commit mới thể hiện lại thay đổi mong muốn. Hãy xem lịch sử và thống nhất cách khôi phục trước khi thao tác.

## 8. Revert một commit revert

Đôi khi bạn hoàn tác một commit vì phát hiện lỗi, sau đó lỗi được sửa và muốn đưa chức năng trở lại. Nếu commit revert trước đó là `R`, có thể revert `R`:

```bash
git revert <revert-commit>
```

Thao tác này tạo một commit mới đảo ngược tác động của `R`, về mặt nội dung thường khôi phục thay đổi ban đầu. Lịch sử sẽ ghi nhận cả commit gốc, commit revert và commit revert của revert.

Tuy nhiên, nếu các commit khác đã thay đổi cùng khu vực sau `R`, việc revert `R` có thể xung đột hoặc cần điều chỉnh. Đừng giả định thao tác này luôn khôi phục chính xác từng byte như trước; hãy kiểm tra diff và test sau khi thực hiện.

## 9. Dùng `--no-edit` và `--no-commit`

Hai tùy chọn này giải quyết hai nhu cầu khác nhau:

| Tùy chọn | Tác dụng |
|---|---|
| `--no-edit` | Dùng thông điệp revert mặc định mà không mở trình soạn thảo |
| `--no-commit` (`-n`) | Áp dụng thay đổi đảo ngược vào index/working tree nhưng không tạo commit ngay |

Ví dụ:

```bash
git revert --no-edit <commit>
```

Lệnh tạo commit revert với thông điệp mặc định mà không mở editor. Còn:

```bash
git revert --no-commit <commit>
```

Lệnh chỉ chuẩn bị thay đổi đảo ngược để bạn xem xét. Sau đó bạn có thể tiếp tục chỉnh sửa, chạy test và tự tạo commit khi đã xác nhận kết quả.

## 10. Giới hạn của revert với dữ liệu và tác động bên ngoài

Git revert chỉ thay đổi nội dung được quản lý trong repository. Nó không tự đảo ngược những tác động đã xảy ra bên ngoài Git, ví dụ:

- Migration đã chạy trên cơ sở dữ liệu production.
- Email, thông báo hoặc giao dịch đã được gửi tới khách hàng.
- Tài nguyên cloud đã được tạo hoặc xóa.
- File hoặc dữ liệu đã được ghi vào volume, object storage hay hệ thống khác.

Ví dụ, revert commit chứa migration SQL không tự đưa cơ sở dữ liệu đang chạy về schema cũ. Bạn cần một migration mới có chủ đích đảo ngược schema hoặc một quy trình khôi phục dữ liệu phù hợp. Với giao dịch đã gửi, có thể cần thao tác bù trừ theo nghiệp vụ thay vì xóa dấu vết giao dịch.

Trước khi revert commit liên quan đến dữ liệu hoặc triển khai, hãy xác định thay đổi đó đã được thực thi ở môi trường nào và lập kế hoạch bù trừ cho từng hệ thống chịu ảnh hưởng.

## 11. Các lỗi thường gặp khi dùng revert

- **Chọn nhầm commit:** luôn kiểm tra hash, thông điệp và diff trước khi revert.
- **Nghĩ rằng revert xóa commit cũ:** commit gốc vẫn nằm trong lịch sử; commit mới chỉ đảo ngược tác động nội dung.
- **Revert mà không kiểm tra thay đổi về sau:** patch đảo ngược có thể ảnh hưởng logic mới được thêm sau commit gốc.
- **Chọn sai mainline khi revert merge:** kiểm tra thứ tự parent bằng `git show --pretty=raw` trước khi dùng `-m`.
- **Dùng `--skip` hoặc bỏ qua thay đổi mà chưa hiểu:** nếu revert đang dừng, xác định chính xác commit và nội dung bị bỏ trước khi tiếp tục.
- **Cho rằng Git rollback được hệ thống bên ngoài:** lập migration hoặc thao tác bù trừ riêng cho dữ liệu và dịch vụ đã thay đổi.
- **Dùng reset/force push trên nhánh chung để thay thế revert:** cách đó viết lại lịch sử và có thể làm mất công việc mà người khác đã lấy về.

## 12. Quy trình thực hành: hoàn tác một commit đã push

Giả sử bạn đã push commit `abc1234` lên `main`, sau đó phát hiện thay đổi gây lỗi. Nhóm thống nhất hoàn tác bằng một commit mới.

1. Kiểm tra nhánh, working tree và lịch sử:

   ```bash
   git status -sb
   git log --oneline --decorate -10
   git show --stat --oneline abc1234
   ```

2. Cập nhật thông tin từ remote và xác nhận bạn đang làm trên nền mới nhất:

   ```bash
   git fetch origin
   git log --oneline --graph --decorate HEAD origin/main
   ```

   Nếu `main` local đã cũ, hãy tích hợp commit remote theo quy trình của nhóm trước khi revert.

3. Tạo commit đảo ngược:

   ```bash
   git revert abc1234
   ```

4. Xem commit mới, chạy test và kiểm tra các chức năng liên quan:

   ```bash
   git show --stat --oneline HEAD
   git status
   ```

5. Khi kết quả đạt và nhánh vẫn được phép cập nhật, push commit revert:

   ```bash
   git push origin main
   ```

Nếu remote nhận thêm commit trong lúc bạn xử lý, push có thể bị từ chối non-fast-forward. Hãy fetch, xem lịch sử mới và tích hợp theo quy trình; không force push chỉ để vượt qua từ chối.

## 13. Ghi nhớ

`git revert` là cách hoàn tác phù hợp với lịch sử đã chia sẻ vì nó tạo commit đảo ngược mới và giữ nguyên commit cũ. Hãy xác định đúng commit, kiểm tra các thay đổi phát sinh sau đó, chọn đúng mainline khi revert merge commit và chạy test trước khi push. Với dữ liệu hoặc tác động ngoài repository, cần có thao tác bù trừ riêng; Git không thể tự hoàn tác những việc đã xảy ra trong hệ thống bên ngoài.
