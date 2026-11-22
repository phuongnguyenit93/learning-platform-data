# Quyền thực thi, core.filemode và giới hạn metadata Git lưu

Khi một dự án được phát triển trên Windows, Linux và macOS, cùng một tệp có thể xuất hiện với quyền hệ thống khác nhau trên từng máy. Ví dụ, một script shell có quyền thực thi trên Linux nhưng khi checkout trên filesystem không biểu diễn quyền thực thi theo cách Git mong đợi, Git có thể không nhận ra thay đổi đó. Để cộng tác ổn định, cần hiểu Git lưu quyền tệp ở mức nào, `core.filemode` ảnh hưởng ra sao và những metadata nào nằm ngoài mô hình lưu trữ của Git.

Git có ghi nhận một phần thông tin về loại tệp và quyền thực thi. Với tệp thông thường, Git phân biệt trạng thái executable và non-executable. Git không lưu toàn bộ quyền POSIX, ACL của Windows, chủ sở hữu, thời gian sửa đổi hay mọi thuộc tính của filesystem. Vì vậy, repository lưu được trạng thái cần thiết để cộng tác, nhưng không phải là bản sao đầy đủ metadata của hệ điều hành.

## 1. Git lưu quyền tệp ở mức nào?

Trong tree của Git, một tệp thông thường thường có một trong hai mode:

| Mode | Ý nghĩa |
|---|---|
| `100644` | Tệp thông thường không có quyền thực thi |
| `100755` | Tệp thông thường có quyền thực thi |

Hai mode này là biểu diễn theo dạng octal trong cấu trúc tree/index của Git. Phần `100` biểu thị loại đối tượng là tệp thông thường; phần cuối phân biệt tệp có hay không có quyền thực thi. Git không ghi lại riêng từng bit đọc/ghi cho owner, group và others như filesystem POSIX.

Git còn biểu diễn một số loại mục khác trong tree:

| Mode | Loại mục | Ý nghĩa |
|---|---|---|
| `120000` | Symbolic link | Một liên kết tượng trưng; blob chứa đường dẫn đích của liên kết |
| `160000` | Gitlink | Tham chiếu đến commit của submodule |
| `040000` | Tree | Thư mục được biểu diễn bằng một tree con; thư mục rỗng không được lưu như một mục độc lập |

Đối với một file thông thường, điều Git cần biết cho việc cộng tác là file đó có được đánh dấu executable hay không. Ví dụ, script triển khai cần chạy trực tiếp có thể được lưu ở mode `100755`; file cấu hình hoặc mã nguồn thông thường thường là `100644`.

## 2. Git không lưu toàn bộ quyền và metadata của filesystem

Git tập trung vào nội dung, đường dẫn, cấu trúc cây, loại mục và một số thuộc tính cần cho việc tái tạo repository. Những thông tin sau thường không được lưu trong commit như metadata của tệp:

| Metadata của hệ điều hành | Git lưu trong commit? | Ghi chú |
|---|---|---|
| Nội dung tệp | Có | Được lưu bằng blob object |
| Đường dẫn và cấu trúc thư mục | Có | Được biểu diễn qua tree object |
| Bit executable của tệp thông thường | Có | Phân biệt mode `100644` và `100755` |
| Loại symbolic link | Có | Mode `120000`, blob chứa đường dẫn đích |
| Tham chiếu submodule | Có | Gitlink mode `160000` trỏ đến commit submodule |
| Quyền đọc/ghi chi tiết theo owner, group, others | Không | Git không lưu đầy đủ các bit quyền POSIX |
| Chủ sở hữu và nhóm sở hữu | Không | Không được khôi phục từ commit khi checkout |
| ACL trên NTFS hoặc POSIX ACL | Không | Cần quản lý bằng hệ thống triển khai hoặc cấu hình máy chủ |
| Thời gian tạo, truy cập, sửa đổi | Không | Checkout tạo thời gian filesystem mới trên máy hiện tại |
| Thuộc tính ẩn, system, archive, read-only của Windows | Không | Không phải metadata chuẩn được lưu trong commit Git |
| Extended attributes và metadata riêng của filesystem | Không | Cần công cụ hoặc quy trình riêng nếu dự án phụ thuộc vào chúng |
| Hard link giữa các đường dẫn | Không | Git lưu các đường dẫn và nội dung, không lưu quan hệ hard link |

