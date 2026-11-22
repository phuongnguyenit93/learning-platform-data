# Tác động của prune, reflog expire và thao tác chạy đồng thời

Git giữ lại object để bạn có thể xem lịch sử, chuyển nhánh và khôi phục một số thao tác đã thực hiện. Theo thời gian, repository có thể tích lũy object không còn được branch hoặc tag tham chiếu, reflog cũ và nhiều dữ liệu đóng gói. Các lệnh bảo trì như `git prune`, `git reflog expire` và `git gc` giúp thu hồi dữ liệu không còn cần thiết, nhưng cũng có thể làm mất cơ hội phục hồi commit hoặc object đã bị bỏ khỏi lịch sử.

Rủi ro tăng lên khi nhiều tiến trình Git cùng đọc và ghi repository. Git có cơ chế khóa để bảo vệ một số thao tác cập nhật, nhưng việc chạy dọn dẹp mạnh trong lúc một tiến trình khác đang tạo object hoặc cập nhật ref có thể gây lỗi hoặc làm mất dữ liệu chưa kịp được tham chiếu. Cần hiểu quan hệ giữa reachability, reflog, thời gian hết hạn và khóa trước khi chạy bảo trì thủ công.

## 1. Object nào được xem là còn cần thiết?

Git lưu commit, tree, blob và tag thành object trong object database. Một object có thể được tìm thấy từ các điểm bắt đầu (roots) như branch, tag, ref khác, index và reflog. Git lần theo các liên kết từ những điểm đó để xác định object nào còn reachable.

Ví dụ:

```text
refs/heads/main ------> commit C ----> tree ----> blob
refs/tags/v1.0 -------> tag object ---> commit A
reflog HEAD ----------> commit B
```

Trong ví dụ, commit A, B, C và các object mà chúng tham chiếu đều có thể được giữ lại dù một commit không còn là đầu branch hiện tại. Nếu commit B bị bỏ khỏi branch sau reset nhưng vẫn còn trong reflog, Git vẫn có thể giữ object để hỗ trợ khôi phục.

Một object **unreachable** là object không còn được tìm thấy từ các tham chiếu và nguồn gốc mà phép kiểm tra reachability đang xét. Unreachable không đồng nghĩa với việc object bị xóa ngay. Git có thời gian ân hạn để tránh xóa object vừa được tạo hoặc vừa bị bỏ tham chiếu.

Kiểm tra object unreachable:

```bash
git fsck --full --unreachable
```

Lệnh này giúp phát hiện object không còn reachable theo phạm vi kiểm tra. Để tìm cả object không được reflog giữ lại, có thể dùng:

```bash
git fsck --full --no-reflogs --unreachable
```

Không dùng kết quả `fsck` như danh sách chắc chắn có thể xóa. Một object đang unreachable có thể vẫn cần cho việc khôi phục, cho một tiến trình đang chạy hoặc cho một branch mà bạn chưa fetch.

## 2. git prune làm gì?

`git prune` loại bỏ các **loose object** không còn reachable và đã cũ hơn thời điểm hết hạn được chọn. Loose object là object được lưu riêng trong `.git/objects`, không nằm trong packfile.

Lệnh kiểm tra trước, không xóa:

```bash
git prune --dry-run --verbose
```

Khi chạy không có `--dry-run`, Git có thể xóa object thỏa điều kiện prune:

```bash
git prune --verbose
```

Mặc định, prune giữ lại object mới hơn khoảng thời gian ân hạn (thường là hai tuần). Có thể chỉ rõ mốc hết hạn:

```bash
git prune --expire=2.weeks.ago --dry-run --verbose
```

Để xem tác động của một lần prune mạnh hơn mà chưa xóa:

```bash
git prune --expire=now --dry-run --verbose
```

`--expire=now` làm cho mọi loose object unreachable đủ điều kiện theo mốc thời gian ngay lập tức. Không bỏ `--dry-run` nếu bạn chỉ đang khảo sát.

