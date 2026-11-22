# Liệt kê tham chiếu từ xa bằng git ls-remote

Khi làm việc với repository được lưu trên Git server, đôi lúc bạn chỉ cần biết remote đang có những branch hoặc tag nào, nhánh mặc định của repository là gì, hay một branch cụ thể đã được đẩy lên chưa. Bạn có thể cần thông tin đó trước khi quyết định fetch, checkout hoặc tích hợp thay đổi.

Git cung cấp lệnh `git ls-remote` để hỏi repository từ xa về các tham chiếu (*refs*) mà nó đang quảng bá. Lệnh này trả về mã đối tượng và tên tham chiếu, nhờ đó bạn có thể kiểm tra branch, tag và `HEAD` ở remote. Đây là thao tác tra cứu: nó không tải lịch sử commit về, không cập nhật remote-tracking branch trên máy và không thay đổi working tree.

## 1. Tham chiếu từ xa là gì?

Trong Git, một tham chiếu (*reference*, thường viết tắt là *ref*) là một tên dễ đọc trỏ đến một đối tượng Git, thường là commit. Một số ref phổ biến:

| Dạng ref | Ví dụ | Ý nghĩa |
|---|---|---|
| `refs/heads/` | `refs/heads/main` | Branch được lưu trong repository đó |
| `refs/tags/` | `refs/tags/v1.2.0` | Tag đánh dấu một mốc trong lịch sử |
| `HEAD` | `HEAD` | Vị trí mặc định mà repository công bố; trên server thường trỏ tượng trưng đến branch mặc định |

Branch trên remote và remote-tracking branch trên máy bạn là hai khái niệm khác nhau. Ví dụ:

- `refs/heads/main` là branch `main` trong repository remote.
- `refs/remotes/origin/main` là remote-tracking branch được lưu cục bộ, phản ánh lần đồng bộ gần nhất từ remote `origin`.

Tên `origin` chỉ là tên remote thường được Git đặt mặc định khi clone. Repository có thể dùng tên khác hoặc có nhiều remote cùng lúc.

## 2. Cú pháp cơ bản của git ls-remote

Cú pháp tổng quát:

```bash
git ls-remote [<options>] <repository> [<patterns>...]
```

`<repository>` có thể là tên remote đã cấu hình, chẳng hạn `origin`, hoặc URL của repository. Nếu bỏ phần `<patterns>`, Git liệt kê các ref mà remote công bố, sau khi áp dụng những bộ lọc tùy chọn.

Để xem danh sách ref cơ bản:

```bash
git ls-remote origin
```

Ví dụ kết quả:

```text
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    HEAD
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    refs/heads/main
19ab2c3d4e5f60718293a4b5c6d7e8f901234567    refs/heads/feature/login
4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f70    refs/tags/v1.0.0
8a9b0c1d2e3f405162738495a6b7c8d9e0f12345    refs/tags/v2.0.0
6b7c8d9e0f1234567890a1b2c3d4e5f60718293a    refs/tags/v2.0.0^{}
```

Mỗi dòng thường có hai cột, phân cách bằng tab:

1. **Object ID:** mã định danh đối tượng Git mà ref trỏ đến. Độ dài mã phụ thuộc định dạng hash của repository.
2. **Ref name:** tên tham chiếu, ví dụ `HEAD`, `refs/heads/main` hoặc `refs/tags/v1.0.0`.

Trong ví dụ, `HEAD` và `refs/heads/main` có cùng object ID, cho thấy `HEAD` của remote đang trỏ đến branch `main`. Dòng `refs/tags/v2.0.0^{}` là dòng peeled của annotated tag, thể hiện đối tượng mà tag đó trỏ đến sau khi bóc lớp tag object.

Các mã trong ví dụ chỉ nhằm minh họa định dạng; khi chạy thực tế, object ID sẽ do repository trả về.

## 3. Chỉ liệt kê remote branch hoặc tag

### Chỉ xem branch

Dùng `--heads` để lọc các ref thuộc `refs/heads/`:

```bash
git ls-remote --heads origin
```

Ví dụ:

```text
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    refs/heads/main
19ab2c3d4e5f60718293a4b5c6d7e8f901234567    refs/heads/feature/login
2abc3d4e5f60718293a4b5c6d7e8f90123456789    refs/heads/release/1.x
```

Lệnh này hữu ích khi cần biết remote có những branch nào mà không bị lẫn với tag hoặc `HEAD`.

### Chỉ xem tag

Dùng `--tags` để lọc các ref thuộc `refs/tags/`:

```bash
git ls-remote --tags origin
```

Ví dụ:

```text
4d5e6f708192a3b4c5d6e7f8091a2b3c4d5e6f70    refs/tags/v1.0.0
8a9b0c1d2e3f405162738495a6b7c8d9e0f12345    refs/tags/v2.0.0
6b7c8d9e0f1234567890a1b2c3d4e5f60718293a    refs/tags/v2.0.0^{}
```

