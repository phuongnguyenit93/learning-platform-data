# Phân biệt địa chỉ fetch với địa chỉ push

Khi làm việc với repository từ xa, Git cần biết nơi lấy dữ liệu và nơi gửi dữ liệu. Hai địa chỉ này thường giống nhau, nhưng không bắt buộc phải giống nhau. Một remote có thể dùng một địa chỉ để fetch và một địa chỉ khác để push. Hiểu rõ sự khác biệt giúp bạn cấu hình đúng luồng cộng tác, nhất là khi dự án dùng máy chủ đọc, máy chủ ghi hoặc quy trình fork.

Trong Git, tên như `origin` hay `upstream` là tên gọi của một cấu hình remote ở local. Bên trong cấu hình đó, `url` xác định địa chỉ lấy dữ liệu; `pushurl` có thể chỉ định địa chỉ riêng để gửi dữ liệu. Nếu không cấu hình `pushurl`, Git dùng `url` làm địa chỉ push mặc định.

## 1. Remote là tên cấu hình, URL là địa chỉ kết nối

Khi clone một repository, Git thường tạo remote tên `origin`. Ví dụ:

```bash
git clone https://git.example.com/team/app.git
cd app
git remote -v
```

`origin` không phải địa chỉ máy chủ. Đó là tên ngắn để Git tra cứu các thiết lập kết nối đã lưu trong repository local. Bạn có thể đặt tên khác khi thêm remote:

```bash
git remote add upstream https://git.example.com/team/app.git
```

Một remote có thể có các thiết lập quan trọng sau:

| Thiết lập | Ý nghĩa |
|---|---|
| `remote.<name>.url` | Địa chỉ remote được dùng khi fetch; cũng là địa chỉ push mặc định nếu không có `pushurl`. |
| `remote.<name>.pushurl` | Địa chỉ riêng được dùng khi push. Có thể cấu hình nhiều giá trị; Git sẽ push đến tất cả địa chỉ đó. |
| `remote.<name>.fetch` | RefSpec quy định ref nào trên remote được lấy và ánh xạ vào ref nào trong local, thường là remote-tracking branch. |

Ví dụ, với remote tên `origin`, các khóa cấu hình tương ứng là `remote.origin.url`, `remote.origin.pushurl` và `remote.origin.fetch`.

## 2. Fetch và push thực hiện hai chiều công việc khác nhau

**Fetch** lấy commit, tree, blob và thông tin ref từ repository từ xa về repository local. Git kết nối đến địa chỉ `url` của remote. Sau khi nhận dữ liệu, Git cập nhật các ref local theo refspec đã cấu hình, thường là các remote-tracking branch như `origin/main`.

Fetch không tự hợp nhất thay đổi vào nhánh local hiện tại và thông thường không thay đổi working tree. Ví dụ:

```bash
# Lấy thông tin và đối tượng mới từ remote origin
git fetch origin

# Xem các nhánh remote-tracking sau khi fetch
git branch -r

# So sánh nhánh local main với trạng thái đã fetch của origin/main
git log --oneline main..origin/main
```

**Push** gửi các đối tượng cần thiết từ repository local lên repository từ xa và yêu cầu cập nhật ref ở phía remote. Git dùng `pushurl` nếu remote đã cấu hình khóa này; nếu không, Git dùng `url`.

```bash
# Gửi nhánh local main lên nhánh main của origin
git push origin main
```

Trong ví dụ trên, `origin` xác định cấu hình remote, còn `main` xác định ref được đẩy theo cách viết lệnh này. Máy chủ có thể từ chối cập nhật nếu người dùng không có quyền, nhánh được bảo vệ hoặc cập nhật không đáp ứng quy tắc fast-forward.

`git pull` kết hợp fetch với bước tích hợp thay đổi vào nhánh hiện tại. Bước tích hợp có thể dùng merge hoặc rebase tùy tùy chọn và cấu hình. Vì vậy, khi remote có địa chỉ fetch và push riêng, `git pull` lấy dữ liệu từ địa chỉ fetch, còn `git push` gửi dữ liệu đến địa chỉ push.