### Prune không đồng nghĩa với dọn mọi object trong repository

`git prune` tập trung vào loose object. Repository có thể chứa object trong packfile hoặc cruft pack; việc đóng gói, tách và loại bỏ dữ liệu trong các pack được điều phối bởi `git repack` và `git gc`, với hành vi phụ thuộc phiên bản Git và cấu hình. Vì vậy, đừng suy ra rằng chạy `git prune` sẽ thu hồi toàn bộ dung lượng của mọi object unreachable.

## 3. git reflog expire làm gì?

Reflog ghi lại những lần một ref local thay đổi. Ví dụ, `HEAD` reflog có thể ghi việc bạn checkout branch, commit, reset hoặc rebase. Reflog là nhật ký cục bộ của clone, không được push lên remote cùng branch.

Xem reflog:

```bash
git reflog --date=local
git reflog show --all
```

Nếu bạn reset nhầm, reflog có thể giúp tìm commit mà branch từng trỏ tới. Tuy nhiên, reflog có chính sách hết hạn. `git reflog expire` xóa các entry cũ theo mốc thời gian:

```bash
git reflog expire --dry-run --verbose --all
```

Đây là chế độ xem trước. Khi đã hiểu rõ các entry bị ảnh hưởng, có thể chạy lệnh expire thực tế theo chính sách đã chọn:

```bash
git reflog expire --all
```

Không nên chạy lệnh này theo thói quen trong lúc đang điều tra một sự cố hoặc trước khi sao lưu các commit có thể cần khôi phục.

### Hai mốc hết hạn thường dùng

Git có hai thiết lập mặc định phổ biến:

| Cấu hình | Giá trị mặc định thường gặp | Ý nghĩa |
|---|---:|---|
| `gc.reflogExpire` | 90 ngày | Hết hạn entry reflog cũ theo chính sách chung |
| `gc.reflogExpireUnreachable` | 30 ngày | Hết hạn sớm hơn các entry trỏ đến commit không còn reachable từ đầu ref hiện tại |

Các giá trị có thể được thay đổi ở cấp system, global hoặc repository; cấu hình theo pattern ref cũng có thể áp dụng riêng. Xem cấu hình hiệu lực và nguồn khai báo:

```bash
git config --show-origin --get-all gc.reflogExpire
git config --show-origin --get-all gc.reflogExpireUnreachable
```

Giá trị `--expire` và `--expire-unreachable` trong lệnh `git reflog expire` cho phép chỉ định chính sách cho lần chạy đó:

```bash
git reflog expire --expire=90.days.ago --expire-unreachable=30.days.ago --all --dry-run --verbose
```

`--expire` điều khiển entry cũ nói chung; `--expire-unreachable` điều khiển entry dẫn đến commit không còn reachable từ đầu ref hiện tại. Đây là thời gian lưu entry reflog, không phải tuổi của object trong object database.

## 4. Reflog expire và prune có quan hệ thế nào?

Hai thao tác có tác động khác nhau và thường nối tiếp nhau:

1. Một commit bị bỏ khỏi branch sau reset hoặc rebase.
2. Reflog vẫn ghi ref từng trỏ đến commit đó, nên commit có thể vẫn được giữ reachable thông qua reflog.
3. `git reflog expire` xóa entry reflog đã hết hạn.
4. Commit và object liên quan có thể trở thành unreachable nếu không còn ref hoặc index nào giữ chúng.
5. `git prune` hoặc `git gc` có thể xóa object unreachable sau khi thời gian ân hạn tương ứng đã qua.

Sơ đồ:

```text
Commit bị bỏ khỏi branch
          |
          v
   Reflog còn entry?
       /       \
     Có         Không
      |            |
      v            v
 Object còn    Kiểm tra các ref,
 được giữ      index và nguồn khác
      |
      v
 Reflog expire xóa entry
          |
          v
 Object có thể trở thành unreachable
          |
          v
 Đủ thời gian ân hạn?
          |
          v
    prune / gc có thể xóa
```

