# Bổ sung lịch sử bằng --deepen và --unshallow

Một repository được clone với giới hạn độ sâu (shallow clone) chỉ chứa một phần lịch sử commit của nhánh được lấy về. Cách clone này giúp giảm thời gian tải và dung lượng khi bạn chỉ cần mã nguồn gần nhất, nhưng có thể gây thiếu thông tin khi xem lịch sử, tìm merge base, chạy bisect hoặc thực hiện một số thao tác tích hợp.

Khi cần thêm lịch sử, Git cung cấp hai tùy chọn fetch quan trọng: `--deepen=<n>` tải thêm một số commit tính từ ranh giới shallow hiện tại; `--unshallow` yêu cầu lấy toàn bộ lịch sử còn có từ remote. Hai tùy chọn này bổ sung dữ liệu lịch sử vào repository hiện tại mà không cần clone lại từ đầu.

## 1. Shallow clone là gì?

Trong một clone đầy đủ, Git có thể truy cập lịch sử commit của các nhánh và tag đã được fetch, bắt đầu từ những commit hiện có cho đến các tổ tiên của chúng. Trong shallow clone, Git chỉ tải một phần lịch sử và đánh dấu những commit ở ranh giới mà lịch sử bị cắt.

Ví dụ, clone repository với độ sâu một commit:

```bash
git clone --depth=1 https://git.example.com/platform/payment-service.git
```

Lệnh này lấy commit mới nhất của nhánh được clone cùng dữ liệu cần thiết để checkout. Lịch sử phía trước commit đó chưa được tải đầy đủ. Khi dùng `--depth`, Git mặc định chỉ clone một nhánh (`--single-branch`), trừ khi bạn chỉ định `--no-single-branch`.

Kiểm tra repository có phải shallow clone hay không:

```bash
git rev-parse --is-shallow-repository
```

Kết quả:

```text
true
```

cho biết repository còn giới hạn shallow. Nếu kết quả là `false`, repository hiện không còn ở trạng thái shallow.

Bạn cũng có thể xem lịch sử hiện có:

```bash
git log --oneline --graph --decorate --all
```

Trong shallow clone, lịch sử có thể dừng ở ranh giới shallow dù commit thực tế trên remote còn có tổ tiên cũ hơn. Git ghi nhận các ranh giới này trong metadata repository, thường qua file `shallow` bên trong thư mục Git. Không chỉnh sửa file metadata này bằng tay; hãy dùng lệnh fetch để thay đổi độ sâu.

## 2. Vì sao cần bổ sung lịch sử?

Shallow clone hữu ích trong CI, build container hoặc môi trường chỉ cần snapshot mới nhất. Tuy nhiên, một số tác vụ cần biết thêm các commit tổ tiên:

- Xem thay đổi của một file trong nhiều tuần hoặc nhiều tháng trước.
- Tìm merge base giữa hai nhánh trước khi merge hoặc rebase.
- Chạy `git bisect` để tìm commit gây ra lỗi trong một khoảng lịch sử dài.
- Kiểm tra tag phát hành cũ hoặc commit mà một tag trỏ tới.
- Phân tích lịch sử merge, tác giả và thời điểm một thay đổi xuất hiện.
- Thực hiện công cụ CI yêu cầu đủ lịch sử để tạo changelog, tính phiên bản hoặc so sánh với tag trước đó.

Khi gặp lỗi do thiếu lịch sử, không nhất thiết phải tải lại toàn bộ repository ngay. Bạn có thể tăng độ sâu từng bước để lấy đủ commit cần thiết.

## 3. Bổ sung một số commit bằng --deepen

Cú pháp:

```bash
git fetch --deepen=<n> <remote> [<refspec>...]
```

`<n>` là số commit muốn đi sâu thêm tính từ ranh giới shallow hiện tại. Ví dụ repository ban đầu được clone với `--depth=1`, bạn muốn lấy thêm 50 commit:

```bash
git fetch --deepen=50 origin
```

Git fetch thêm lịch sử từ remote `origin` theo refspec fetch đã cấu hình. Nếu clone chỉ theo dõi một nhánh, lệnh mặc định thường chỉ deepen nhánh đó.

Kiểm tra lịch sử sau khi fetch:

```bash
git rev-parse --is-shallow-repository
git log --oneline --decorate -60 origin/main
```

Repository có thể vẫn trả về `true` vì bạn mới tải thêm 50 commit mà chưa lấy đến tổ tiên đầy đủ. Đây là hành vi bình thường của `--deepen`.

### Deepen một nhánh cụ thể

Nếu muốn chỉ rõ nhánh `main` và cập nhật remote-tracking branch tương ứng, có thể dùng refspec đầy đủ:

```bash
git fetch --deepen=50 origin refs/heads/main:refs/remotes/origin/main
```

Phần trước dấu hai chấm là ref trên remote; phần sau là ref local sẽ được cập nhật. Cách viết này hữu ích khi bạn cần kiểm soát chính xác nhánh nào được fetch trong repository có nhiều remote hoặc refspec tùy chỉnh.