## 3. Khi nào hai địa chỉ giống nhau hoặc khác nhau?

Trong trường hợp thông thường, cùng một máy chủ nhận cả thao tác đọc và ghi. Khi đó chỉ cần cấu hình `url`:

```ini
[remote "origin"]
    url = https://git.example.com/team/app.git
    fetch = +refs/heads/*:refs/remotes/origin/*
```

Do không có `pushurl`, Git dùng `https://git.example.com/team/app.git` cho cả fetch và push.

Một hệ thống khác có thể cung cấp địa chỉ đọc và ghi riêng. Ví dụ, nhóm phát triển fetch từ máy chủ HTTPS dùng cho đọc và push qua SSH đến máy chủ nhận ghi:

```ini
[remote "origin"]
    url = https://read.git.example.com/team/app.git
    pushurl = git@write.git.example.com:team/app.git
    fetch = +refs/heads/*:refs/remotes/origin/*
```

Khi đó:

- `git fetch origin` kết nối đến `https://read.git.example.com/team/app.git`.
- `git pull origin main` fetch từ địa chỉ đọc trước khi tích hợp thay đổi.
- `git push origin main` kết nối đến `git@write.git.example.com:team/app.git`.

Địa chỉ khác nhau có thể phục vụ nhiều mục đích: dùng giao thức HTTPS để đọc nhưng SSH để ghi, fetch từ máy chủ mirror gần hơn, hoặc đẩy thay đổi đến repository fork trong khi vẫn lấy dữ liệu từ repository gốc.

## 4. Kiểm tra địa chỉ fetch và push đang có hiệu lực

Lệnh hữu ích nhất để kiểm tra nhanh cấu hình là:

```bash
git remote -v
```

Ví dụ kết quả khi hai địa chỉ khác nhau:

```text
origin  https://read.git.example.com/team/app.git (fetch)
origin  git@write.git.example.com:team/app.git (push)
```

Nhãn `(fetch)` và `(push)` cho biết mỗi địa chỉ được dùng cho thao tác nào. Nếu hai địa chỉ giống nhau, Git vẫn có thể hiển thị hai dòng với cùng URL.

Bạn cũng có thể truy vấn riêng từng địa chỉ:

```bash
# Địa chỉ fetch
git remote get-url origin

# Địa chỉ push hiệu lực
git remote get-url --push origin

# Hiển thị tất cả URL được cấu hình cho mục đích tương ứng
git remote get-url --all origin
git remote get-url --push --all origin
```

Để xem giá trị lưu trong cấu hình:

```bash
# Xem các giá trị URL dùng cho fetch
git config --get-all remote.origin.url

# Xem các giá trị pushurl; có thể không có kết quả nếu chưa cấu hình
git config --get-all remote.origin.pushurl
```

`git remote get-url` có thể mở rộng quy tắc viết tắt URL như `url.<base>.insteadOf`. Vì vậy, kết quả của lệnh này hữu ích khi muốn biết địa chỉ Git thực sự sử dụng sau khi áp dụng các quy tắc viết lại.

## 5. Cấu hình địa chỉ fetch và push riêng

### Đổi địa chỉ fetch

Sử dụng `git remote set-url`:

```bash
git remote set-url origin https://read.git.example.com/team/app.git
```

Lệnh này cập nhật `remote.origin.url`. Nếu remote chưa có `pushurl`, địa chỉ mới cũng trở thành địa chỉ push mặc định. Nếu `pushurl` đã được cấu hình riêng, địa chỉ push riêng đó vẫn được giữ nguyên.

### Đặt hoặc đổi địa chỉ push

Thêm tùy chọn `--push` để cập nhật địa chỉ push:

```bash
git remote set-url --push origin git@write.git.example.com:team/app.git
```