Git có hai kiểu tag phổ biến:

- **Lightweight tag:** ref trỏ trực tiếp đến đối tượng được đánh dấu, thường là commit. Output có một dòng cho tag.
- **Annotated tag:** ref trỏ đến một tag object chứa metadata như người tạo, ngày tạo và thông điệp. Git có thể in thêm dòng có hậu tố `^{}` để thể hiện đối tượng đích sau khi bóc tag object.

Vì vậy, với annotated tag, đừng mặc định rằng mã ở dòng `refs/tags/<tag>` chính là mã commit. Nếu muốn output bỏ các dòng peeled và pseudoref như `HEAD`, dùng `--refs`:

```bash
git ls-remote --tags --refs origin
```

### Kết hợp bộ lọc

Có thể kết hợp `--heads` và `--tags` để chỉ xem branch và tag:

```bash
git ls-remote --heads --tags origin
```

`--refs` có thể thêm vào khi chỉ muốn các ref thực trong hai nhóm đó mà không cần dòng peeled hoặc pseudoref:

```bash
git ls-remote --heads --tags --refs origin
```

## 4. Tìm một branch hoặc nhóm ref bằng pattern

Sau tên repository, bạn có thể truyền một hoặc nhiều pattern để lọc tên ref. Pattern được Git hiểu theo dạng glob. Để dễ đọc và tránh nhầm lẫn, nên dùng tên ref đầy đủ bắt đầu bằng `refs/heads/` hoặc `refs/tags/`.

Kiểm tra một branch cụ thể:

```bash
git ls-remote --heads origin "refs/heads/feature/login"
```

Liệt kê các branch trong nhóm `release`:

```bash
git ls-remote --heads origin "refs/heads/release/*"
```

Tìm các tag phiên bản bắt đầu bằng `v2.`:

```bash
git ls-remote --tags origin "refs/tags/v2.*"
```

Đặt pattern trong dấu nháy để shell không tự mở rộng ký tự `*` trước khi chuyển đối số cho Git. Pattern chỉ lọc output của lần truy vấn; nó không tạo branch, không tải ref về và không thay đổi cấu hình remote.

Nếu cần kiểm tra chính xác một branch có tồn tại hay không trong script, kết hợp `--exit-code`:

```bash
git ls-remote --exit-code --heads origin "refs/heads/feature/login"
```

Khi có ref khớp, Git in dòng tương ứng và trả mã thoát `0`. Nếu kết nối thành công nhưng không có ref nào khớp, Git trả mã thoát `2`. Lỗi xác thực, DNS hoặc kết nối là lỗi khác và cũng cần được xử lý; không nên coi mọi mã khác `0` đều có nghĩa branch không tồn tại.

Ví dụ dùng trong shell:

```bash
if git ls-remote --exit-code --heads origin "refs/heads/feature/login"; then
    echo "Branch exists on remote"
else
    result=$?
    if [ "$result" -eq 2 ]; then
        echo "Branch does not exist on remote"
    else
        echo "Could not query remote (exit code: $result)"
        exit "$result"
    fi
fi
```

## 5. Xác định HEAD và branch mặc định của remote

`HEAD` là tham chiếu đặc biệt cho biết vị trí mặc định mà repository công bố. Khi clone, Git thường dùng thông tin này để chọn branch ban đầu. Có thể xem object ID của `HEAD` bằng:

```bash
git ls-remote origin HEAD
```

Để yêu cầu server cung cấp thêm thông tin symbolic ref, dùng `--symref`:

```bash
git ls-remote --symref origin HEAD
```

Ví dụ:

```text
ref: refs/heads/main    HEAD
7c9a1f2b3d4e5f60718293a4b5c6d7e8f9012345    HEAD
```

Dòng bắt đầu bằng `ref:` cho biết `HEAD` đang trỏ tượng trưng đến `refs/heads/main`; dòng tiếp theo là object ID mà `HEAD` phân giải ra. Thông tin symbolic ref phụ thuộc vào việc remote server có quảng bá thông tin đó hay không. Nếu chỉ thấy dòng object ID, bạn vẫn biết commit đích nhưng chưa chắc suy ra được tên branch mặc định từ output đó.

## 6. Kiểm tra remote trước khi truy vấn

Để xem các remote đã cấu hình trong repository hiện tại:

```bash
git remote -v
```

Ví dụ:

```text
origin  https://example.com/team/sample-project.git (fetch)
origin  https://example.com/team/sample-project.git (push)
upstream https://example.com/org/sample-project.git (fetch)
upstream https://example.com/org/sample-project.git (push)
```

Bạn có thể truy vấn từng remote theo tên:

```bash
git ls-remote origin
git ls-remote upstream
```