Đây là mô hình khái quát. Object chỉ bị xóa nếu không còn được giữ bởi bất kỳ ref hoặc nguồn reachability nào khác, và đáp ứng điều kiện tuổi cũng như loại object mà thao tác dọn dẹp xử lý.

## 5. git gc kết hợp các công việc bảo trì

`git gc` là lệnh bảo trì tổng hợp. Tùy phiên bản và cấu hình, nó có thể expire các entry reflog theo chính sách, dọn file tạm, đóng gói loose object, gộp pack, cập nhật dữ liệu phụ trợ và prune object hết hạn. Vì vậy, một lần GC có thể vừa làm mất các mốc reflog cũ vừa làm object không còn reachable trở thành ứng viên bị dọn.

Xem các tùy chọn:

```bash
git gc -h
```

Chạy garbage collection thông thường:

```bash
git gc
```

Git cũng có thể tự chạy `git gc --auto` sau một số thao tác nếu số lượng loose object hoặc pack đạt ngưỡng. Các cấu hình như `gc.auto`, `gc.autoPackLimit` và `gc.pruneExpire` ảnh hưởng thời điểm hoặc cách bảo trì.

Xem cấu hình:

```bash
git config --show-origin --get-regexp '^gc\.'
```

`git gc` mặc định dùng thời gian ân hạn khi prune (thường khoảng hai tuần). Có thể chỉ rõ mốc prune cho lần chạy:

```bash
git gc --prune=2.weeks.ago
```

Tránh chạy:

```bash
git gc --prune=now
```

trên repository đang có tiến trình khác ghi object hoặc cập nhật ref. Không có thời gian ân hạn làm tăng nguy cơ object mới được ghi nhưng chưa kịp được tham chiếu bị dọn mất.

## 6. Prune remote-tracking ref khác với prune object

Tên lệnh dễ gây nhầm lẫn:

- `git prune`: dọn loose object unreachable trong object database.
- `git remote prune origin`: xóa remote-tracking ref của `origin` mà remote không còn công bố.
- `git fetch --prune origin`: fetch và đồng thời dọn remote-tracking ref đã lỗi thời.

Ví dụ:

```bash
git remote prune --dry-run origin
git fetch --prune origin
```

Remote-tracking ref như `refs/remotes/origin/feature/old` có thể bị xóa khi branch tương ứng đã bị xóa trên server. Thao tác này không trực tiếp xóa commit object. Tuy nhiên, nếu không còn ref khác giữ commit và reflog liên quan hết hạn, object có thể trở thành ứng viên cho garbage collection về sau.

Để kiểm tra trước các ref có thể bị dọn, dùng `--dry-run`. Không nhầm `git fetch --prune` với `git prune --expire=now`; một lệnh dọn tên tham chiếu remote, lệnh kia dọn object.

## 7. Git xử lý thao tác đồng thời như thế nào?

Nhiều lệnh Git có thể đọc repository cùng lúc. Khi cần cập nhật một số file metadata quan trọng, Git dùng cơ chế lock file và thường ghi vào file tạm rồi đổi tên nguyên tử khi hoàn tất.

Ví dụ:

- `git add` có thể tạo `index.lock` trước khi cập nhật index.
- Cập nhật ref có thể tạo file `.lock` tương ứng trong `refs/` hoặc khu vực quản lý ref.
- Cập nhật cấu hình có thể dùng `config.lock`.
- Các thao tác đóng gói và garbage collection có cơ chế khóa riêng để hạn chế nhiều tiến trình GC chạy chồng lên nhau.

Nếu một tiến trình khác đang giữ lock, lệnh thứ hai có thể báo lỗi như `Unable to create ... .lock` hoặc `cannot lock ref`. Đây thường là dấu hiệu có thao tác khác đang cập nhật cùng dữ liệu, hoặc một tiến trình trước đó bị dừng và để lại lock file.