### Deepen thêm nhiều lần

Bạn có thể tăng độ sâu theo từng bước:

```bash
git fetch --deepen=50 origin
git fetch --deepen=100 origin
```

Hai lệnh này lần lượt lấy thêm 50 rồi thêm 100 commit từ ranh giới shallow mới. Nếu ban đầu depth là 1, độ sâu lịch sử theo nhánh có thể tiến đến khoảng 151 commit, tùy cấu trúc lịch sử và số commit có thể tải. `--deepen=100` không đặt tổng độ sâu thành 100; nó thêm 100 commit tính từ ranh giới hiện tại.

## 4. Phân biệt --deepen với --depth

Hai tùy chọn có ý nghĩa khác nhau:

| Tùy chọn | Ý nghĩa | Ví dụ |
|---|---|---|
| `--deepen=<n>` | Thêm `<n>` commit tính từ ranh giới shallow hiện tại | `git fetch --deepen=50 origin` |
| `--depth=<n>` | Đặt giới hạn độ sâu lịch sử tính từ đầu nhánh được fetch | `git fetch --depth=200 origin` |
| `--unshallow` | Lấy toàn bộ lịch sử còn có từ nguồn fetch nếu nguồn có đủ lịch sử | `git fetch --unshallow origin` |

Giả sử repository hiện có độ sâu 20:

```bash
git fetch --depth=100 origin
```

Lệnh trên yêu cầu lịch sử có độ sâu tổng cộng 100 commit từ đầu nhánh được fetch. Trong khi đó:

```bash
git fetch --deepen=100 origin
```

yêu cầu thêm 100 commit tính từ ranh giới shallow hiện tại. Vì vậy, kết quả có thể sâu hơn 100 commit tính từ đầu nhánh.

Nếu bạn chỉ muốn lấy thêm một lượng lịch sử nhỏ để kiểm tra, `--deepen` thể hiện ý định rõ ràng. Nếu muốn đặt giới hạn tổng thể cụ thể, dùng `--depth`.

## 5. Lấy toàn bộ lịch sử bằng --unshallow

Khi không còn muốn giới hạn lịch sử, dùng:

```bash
git fetch --unshallow origin
```

Git yêu cầu remote cung cấp toàn bộ lịch sử còn thiếu cho các ref được fetch. Nếu remote có đầy đủ lịch sử, repository local sẽ chuyển từ shallow sang đầy đủ.

Kiểm tra kết quả:

```bash
git rev-parse --is-shallow-repository
git log --oneline --graph --decorate --all
```

Khi không còn shallow boundary, lệnh kiểm tra trả về:

```text
false
```

### Nếu remote nguồn cũng là shallow repository

Nếu repository nguồn bản thân cũng bị giới hạn shallow, `--unshallow` chỉ có thể tải phần lịch sử mà nguồn cung cấp. Git không thể tạo ra các commit tổ tiên không tồn tại hoặc không được phép truy cập ở phía remote. Trong tình huống này, kết quả có thể vẫn còn shallow boundary.

Việc fetch cũng phụ thuộc máy chủ có cho phép yêu cầu shallow/deepen hay không. Một số máy chủ hoặc dịch vụ Git có thể áp dụng giới hạn về lịch sử, quyền truy cập hoặc giao thức.

## 6. Deepen nhánh trong shallow clone chỉ theo một nhánh

Clone có `--depth` thường bật chế độ single-branch nếu không chỉ định khác. Điều đó có nghĩa refspec fetch mặc định có thể chỉ theo dõi nhánh đã clone.

Kiểm tra refspec đang cấu hình:

```bash
git config --get-all remote.origin.fetch
```

Nếu bạn cần lấy lịch sử cho nhánh `release/2.4`, hãy fetch nhánh đó với refspec rõ ràng:

```bash
git fetch --deepen=50 origin refs/heads/release/2.4:refs/remotes/origin/release/2.4
```

Nếu muốn tiếp tục theo dõi nhánh đó trong các lần fetch sau, có thể thêm nhánh vào cấu hình remote:

```bash
git remote set-branches --add origin release/2.4
```

Sau đó:

```bash
git fetch --deepen=50 origin
git branch -r
```

Lệnh `remote set-branches --add` mở rộng danh sách nhánh mà remote `origin` sẽ fetch theo cấu hình. Nó không tự tạo branch local. Nếu cần làm việc trên nhánh đó, hãy tạo branch local theo quy trình phù hợp.

## 7. Tag và shallow history

Shallow clone có thể không tải toàn bộ tag của repository. Git thường auto-follow các tag liên quan đến đối tượng vừa được fetch, nhưng điều đó không đảm bảo mọi tag cũ đều có trong local.

Xem tag đang có:

```bash
git tag --list
```

Lấy toàn bộ tag từ remote:

```bash
git fetch --tags origin
```

Hoặc lấy một tag cụ thể:

```bash
git fetch origin tag v1.8.0
```