Hoặc truy vấn trực tiếp URL:

```bash
git ls-remote https://example.com/team/sample-project.git
```

Nếu muốn xem URL sau khi Git áp dụng cấu hình `url.*.insteadOf`, dùng `--get-url`:

```bash
git ls-remote --get-url origin
```

Tùy chọn này chỉ in URL đã được mở rộng, không kết nối tới server để liệt kê refs. Khi repository riêng tư, Git cần thông tin xác thực phù hợp qua SSH agent, credential helper hoặc cơ chế đăng nhập đã cấu hình. Không nên nhúng access token hay mật khẩu trực tiếp vào URL hoặc câu lệnh được lưu trong lịch sử terminal.

## 7. Phân biệt git ls-remote với các lệnh xem ref khác

Các lệnh sau đều có thể hiển thị tên branch hoặc tag, nhưng chúng đọc dữ liệu ở những nơi và thời điểm khác nhau:

| Lệnh | Nguồn dữ liệu | Có cập nhật repository cục bộ không? |
|---|---|---|
| `git ls-remote origin` | Các ref remote đang quảng bá tại thời điểm truy vấn | Không |
| `git branch -r` | Remote-tracking branch đang lưu cục bộ | Không |
| `git show-ref` | Các ref hiện có trong repository cục bộ | Không |
| `git fetch origin` | Dữ liệu được tải từ remote theo refspec | Có thể cập nhật remote-tracking refs và tải object về |

Ví dụ, `git branch -r` có thể hiển thị `origin/feature/login` dù branch đó đã bị xóa trên server, nếu lần fetch gần nhất chưa dọn ref cục bộ. Ngược lại, `git ls-remote --heads origin` phản ánh những branch server đang quảng bá ở thời điểm gọi lệnh.

Nếu chỉ muốn kiểm tra remote có branch hay tag nào, dùng `git ls-remote`. Nếu muốn tải commit và cập nhật dữ liệu local để làm việc tiếp, dùng `git fetch`:

```bash
# Tra cứu branch remote, không cập nhật ref local.
git ls-remote --heads origin

# Tải dữ liệu và cập nhật remote-tracking refs theo cấu hình fetch.
git fetch origin

# Xem các remote-tracking branch sau khi fetch.
git branch -r
```

`git ls-remote` không thay thế `git fetch`: nó chỉ cung cấp danh sách ref và object ID mà remote công bố, không tải nội dung commit hoặc cây thư mục để bạn checkout hay xem file.

## 8. Một số lưu ý khi dùng trong công việc

- **Kiểm tra đúng remote:** dự án có thể có `origin` trỏ về fork cá nhân và `upstream` trỏ về repository gốc. Hãy dùng `git remote -v` trước khi kết luận branch có hay không.
- **Phân biệt ref remote với ref local:** kết quả `refs/heads/main` là branch trên server; `refs/remotes/origin/main` là bản tham chiếu theo dõi ở local.
- **Dùng `--heads` hoặc `--tags` khi cần danh sách rõ ràng:** việc lọc giảm nhiễu từ các ref khác.
- **Dùng `--exit-code` khi kiểm tra sự tồn tại:** phân biệt trường hợp không tìm thấy ref (mã thoát `2`) với lỗi kết nối hoặc xác thực.
- **Chú ý annotated tag:** output có thể chứa cả tag object và dòng peeled kết thúc bằng `^{}`.
- **Không coi kết quả là dữ liệu cố định:** remote có thể thay đổi ngay sau khi truy vấn do người khác push hoặc xóa branch/tag.
- **Không đưa thông tin bí mật vào lệnh:** dùng credential helper hoặc SSH agent để xác thực an toàn.

## 9. Quy trình tra cứu nhanh

Khi cần kiểm tra trạng thái refs của một remote trong công việc hằng ngày, bạn có thể đi theo trình tự:

1. Chạy `git remote -v` để xác nhận tên và URL remote.
2. Chạy `git ls-remote --heads origin` để xem các branch đang được công bố.
3. Chạy `git ls-remote --tags origin` để xem các tag.
4. Chạy `git ls-remote --symref origin HEAD` để kiểm tra thông tin branch mặc định mà server cung cấp.
5. Dùng pattern và `--exit-code` nếu cần xác minh một branch/tag cụ thể.
6. Chỉ chạy `git fetch origin` khi cần tải dữ liệu về và cập nhật remote-tracking refs trên máy.

Điều quan trọng là đọc đúng hai cột của output: object ID cho biết ref đang trỏ tới đối tượng nào, còn ref name cho biết đó là branch, tag hay `HEAD`. Khi hiểu định dạng này, bạn có thể nhanh chóng kiểm tra trạng thái remote, phát hiện branch đã được push hay chưa và chọn đúng bước đồng bộ tiếp theo.