Không xóa `.lock` ngay khi thấy lỗi. Trước tiên, kiểm tra có tiến trình Git, IDE, GUI client, hook hoặc tác vụ CI nào đang chạy hay không. Nếu tiến trình vẫn hoạt động, chờ nó hoàn tất. Chỉ xem xét xóa lock file bị bỏ lại khi đã xác nhận không còn tiến trình sở hữu lock và hiểu file đó thuộc thao tác nào.

## 8. Rủi ro khi chạy prune hoặc GC cùng lúc với tiến trình ghi

Một tình huống nguy hiểm có thể xảy ra:

1. Tiến trình A ghi một object mới vào object database.
2. Tiến trình A chưa kịp cập nhật ref để commit hoặc branch tham chiếu đến object đó.
3. Tiến trình B chạy prune với mốc hết hạn `now`.
4. Object mới có thể bị nhìn thấy là unreachable và bị xóa trước khi tiến trình A hoàn tất cập nhật ref.

Đây là lý do thời gian ân hạn mặc định có ý nghĩa. Object vừa được tạo thường được bảo vệ trong một khoảng thời gian để các thao tác ghi có cơ hội hoàn tất. Khi dùng `--prune=now`, bạn bỏ lớp bảo vệ đó.

Các thao tác đồng thời khác cũng cần được xem xét:

| Tiến trình đang chạy | Tác động có thể gặp khi chạy bảo trì đồng thời |
|---|---|
| `git add` hoặc `git commit` | Cạnh tranh cập nhật index/ref; lệnh có thể chờ hoặc thất bại do lock |
| `git fetch` hoặc `git receive-pack` | Object được tải/ghi trước khi ref được cập nhật; prune quá mạnh có thể tạo rủi ro cho object mới |
| `git repack` hoặc `git gc` khác | Cạnh tranh đóng gói, lock hoặc thay đổi pack; để Git điều phối thay vì chạy nhiều tác vụ dọn dẹp thủ công |
| IDE đang tự fetch, commit hoặc refresh repository | Có thể tạo thao tác Git nền mà người dùng không nhìn thấy trong terminal |
| Hook hoặc CI runner dùng chung repository | Có thể đang ghi object/ref cùng lúc với bảo trì thủ công |

Git có lock và cơ chế bảo vệ để xử lý nhiều tình huống thường gặp, nhưng không nên dựa vào đó để chạy prune tức thời trong lúc repository đang được ghi. Hãy lên lịch bảo trì khi không có tiến trình ghi, giữ thời gian ân hạn và tránh thao tác trực tiếp trên thư mục `.git`.

## 9. Những dấu hiệu cho thấy repository đang có tiến trình khác

Trước khi chạy bảo trì thủ công, kiểm tra các tiến trình Git và ứng dụng đang dùng repository:

```bash
git status
git count-objects -vH
```

Trên Windows PowerShell, có thể xem tiến trình Git:

```powershell
Get-Process git -ErrorAction SilentlyContinue
```

Trên Linux/macOS:

```bash
ps -ef | grep '[g]it'
```

Các lệnh trên chỉ giúp quan sát, không chứng minh repository hoàn toàn không có tiến trình ghi. Một GUI client hoặc IDE có thể khởi chạy Git trong thời gian ngắn. Nếu có tác vụ CI, scheduled job hoặc IDE tự động fetch, hãy dừng hoặc chờ chúng theo quy trình trước khi thực hiện GC thủ công.

Nếu gặp lỗi lock:

```text
fatal: Unable to create '.git/index.lock': File exists.
```

Hãy kiểm tra tiến trình có thể đang dùng index. Không mở hai lệnh stage/commit đồng thời trong cùng worktree. Nếu lock còn lại sau khi tiến trình đã kết thúc bất thường, kiểm tra nội dung và thời điểm của lock file trước khi xử lý.