Từ thời điểm đó, `git fetch origin` tiếp tục dùng URL fetch, còn `git push origin ...` dùng URL push vừa cấu hình.

### Tạo remote rồi cấu hình hai địa chỉ

Có thể thực hiện theo từng bước:

```bash
# Tạo remote với địa chỉ fetch
git remote add origin https://read.git.example.com/team/app.git

# Cấu hình địa chỉ push riêng
git remote set-url --push origin git@write.git.example.com:team/app.git

# Kiểm tra lại cả hai địa chỉ
git remote -v
```

Nếu muốn bỏ địa chỉ push riêng để quay lại dùng chung URL, xóa cấu hình `pushurl`:

```bash
git config --unset-all remote.origin.pushurl
```

Sau khi xóa, push sẽ dùng `remote.origin.url`. Nếu có nhiều giá trị `pushurl`, lệnh `--unset-all` xóa tất cả các giá trị đó.

## 6. Ví dụ thực tế: fetch từ repository gốc, push lên fork

Trong quy trình fork, lập trình viên thường có quyền ghi vào repository fork của mình nhưng chỉ đọc repository gốc của dự án. Giả sử repository local chưa có hai remote `origin` và `upstream`; nếu `origin` đã tồn tại, hãy cập nhật URL của nó bằng `git remote set-url` thay vì thêm lại. Có thể cấu hình hai remote riêng:

```bash
# origin là fork mà bạn có quyền push
git remote add origin git@github.com:my-account/project.git

# upstream là repository gốc để lấy thay đổi mới
git remote add upstream https://github.com/original-owner/project.git

# Lấy các nhánh mới từ repository gốc
git fetch upstream

# Tạo nhánh công việc từ nhánh main đã cập nhật
git switch -c feature/search upstream/main

# Sau khi hoàn thành và commit, đẩy nhánh lên fork
git push -u origin feature/search
```

Ở cách tổ chức này, `origin` và `upstream` là hai remote khác nhau. `origin` trỏ đến fork; `upstream` trỏ đến repository gốc. Bạn fetch từ `upstream` và push nhánh của mình lên `origin`.

Một cách cấu hình thay thế là giữ một tên remote nhưng đặt fetch URL là repository gốc và push URL là fork. Ví dụ này dùng một repository local riêng; nếu `origin` đã tồn tại trong repository hiện tại, dùng `git remote set-url origin ...` để đổi fetch URL thay vì chạy `git remote add`:

```bash
# Tạo remote với URL đọc từ repository gốc
git remote add origin https://github.com/original-owner/project.git

# Chỉ định fork làm địa chỉ push
git remote set-url --push origin git@github.com:my-account/project.git

# Kiểm tra hướng kết nối
git remote -v
```

Với cấu hình thứ hai, `git fetch origin` lấy thay đổi từ repository gốc, còn `git push origin feature/search` đẩy nhánh lên fork. Cách này tiện khi muốn một tên remote đại diện cho hai đầu kết nối, nhưng cần kiểm tra kỹ `git remote -v` để tránh gửi nhầm thay đổi.

## 7. Phân biệt địa chỉ remote với nhánh đích

Địa chỉ fetch/push chỉ quyết định Git kết nối đến đâu. Nó không tự quyết định nhánh nào được lấy hoặc cập nhật. Việc chọn ref chịu ảnh hưởng của refspec, upstream branch và các tùy chọn push.

Ví dụ cấu hình fetch mặc định thường có dạng:

```ini
fetch = +refs/heads/*:refs/remotes/origin/*
```

Đây là refspec: lấy các nhánh trên remote và ánh xạ chúng thành remote-tracking branch dưới `refs/remotes/origin/`. Nó không phải URL và không thay đổi máy chủ được kết nối.

Các lệnh sau thể hiện rõ sự tách biệt:

```bash
# Chọn remote để fetch
git fetch origin

# Chọn remote và nhánh local/remote để push
git push origin feature/search:feature/search

# Xem nhánh upstream của nhánh hiện tại
git branch -vv
```