Điều này có nghĩa là checkout cùng một commit trên hai máy không bảo đảm mọi chi tiết quyền và metadata của filesystem giống nhau. Git khôi phục trạng thái mà mô hình của nó quản lý; hệ điều hành và filesystem quyết định các chi tiết còn lại.

Nếu quy trình triển khai yêu cầu user/group cụ thể, ACL, quyền đọc/ghi riêng hoặc owner của tệp, hãy cấu hình chúng trong công cụ triển khai, image/container, package hoặc script cài đặt. Không thể dựa vào Git commit để tái tạo các quyền đó.

## 3. `core.filemode` điều khiển việc phát hiện thay đổi executable

`core.filemode` là cấu hình cho biết Git có nên tin vào thay đổi bit executable trong working tree khi so sánh với index hay không.

```bash
# Xem giá trị được cấu hình và nguồn cấu hình
git config --show-origin --get core.filemode

# Bật phát hiện thay đổi executable trong repository hiện tại
git config --local core.filemode true

# Tắt phát hiện thay đổi executable trong repository hiện tại
git config --local core.filemode false
```

Nếu lệnh `git config --get core.filemode` không trả về giá trị, điều đó có nghĩa chưa có giá trị được cấu hình rõ ràng ở các scope đang được đọc. Git sẽ dùng hành vi mặc định phù hợp với nền tảng và khả năng filesystem; khi clone, Git có thể đặt cấu hình này dựa trên việc filesystem có hỗ trợ bit executable đáng tin cậy hay không.

### Khi `core.filemode=true`

Git kiểm tra thay đổi executable trên working tree. Nếu một file tracked đổi từ non-executable sang executable, `git status` và `git diff` có thể báo thay đổi mode dù nội dung file không đổi.

Trên filesystem hỗ trợ quyền thực thi ổn định, đây là cấu hình phù hợp để Git tự nhận ra thay đổi từ `chmod`.

### Khi `core.filemode=false`

Git bỏ qua khác biệt executable quan sát được trên working tree khi so sánh với index. Cấu hình này hữu ích trên filesystem không bảo toàn hoặc không báo bit executable ổn định, chẳng hạn một số môi trường Windows hoặc filesystem chia sẻ.

`core.filemode=false` chỉ ảnh hưởng việc phát hiện thay đổi mode từ working tree. Nó không xóa mode đã lưu trong commit, cũng không ngăn bạn chủ động đặt mode trong index bằng `git update-index --chmod`.

### Chọn scope cấu hình phù hợp

| Lệnh | Phạm vi |
|---|---|
| `git config --local core.filemode false` | Chỉ repository hiện tại |
| `git config --global core.filemode false` | Các repository của người dùng hiện tại, trừ nơi có cấu hình ưu tiên cao hơn |
| `git config --system core.filemode false` | Toàn hệ thống Git, thường cần quyền quản trị |

Không nên đặt `core.filemode=false` toàn cục chỉ để che một thay đổi quyền bất thường trong một repository. Hãy xác định filesystem và nhu cầu của từng dự án trước khi chọn phạm vi. Nếu chỉ một repository gặp vấn đề, cấu hình `--local` thường dễ kiểm soát hơn.

## 4. Thay đổi quyền thực thi trên Linux và macOS

Trên filesystem POSIX hỗ trợ executable bit, có thể dùng `chmod`:

```bash
# Bật quyền thực thi cho script
chmod +x scripts/deploy.sh

# Kiểm tra Git có nhận ra thay đổi mode không
git status --short
git diff --summary
```

Nếu Git đang theo dõi thay đổi mode, kết quả có thể tương tự:

```text
 mode change 100644 => 100755 scripts/deploy.sh
```

Sau đó stage và kiểm tra thay đổi đã staged:

```bash
git add scripts/deploy.sh
git diff --cached --summary
git ls-files --stage -- scripts/deploy.sh
```

Nếu file cần trở lại non-executable:

```bash
chmod -x scripts/deploy.sh
git add scripts/deploy.sh
git diff --cached --summary
```

Khi nội dung không đổi, diff có thể chỉ hiển thị mode change. Hãy kiểm tra đúng đường dẫn trước khi commit để tránh vô tình thay đổi quyền của nhiều tệp.

## 5. Đặt mode trong index bằng `git update-index --chmod`

Trên môi trường mà `chmod` không thể thay đổi hoặc Git không phát hiện được executable bit, có thể đặt mode trực tiếp trong index:

```bash
# Đánh dấu file đã tracked là executable trong index
git update-index --chmod=+x scripts/deploy.sh

# Xem mode hiện tại trong index
git ls-files --stage -- scripts/deploy.sh

# Xem khác biệt đã staged so với commit hiện tại
git diff --cached --summary
```

`git update-index --chmod=+x` yêu cầu Git ghi nhận file ở mode executable trong index. Lệnh `--chmod=-x` đặt lại mode non-executable:

```bash
git update-index --chmod=-x scripts/deploy.sh
git diff --cached --summary
```

Với một file mới chưa nằm trong index, hãy thêm file trước rồi đặt mode:

```bash
git add scripts/deploy.sh
git update-index --chmod=+x scripts/deploy.sh
git diff --cached --summary
```

Lệnh này điều chỉnh mode trong index để commit kế tiếp lưu đúng trạng thái. Nó không phải công cụ thay đổi toàn bộ ACL hoặc quyền thực tế của filesystem. Trên máy Windows, file có thể vẫn không có khái niệm executable như Linux, nhưng commit vẫn có thể ghi nhận mode `100755` để các môi trường POSIX checkout đúng quyền thực thi.

## 6. Kiểm tra mode trong index và commit

Có ba trạng thái cần phân biệt:

- **Working tree:** quyền mà filesystem hiện tại đang thể hiện cho file.
- **Index:** mode sẽ được ghi vào commit kế tiếp.
- **Commit:** mode đã được lưu trong tree của commit.

Các lệnh sau giúp kiểm tra từng nơi:

```bash
# Xem quyền mà hệ điều hành hiển thị (trên Unix-like)
ls -l scripts/deploy.sh

# Xem mode đã stage trong index
git ls-files --stage -- scripts/deploy.sh

# Xem mode đã commit trong HEAD
git ls-tree HEAD -- scripts/deploy.sh

# Xem tóm tắt thay đổi mode chưa stage
git diff --summary

# Xem tóm tắt thay đổi mode đã stage
git diff --cached --summary
```

Ví dụ `git ls-files --stage` có thể trả về:

```text
100755 2f7c... 0    scripts/deploy.sh
```

Số `100755` là mode đang nằm trong index. Nếu `git ls-tree HEAD -- scripts/deploy.sh` vẫn hiển thị `100644`, điều đó cho biết mode executable chưa được ghi vào commit hiện tại, dù index có thể đã được cập nhật.

Sau khi commit:

```bash
git commit -m "Mark deployment script executable"
git ls-tree HEAD -- scripts/deploy.sh
git show --summary --format=short HEAD
```

Hãy xác nhận commit hiển thị mode mong muốn. Khi clone hoặc checkout trên Linux/macOS với filesystem hỗ trợ, Git có thể khôi phục executable bit từ mode đã lưu.

## 7. Làm việc với nhiều hệ điều hành

Một repository có thể được checkout trên Windows, Linux và macOS. Các hệ điều hành và filesystem không có cùng cách biểu diễn quyền:

| Môi trường | Khả năng thường gặp | Cách phối hợp |
|---|---|---|
| Linux | Filesystem POSIX thường hỗ trợ executable bit | Dùng `chmod` và để Git phát hiện khi `core.filemode=true` |
| macOS | Filesystem thường hỗ trợ executable bit | Dùng `chmod`; kiểm tra mode trước khi commit |
| Windows với NTFS | Mô hình quyền và thuộc tính khác POSIX; Git có thể không phát hiện executable bit như trên Unix | Kiểm tra `core.filemode`; dùng `git update-index --chmod` khi cần ghi mode rõ ràng |
| Filesystem chia sẻ hoặc mount đặc biệt | Có thể ánh xạ hoặc làm mất khác biệt quyền | Kiểm tra hành vi thực tế; cấu hình `core.filemode` phù hợp với repository |