## 10. Quy trình bảo trì an toàn

Trước khi dọn object hoặc reflog:

1. **Xác nhận repository đúng.** Kiểm tra `git rev-parse --show-toplevel` và remote.
2. **Kiểm tra working tree và index.** Dùng `git status`; commit hoặc lưu thay đổi cần giữ.
3. **Kiểm tra ref.** Xem branch, tag và remote-tracking ref; fetch những branch cần giữ trước khi dọn.
4. **Kiểm tra reflog.** Dùng `git reflog --all` để tìm commit có thể cần phục hồi.
5. **Khảo sát object unreachable.** Dùng `git fsck --full --unreachable` và cân nhắc lưu commit quan trọng vào branch cứu hộ.
6. **Xem trước phạm vi expire/prune.** Dùng `git reflog expire --dry-run --verbose --all` và `git prune --dry-run --verbose`.
7. **Bảo đảm không có tiến trình ghi.** Kiểm tra terminal, IDE, GUI client, hook và CI runner.
8. **Chạy bảo trì với thời gian ân hạn phù hợp.** Ưu tiên `git gc` mặc định; chỉ thay đổi mốc expire/prune khi có lý do và backup.
9. **Kiểm tra sau bảo trì.** Chạy `git status`, `git fsck --full` và xem thống kê object.

Nếu cần giữ một commit đang chỉ còn trong reflog, tạo ref cứu hộ trước khi expire:

```bash
git branch rescue/before-cleanup <COMMIT_ID>
```

Khi commit đã được branch tham chiếu, nó sẽ tiếp tục reachable qua ref đó. Hãy bảo đảm branch cứu hộ được lưu ở đúng repository và có tên rõ ràng.

## 11. Ví dụ điều tra trước khi expire reflog

Giả sử bạn vừa reset branch và muốn chắc chắn không mất commit cũ:

```bash
git reflog --date=local -20
git fsck --full --no-reflogs --unreachable
```

Tìm commit trước lần reset, sau đó tạo branch cứu hộ:

```bash
git branch rescue/pre-reset <COMMIT_ID>
```

Kiểm tra branch mới:

```bash
git log --oneline --decorate -5 rescue/pre-reset
```

Chỉ sau khi xác nhận không còn commit cần phục hồi mới xem xét chính sách expire hoặc GC. Không cần chạy `git reflog expire` thủ công chỉ để giảm dung lượng; `git gc` và maintenance thông thường đã xử lý phần lớn công việc theo chính sách mặc định.

## 12. Bài tập thực hành

Thực hiện trong repository thử nghiệm có thể xóa bỏ:

1. Tạo vài commit, ghi lại OID commit mới nhất.
2. Dùng `git reset --hard HEAD~1` để bỏ commit khỏi đầu branch, rồi tìm commit cũ trong `git reflog`.
3. Chạy `git fsck --full --unreachable` và `git fsck --full --no-reflogs --unreachable` để quan sát khác biệt khi xét reflog.
4. Chạy `git reflog expire --dry-run --verbose --all` để xem entry có thể hết hạn.
5. Tạo branch cứu hộ trỏ đến commit cũ và xác nhận commit vẫn reachable.
6. Chạy `git prune --dry-run --verbose --expire=now` để khảo sát object có thể bị dọn; không bỏ `--dry-run` trong bài tập nếu chưa có bản sao lưu.
7. Chạy `git count-objects -vH` trước và sau một lần `git gc` thông thường để quan sát thống kê repository.
8. Mô tả một tình huống trong đó `git gc --prune=now` chạy cùng lúc với `git fetch` hoặc `git commit` có thể gây rủi ro.

Bạn hoàn thành bài tập khi phân biệt được xóa reflog entry với xóa object, phân biệt `git prune` với `git remote prune`, giải thích thời gian ân hạn và biết cách kiểm tra tiến trình/lock trước khi bảo trì.