Nếu tag cũ trỏ đến commit nằm ngoài phần lịch sử shallow hiện có, việc lấy tag có thể kéo theo đối tượng cần thiết nhưng không nhất thiết làm toàn bộ nhánh trở thành full history. Khi cần phân tích lịch sử phía sau tag, hãy kết hợp fetch tag với `--deepen` hoặc `--unshallow` theo nhu cầu.

Kiểm tra tag và commit đích:

```bash
git show --no-patch --decorate v1.8.0
git log --oneline v1.8.0
```

## 8. Fetch lịch sử không tự cập nhật branch local

`git fetch --deepen` và `git fetch --unshallow` cập nhật dữ liệu và các ref được fetch, chẳng hạn `origin/main`. Chúng không tự động di chuyển branch local `main` hoặc thay đổi working tree hiện tại.

Kiểm tra hai ref:

```bash
git log --oneline main -5
git log --oneline origin/main -10
```

Nếu `origin/main` đã được cập nhật nhưng branch local `main` chưa thay đổi, bạn có thể tích hợp theo quy trình của nhóm:

```bash
git switch main
git merge --ff-only origin/main
```

Chỉ thực hiện bước tích hợp khi bạn muốn cập nhật branch local. Nếu đang làm trên một branch khác, có thể chỉ cần thêm lịch sử vào remote-tracking ref để phục vụ phân tích hoặc kiểm tra.

## 9. Tác động và lưu ý khi bổ sung lịch sử

- **Dung lượng tăng:** mỗi lần deepen tải thêm commit và object liên quan, nên repository có thể lớn lên đáng kể.
- **Thời gian mạng:** lịch sử dài, nhiều file lớn hoặc nhiều nhánh có thể làm fetch lâu hơn.
- **Refspec quyết định phạm vi:** chỉ các nhánh/ref được fetch mới được bổ sung lịch sử theo lệnh đó.
- **Không sửa commit:** deepen/unshallow chỉ bổ sung object và mở rộng lịch sử có thể truy cập; chúng không viết lại mã commit hiện có.
- **Không đồng nghĩa với sparse checkout:** shallow clone giới hạn số lượng lịch sử commit; sparse checkout giới hạn các đường dẫn được đưa vào working tree. Hai tính năng có thể dùng cùng nhau nhưng giải quyết hai vấn đề khác nhau.
- **Không sửa file metadata thủ công:** để thay đổi shallow boundary, hãy dùng `git fetch --deepen`, `--depth` hoặc `--unshallow`.

Nếu repository được dùng trong CI, hãy chọn độ sâu theo nhu cầu pipeline. Ví dụ, build đơn giản có thể dùng depth nhỏ; pipeline tạo changelog hoặc chạy `git describe` cần tag và lịch sử phù hợp. Với pipeline cần phân tích toàn bộ lịch sử, dùng `--unshallow` hoặc clone đầy đủ.

## 10. Quy trình xử lý khi thiếu lịch sử

Giả sử CI báo không tìm được tag phát hành cũ hoặc `git log` chỉ hiển thị một commit. Hãy kiểm tra:

```bash
git rev-parse --is-shallow-repository
git log --oneline --decorate --all -20
git config --get-all remote.origin.fetch
git tag --list
```

Nếu repository shallow và chỉ cần thêm lịch sử vừa đủ:

```bash
git fetch --deepen=100 origin
```

Nếu cần lịch sử đầy đủ:

```bash
git fetch --unshallow origin
```

Nếu cần một nhánh chưa được theo dõi:

```bash
git fetch origin refs/heads/release/2.4:refs/remotes/origin/release/2.4
```

Sau đó kiểm tra lại:

```bash
git rev-parse --is-shallow-repository
git log --oneline --graph --decorate --all -50
git branch -r
git tag --list
```

Chọn `--deepen` khi muốn tải thêm có kiểm soát; chọn `--unshallow` khi công cụ cần toàn bộ lịch sử và remote có thể cung cấp.

## 11. Bài tập thực hành

Thực hành trong một repository thử nghiệm hoặc clone riêng, tránh thay đổi cấu hình của repository đang làm việc:

1. Clone một repository với `--depth=1` và kiểm tra bằng `git rev-parse --is-shallow-repository`.
2. Xem lịch sử bằng `git log --oneline --all` và ghi nhận số commit có thể truy cập.
3. Chạy `git fetch --deepen=20 origin`, sau đó kiểm tra lại trạng thái shallow và lịch sử.
4. So sánh `git fetch --depth=50 origin` với `git fetch --deepen=50 origin` trong hai clone thử nghiệm độc lập.
5. Chạy `git fetch --unshallow origin` và xác nhận kết quả bằng `git rev-parse --is-shallow-repository`.
6. Tạo shallow clone với `--single-branch`, kiểm tra `remote.origin.fetch`, rồi fetch một nhánh khác bằng refspec tường minh.
7. Giải thích vì sao bổ sung lịch sử không tự cập nhật branch local và vì sao shallow clone khác sparse checkout.

Bạn hoàn thành bài tập khi chọn đúng giữa `--deepen`, `--depth` và `--unshallow`, biết cách kiểm tra shallow state và xác định được ref nào sẽ nhận lịch sử bổ sung.