Ví dụ nhóm có script `scripts/deploy.sh` cần executable trên Linux. Một thành viên Windows chỉnh nội dung script nhưng không thể tạo executable bit theo cách thông thường. Thành viên đó có thể stage nội dung, sau đó đặt mode trong index:

```bash
git add scripts/deploy.sh
git update-index --chmod=+x scripts/deploy.sh
git diff --cached --summary
git commit -m "Update deployment script and executable mode"
```

Khi thành viên Linux fetch và checkout commit này, Git có thể đặt executable bit theo mode `100755`, miễn filesystem và cấu hình local hỗ trợ. Người dùng Windows không nên kết luận mode trong repository sai chỉ vì File Explorer không hiển thị quyền thực thi như Linux.

Nếu một thành viên thường xuyên thấy mode change không mong muốn khi checkout hoặc sao chép tệp qua filesystem không bảo toàn quyền, hãy kiểm tra `core.filemode` trong repository đó. Tắt phát hiện mode có thể giảm nhiễu, nhưng khi cần thay đổi executable có chủ đích thì phải stage mode một cách tường minh.

## 8. Symbolic link và giới hạn nền tảng

Git có thể lưu một symbolic link như một mục mode `120000`. Blob của mục đó chứa đường dẫn đích của liên kết, không phải nội dung của file đích. Khi checkout, Git cần filesystem và quyền của người dùng hỗ trợ tạo symbolic link.

Trên môi trường không hỗ trợ hoặc không có quyền tạo symlink, cấu hình `core.symlinks=false` có thể khiến Git checkout symlink dưới dạng tệp thường chứa đường dẫn đích. Đây là vấn đề khác với `core.filemode`:

| Cấu hình | Điều khiển |
|---|---|
| `core.filemode` | Có tin vào thay đổi bit executable trên file thường trong working tree hay không |
| `core.symlinks` | Có tạo symbolic link thật khi checkout hay dùng biểu diễn dạng tệp thường |

Không dùng `core.filemode` để sửa lỗi symlink và cũng không dùng `core.symlinks` để xử lý quyền executable. Khi dự án phụ thuộc symlink, cần kiểm tra chính sách hệ điều hành, quyền người dùng và cấu hình clone của từng thành viên.

## 9. Những metadata cần quản lý ngoài Git

Vì Git không lưu đầy đủ quyền hệ điều hành, một số yêu cầu cần được xử lý trong quy trình khác:

- **Owner và group:** tạo user/group phù hợp trong máy chủ, container hoặc bước triển khai.
- **ACL và quyền đọc/ghi:** cấu hình bằng công cụ hệ điều hành, Ansible, script provisioning hoặc chính sách hạ tầng.
- **Thời gian tệp:** không dùng mtime hoặc ctime để xác định phiên bản; dùng commit, tag và object ID.
- **Thuộc tính Windows:** thiết lập hidden/read-only/system bằng script hoặc công cụ triển khai nếu ứng dụng cần.
- **Extended attributes:** sao lưu và phục hồi bằng công cụ hỗ trợ filesystem nếu dữ liệu cần các thuộc tính này.
- **Quyền executable:** lưu bit executable trong Git nếu đó là yêu cầu của repository; kiểm tra thêm quyền thực tế sau khi triển khai.

Ví dụ, một ứng dụng có thể yêu cầu file cấu hình chỉ cho owner đọc. Git có thể lưu nội dung cấu hình mẫu, nhưng quyền `0600` phải được thiết lập trong bước triển khai:

```bash
install -m 600 config/production.example /etc/sample-app/production.conf
chown sample-app:sample-app /etc/sample-app/production.conf
```

Đây là thao tác trên máy đích. Commit Git không lưu lại owner, group hoặc mode `0600` để tự khôi phục cho mọi máy.

## 10. Quy trình chẩn đoán khi mode thay đổi bất ngờ