Khi gọi `git push` mà không ghi tên remote, Git có thể suy ra remote đích từ cấu hình như `branch.<name>.pushRemote`, `remote.pushDefault` hoặc upstream branch. `push.default` ảnh hưởng cách chọn ref cần đẩy. Những thiết lập này quyết định remote hoặc nhánh mặc định; sau khi remote được chọn, `pushurl` vẫn quyết định địa chỉ kết nối dùng cho push.

## 8. Chẩn đoán khi fetch được nhưng push thất bại

Fetch thành công không chứng minh rằng push sẽ thành công. Hai thao tác có thể dùng URL, giao thức, thông tin xác thực hoặc quyền truy cập khác nhau.

Khi gặp lỗi, hãy kiểm tra theo thứ tự:

1. **Xác nhận remote được chọn:** kiểm tra tên remote ghi trong lệnh push. Nếu không ghi tên remote, xem cấu hình mặc định bằng `git branch -vv` và các khóa `branch.<name>.pushRemote`, `remote.pushDefault`; `git remote -v` giúp đối chiếu URL của từng remote.
2. **Xác nhận địa chỉ push hiệu lực:** chạy `git remote get-url --push origin`, thay `origin` bằng remote thực tế.
3. **Kiểm tra cấu hình:** dùng `git config --get-all remote.origin.url` và `git config --get-all remote.origin.pushurl` để phát hiện URL cũ hoặc nhiều địa chỉ.
4. **Kiểm tra xác thực:** với HTTPS, xác nhận credential phù hợp; với SSH, xác nhận khóa và tài khoản SSH có quyền truy cập repository.
5. **Kiểm tra quyền và quy tắc nhánh:** tài khoản có thể đọc nhưng không có quyền ghi, hoặc nhánh đích có thể được bảo vệ.
6. **Kiểm tra lịch sử:** nếu remote có commit mới mà local chưa tích hợp, máy chủ có thể từ chối push non-fast-forward. Fetch và tích hợp thay đổi theo quy trình của nhóm trước khi push lại.

Không nên kết luận rằng cần đổi URL chỉ vì push bị từ chối. Trước tiên hãy xác định lỗi đến từ địa chỉ, xác thực, quyền ghi hay quan hệ lịch sử giữa hai nhánh.

## 9. Tự kiểm tra

1. **Nếu remote có `url` nhưng không có `pushurl`, Git dùng địa chỉ nào khi push?**
   - Dùng giá trị `remote.<name>.url` làm địa chỉ push mặc định.
2. **Khi đã cấu hình `pushurl`, lệnh `git fetch origin` kết nối đến đâu?**
   - Kết nối đến `remote.origin.url`; `pushurl` chỉ dành cho push.
3. **Lệnh nào hiển thị riêng địa chỉ push hiệu lực?**
   - `git remote get-url --push origin`.
4. **`remote.origin.fetch` có phải địa chỉ máy chủ không?**
   - Không. Đây là refspec ánh xạ ref từ remote vào local.
5. **Vì sao fetch thành công nhưng push vẫn có thể thất bại?**
   - Vì push có thể dùng địa chỉ hoặc giao thức khác, cần thông tin xác thực khác, thiếu quyền ghi hoặc bị từ chối do quy tắc cập nhật nhánh.

## Kết luận

`remote.<name>.url` xác định địa chỉ fetch và cũng là địa chỉ push mặc định. `remote.<name>.pushurl` cho phép chỉ định một đích push riêng. Dùng `git remote -v` và `git remote get-url --push` để kiểm tra hướng kết nối, `git remote set-url` để đổi URL fetch, và `git remote set-url --push` để cấu hình URL push. Khi vận hành Git trong nhóm, hãy luôn phân biệt nơi lấy lịch sử, nơi gửi commit và ref mà mỗi lệnh sẽ cập nhật.