Khi `git status` báo mode change hoặc script không chạy được sau checkout, hãy kiểm tra theo trình tự:

```bash
# 1. Xem cấu hình filemode và nguồn cấu hình
git config --show-origin --get core.filemode

# 2. Xem thay đổi Git đang nhận diện
git status --short
git diff --summary

# 3. So sánh mode trong index và commit
git ls-files --stage -- scripts/deploy.sh
git ls-tree HEAD -- scripts/deploy.sh

# 4. Nếu filesystem hỗ trợ, kiểm tra quyền thực tế
ls -l scripts/deploy.sh
```

Sau khi xác định nguyên nhân:

- Nếu file thực sự cần executable và filesystem hỗ trợ, dùng `chmod +x` rồi stage.
- Nếu Git không phát hiện mode vì `core.filemode=false` hoặc filesystem không biểu diễn được quyền, dùng `git update-index --chmod=+x`.
- Nếu file không nên executable, đặt lại mode bằng `chmod -x` hoặc `git update-index --chmod=-x`.
- Nếu quyền đọc/ghi, owner hoặc ACL sai, sửa trên filesystem hoặc trong quy trình triển khai; Git không có metadata tương ứng để khôi phục.

Sau đó kiểm tra lại `git diff --cached --summary`, `git ls-files --stage` và commit khi index đã phản ánh đúng ý định.

## 11. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| Git lưu mọi quyền POSIX của tệp | Git chủ yếu phân biệt file thường executable và non-executable; không lưu đầy đủ owner/group và các bit đọc/ghi. |
| `core.filemode=false` xóa executable bit khỏi commit | Không. Nó chỉ làm Git bỏ qua thay đổi executable được phát hiện từ working tree. |
| `chmod +x` luôn được Git nhận ra trên mọi hệ điều hành | Chỉ khi filesystem và cấu hình cho phép Git quan sát thay đổi đó. |
| `git update-index --chmod=+x` thay đổi ACL trên máy | Không. Nó đặt mode executable trong index để commit ghi nhận. |
| Checkout khôi phục owner và thời gian sửa đổi cũ | Không. Filesystem tạo owner và timestamp theo môi trường hiện tại. |
| `core.filemode` và `core.symlinks` là một cấu hình | Không. Một cấu hình điều khiển phát hiện executable bit; cấu hình kia điều khiển việc checkout symbolic link. |
| Mode `100755` có nghĩa Git lưu chính xác quyền `rwxr-xr-x` của mọi hệ điều hành | Đây là dấu hiệu executable của file thường trong mô hình Git, không phải bản lưu đầy đủ permission bits của filesystem. |

## 12. Tự kiểm tra

1. **Mode nào biểu thị file thông thường có quyền thực thi trong Git?**
   - `100755`.
2. **`core.filemode=false` ảnh hưởng điều gì?**
   - Git bỏ qua thay đổi executable bit được phát hiện từ working tree khi so sánh với index.
3. **Lệnh nào đặt mode executable trực tiếp trong index?**
   - `git update-index --chmod=+x <path>`.
4. **Git có lưu owner, group và ACL của tệp không?**
   - Không. Những metadata đó cần được quản lý ngoài Git.
5. **Mode `120000` đại diện cho loại mục nào?**
   - Symbolic link.
6. **Vì sao cần kiểm tra cả `git ls-files --stage` và `git ls-tree HEAD`?**
   - Lệnh đầu cho biết mode trong index; lệnh sau cho biết mode đã lưu trong commit hiện tại.

## Kết luận

Git lưu nội dung, cấu trúc đường dẫn, loại mục và trạng thái executable của file thường thông qua mode `100644` hoặc `100755`. `core.filemode` quyết định Git có phát hiện thay đổi executable từ working tree hay không; `git update-index --chmod` cho phép đặt mode rõ ràng trong index khi filesystem không hỗ trợ tốt. Owner, group, ACL, timestamp và nhiều thuộc tính hệ điều hành khác nằm ngoài metadata commit, vì vậy cần được cấu hình trong môi trường triển khai. Phân biệt đúng phần Git lưu và phần filesystem quản lý giúp repository hoạt động nhất quán giữa Windows, Linux và macOS.
