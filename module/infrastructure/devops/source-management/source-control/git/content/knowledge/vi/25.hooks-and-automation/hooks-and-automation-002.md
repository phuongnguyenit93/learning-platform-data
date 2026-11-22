# Các thời điểm pre-commit, prepare-commit-msg và commit-msg

Git hỗ trợ các **hook** để chạy chương trình tại những thời điểm nhất định trong quy trình làm việc. Ba hook thường dùng khi tạo commit là `pre-commit`, `prepare-commit-msg` và `commit-msg`. Chúng chạy ở các giai đoạn khác nhau: kiểm tra nội dung đã stage, chuẩn bị thông điệp commit và xác thực thông điệp trước khi Git tạo commit object.

Hiểu đúng thời điểm của từng hook giúp bạn đặt kiểm tra ở nơi phù hợp. Kiểm tra mã nguồn và quy tắc chất lượng thường đặt trong `pre-commit`; bổ sung ngữ cảnh vào thông điệp đặt trong `prepare-commit-msg`; kiểm tra định dạng hoặc quy ước thông điệp đặt trong `commit-msg`.

## 1. Vị trí của ba hook trong quy trình commit

Khi chạy `git commit`, Git thực hiện các bước chính theo thứ tự:

```text
Người dùng chạy git commit
          |
          v
     pre-commit
          |
          v
Chuẩn bị thông điệp commit mặc định
          |
          v
  prepare-commit-msg
          |
          v
Mở editor (nếu cần chỉnh sửa)
          |
          v
      commit-msg
          |
          v
   Tạo commit object
```

Nếu một hook trả về mã thoát khác `0`, Git dừng quy trình tạo commit. Hook có thể kiểm tra hoặc thay đổi dữ liệu ở giai đoạn nó được gọi. `prepare-commit-msg` có quyền sửa trực tiếp file thông điệp; `commit-msg` thường kiểm tra thông điệp đã hoàn chỉnh và có thể từ chối commit nếu không đạt quy ước.

Ba hook này là hook phía client. Chúng chạy trên máy của người tạo commit và có thể không được cài đặt ở mọi clone. Vì vậy, chúng hỗ trợ chất lượng và quy trình làm việc nhưng không nên là lớp kiểm soát duy nhất cho chính sách bắt buộc của toàn dự án.

## 2. `pre-commit`: kiểm tra trước khi tạo thông điệp commit

Hook `pre-commit` chạy sau khi Git xác định lệnh commit có thể tiếp tục, nhưng trước khi Git chuẩn bị thông điệp commit và mở editor. Hook này thường được dùng để:

- Kiểm tra whitespace và lỗi định dạng trong phần đã stage.
- Chạy linter, formatter hoặc kiểm tra tĩnh.
- Chạy test nhanh cần thiết trước khi commit.
- Ngăn commit khi phát hiện tệp không phù hợp, secret hoặc lỗi quy ước.

Hook `pre-commit` không nhận tham số bắt buộc. Nó có thể đọc index và working tree bằng các lệnh Git thông thường. Đặc biệt, `git diff --cached` cho biết nội dung đã stage, tức nội dung dự kiến được đưa vào commit.

### Ví dụ: từ chối commit khi có lỗi whitespace

Tạo file hook tên `pre-commit` trong thư mục hooks đang được Git sử dụng:

```sh
#!/bin/sh

if ! git diff --cached --check; then
    echo "Commit bị từ chối: hãy sửa lỗi whitespace trong phần đã stage."
    exit 1
fi

exit 0
```

`git diff --cached --check` kiểm tra các lỗi whitespace trong thay đổi đã stage, chẳng hạn khoảng trắng thừa ở cuối dòng hoặc dấu whitespace gây lỗi theo quy tắc diff. Nếu lệnh trả về lỗi, hook trả mã khác `0` và Git không tạo commit.

Trên hệ điều hành POSIX, cần đặt quyền thực thi cho hook:

```bash
chmod +x .git/hooks/pre-commit
```

Đường dẫn `.git/hooks` là vị trí mặc định trong repository thông thường. Nếu repository cấu hình `core.hooksPath`, Git sẽ tìm hook trong thư mục được cấu hình thay thế.

### Kiểm tra đúng nội dung sẽ được commit

Một lỗi thiết kế phổ biến là chạy formatter hoặc test trên toàn bộ working tree nhưng không kiểm tra nội dung đã stage. Người dùng có thể đã stage một phiên bản, sau đó tiếp tục sửa file; working tree và index lúc này khác nhau.

```bash
# Xem phần đã stage
git diff --cached

# Xem phần chưa stage
git diff
```

Hook cần xác định rõ nó đang kiểm tra dữ liệu nào. Với kiểm tra dựa trên diff, dùng `git diff --cached`. Với test chạy trên working tree, cần hiểu rằng test có thể đọc cả thay đổi chưa stage; nếu kết quả test phải tương ứng chính xác với commit, quy trình nên kiểm tra bản nội dung đã stage hoặc dùng công cụ chuyên xử lý staged files.

Nếu hook tự sửa tệp, thay đổi đó không tự động trở thành nội dung staged. Hook hoặc công cụ đi kèm cần cập nhật index có chủ đích, sau đó người dùng nên xem lại `git diff --cached` trước khi commit.

## 3. `prepare-commit-msg`: chuẩn bị file thông điệp

Hook `prepare-commit-msg` chạy sau khi Git tạo thông điệp commit ban đầu và trước khi mở editor. Hook nhận các tham số:

| Tham số | Nội dung |
|---|---|
| `$1` | Đường dẫn đến file đang chứa thông điệp commit cần chuẩn bị |
| `$2` | Nguồn tạo thông điệp, nếu có; ví dụ `message`, `template`, `merge`, `squash` hoặc `commit` |
| `$3` | OID của commit nguồn trong trường hợp thông điệp được lấy từ một commit, chẳng hạn khi dùng `-C`, `-c` hoặc amend |

Hook có thể đọc hoặc sửa file ở `$1`. Nó thường được dùng để:

- Thêm mã ticket lấy từ tên nhánh.
- Bổ sung ngữ cảnh khi tạo merge commit.
- Tạo phần mở đầu hoặc mẫu nội dung cho thông điệp.
- Chuẩn bị nội dung theo quy ước của dự án trước khi người dùng chỉnh sửa.

### Ví dụ: thêm tên nhánh vào phần chú thích của thông điệp

Ví dụ dưới đây thêm tên nhánh vào dòng chú thích để người dùng nhìn thấy khi mở editor. Git loại bỏ các dòng chú thích theo ký tự comment được cấu hình khi tạo commit:

```sh
#!/bin/sh

message_file=$1
branch=$(git symbolic-ref --quiet --short HEAD 2>/dev/null || true)

if [ -n "$branch" ]; then
    printf '\n# Branch: %s\n' "$branch" >> "$message_file"
fi

exit 0
```

Ví dụ này dùng ký tự `#` mặc định làm comment character. Nếu dự án cấu hình `core.commentChar` khác, cần điều chỉnh script để phù hợp. Hook chỉ thêm thông tin tham khảo; người dùng vẫn quyết định nội dung thông điệp cuối cùng.

### Hook này không bị bỏ qua bởi `--no-verify`

Khác với `pre-commit` và `commit-msg`, `prepare-commit-msg` không bị bỏ qua khi chạy:

```bash
git commit --no-verify
```

Vì vậy, không nên đặt một kiểm tra tùy chọn hoặc thao tác có thể gây lỗi ngoài ý muốn trong hook này nếu người dùng cần khả năng bỏ qua bằng `--no-verify`. Hãy dành hook này cho việc chuẩn bị thông điệp có thể dự đoán và an toàn.

## 4. `commit-msg`: xác thực thông điệp trước khi tạo commit

Hook `commit-msg` chạy sau khi thông điệp đã được chuẩn bị và người dùng đã chỉnh sửa (nếu có), nhưng trước khi commit object được tạo. Hook nhận một tham số:

| Tham số | Nội dung |
|---|---|
| `$1` | Đường dẫn đến file chứa thông điệp commit cuối cùng đang được kiểm tra |

Hook có thể đọc file này, kiểm tra quy tắc và trả mã khác `0` để từ chối commit. Nó cũng có thể sửa file thông điệp, nhưng thông thường nên tập trung vào việc xác thực để tránh thay đổi nội dung người dùng vừa nhập mà họ không biết.

### Ví dụ: kiểm tra định dạng subject

Giả sử nhóm yêu cầu dòng đầu tiên theo quy ước:

```text
feat: add account endpoint
fix(auth): reject expired token
docs: clarify installation steps
```

Hook `commit-msg` có thể kiểm tra subject như sau:

```sh
#!/bin/sh

message_file=$1
subject=$(sed -n '1p' "$message_file")

if ! printf '%s\n' "$subject" | grep -Eq '^(feat|fix|docs|refactor|test|chore)(\([^)]+\))?: .{1,72}$'; then
    echo "Commit bị từ chối: subject phải theo dạng type(scope): mô tả, tối đa 72 ký tự."
    exit 1
fi

exit 0
```

Hook đọc dòng đầu tiên, kiểm tra loại commit, scope tùy chọn, dấu hai chấm và phần mô tả. Nếu không khớp, nó trả mã `1`, khiến Git hủy commit. Quy tắc biểu thức chính quy cần được điều chỉnh theo quy ước thực tế của nhóm, ví dụ giới hạn độ dài, chữ hoa/thường hoặc danh sách type được phép.

### Vì sao không chỉ kiểm tra bằng `pre-commit`?

`pre-commit` chạy trước khi thông điệp cuối cùng được nhập. Nó phù hợp để kiểm tra mã nguồn và index, nhưng không phải nơi thích hợp để xác thực nội dung subject mà người dùng chưa hoàn tất. `commit-msg` được gọi đúng thời điểm thông điệp đã sẵn sàng để kiểm tra.

## 5. So sánh ba hook

| Hook | Thời điểm | Tham số | Công việc phù hợp | Có thể chặn commit? |
|---|---|---|---|---|
| `pre-commit` | Trước khi chuẩn bị thông điệp | Không có tham số bắt buộc | Lint, test, kiểm tra staged diff, phát hiện secret | Có, nếu trả mã khác `0` |
| `prepare-commit-msg` | Sau khi tạo thông điệp ban đầu, trước editor | File message, source, OID tùy trường hợp | Bổ sung ngữ cảnh, tạo nội dung ban đầu, tự động thêm ticket | Có, nếu trả mã khác `0` |
| `commit-msg` | Sau khi thông điệp được chuẩn bị, trước khi tạo commit | File message | Kiểm tra format, ticket ID, độ dài subject, quy tắc nội dung | Có, nếu trả mã khác `0` |

Hãy đặt mỗi kiểm tra ở giai đoạn phù hợp. Ví dụ, chạy unit test ở `pre-commit`, thêm thông tin nhánh vào thông điệp ở `prepare-commit-msg`, rồi kiểm tra subject ở `commit-msg`.

## 6. Cài đặt và kiểm tra hook trong repository

Git thường tạo sẵn các file mẫu trong `.git/hooks` với phần mở rộng `.sample`. Những file mẫu này không tự chạy. Để bật một hook, tạo file có đúng tên, ví dụ `pre-commit`, `prepare-commit-msg` hoặc `commit-msg`, rồi bảo đảm Git có thể thực thi nó.

Kiểm tra thư mục hooks mặc định và cấu hình thay thế:

```bash
# Xem thư mục hooks mặc định của repository
git rev-parse --git-path hooks

# Kiểm tra cấu hình hooksPath nếu có
git config --show-origin --get core.hooksPath
```

Nếu muốn lưu hook trong một thư mục được commit cùng dự án, có thể dùng `.githooks`:

```bash
mkdir -p .githooks
git config --local core.hooksPath .githooks
```

Sau đó tạo các file `.githooks/pre-commit`, `.githooks/prepare-commit-msg` hoặc `.githooks/commit-msg`. Trên POSIX, đặt quyền thực thi:

```bash
chmod +x .githooks/pre-commit
chmod +x .githooks/prepare-commit-msg
chmod +x .githooks/commit-msg
```

Lưu ý `core.hooksPath` là cấu hình local của repository, không tự được chia sẻ chỉ vì thư mục `.githooks` được commit. Dự án cần hướng dẫn bootstrap hoặc script thiết lập để mỗi thành viên bật cấu hình này. Nếu hook dùng công cụ như Node.js, Python hoặc formatter riêng, nhóm cũng cần hướng dẫn cài phiên bản và dependency tương ứng.

## 7. Kiểm tra thứ tự chạy và xử lý khi hook từ chối commit

Khi commit bị dừng, đọc thông báo của hook để biết bước nào thất bại. Kiểm tra file và cấu hình:

```bash
# Xem các thay đổi đã stage
git diff --cached

# Xem trạng thái hiện tại
git status

# Xem hooksPath hiệu lực
git config --show-origin --get core.hooksPath
```

Nếu `pre-commit` từ chối, sửa lỗi mã nguồn hoặc staged diff rồi stage lại phần cần commit. Nếu `commit-msg` từ chối, sửa dòng subject trong thông điệp và chạy commit lại. Nếu `prepare-commit-msg` làm thay đổi thông điệp không mong muốn, kiểm tra script và nguồn thông điệp truyền vào hook.

Không xóa hook hoặc tắt kiểm tra chỉ để làm lệnh commit chạy qua. Nếu hook có lỗi kỹ thuật, sửa script hoặc cấu hình để nó kiểm tra đúng nội dung và trả mã thoát phù hợp.

## 8. `--no-verify` và giới hạn của client-side hooks

Tùy chọn `--no-verify` bỏ qua hai hook:

```bash
git commit --no-verify
```

- Bỏ qua `pre-commit`.
- Bỏ qua `commit-msg`.
- Không bỏ qua `prepare-commit-msg`.

Điều này có nghĩa client-side hook không thể là cơ chế bảo đảm duy nhất cho quy tắc bắt buộc. Người dùng có thể bỏ qua một số kiểm tra, hook có thể chưa được cài ở clone mới, hoặc môi trường máy có thể thiếu dependency.

Với chính sách cần áp dụng cho mọi đóng góp, hãy đặt thêm kiểm tra ở CI hoặc server-side hook / quy tắc bảo vệ nhánh trên nền tảng lưu trữ. Client hook giúp phản hồi sớm ngay trên máy lập trình viên; CI và server kiểm tra lại trước khi thay đổi được tích hợp vào nhánh dùng chung.

## 9. Lưu ý về bảo mật và độ tin cậy

Hook là chương trình có thể chạy lệnh trên máy người dùng. Trước khi bật hook từ một repository, hãy đọc nội dung và hiểu nó thực hiện gì. Một hook có thể chạy formatter, truy cập file, gọi chương trình bên ngoài hoặc làm thay đổi working tree/index.

Khi thiết kế hook cho nhóm:

- Giữ hook ngắn, có thông báo lỗi cụ thể và mã thoát rõ ràng.
- Không ghi token, mật khẩu hoặc dữ liệu nhạy cảm vào log.
- Không giả định mọi máy đều có cùng phiên bản runtime hoặc công cụ.
- Chỉ sửa thông điệp hoặc index khi hành vi đó được tài liệu hóa và người dùng có thể xem lại.
- Tách kiểm tra nhanh ở local khỏi test tích hợp dài chạy trong CI.
- Không xem kết quả hook local là bằng chứng duy nhất rằng commit an toàn hoặc đạt chính sách.

## 10. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu chính xác |
|---|---|
| `pre-commit` kiểm tra được thông điệp cuối cùng | Hook này chạy trước khi thông điệp được chuẩn bị; dùng `commit-msg` để xác thực thông điệp cuối. |
| `prepare-commit-msg` chỉ chạy khi mở editor | Hook chạy sau khi Git chuẩn bị thông điệp và trước editor; nó vẫn có thể chạy khi thông điệp được cung cấp bằng tùy chọn dòng lệnh. |
| `prepare-commit-msg` bị bỏ qua bởi `--no-verify` | Không. Tùy chọn này bỏ qua `pre-commit` và `commit-msg`, không bỏ qua `prepare-commit-msg`. |
| `commit-msg` không thể từ chối commit | Có thể trả mã khác `0` để Git hủy commit. |
| File `.sample` trong `.git/hooks` tự động chạy | File mẫu không hoạt động cho đến khi được cài thành hook với tên phù hợp. |
| Hook trong `.git/hooks` tự được chia sẻ khi push | Thư mục `.git` không được commit; cần cơ chế cài đặt hoặc `core.hooksPath` trỏ đến thư mục hook được quản lý trong dự án. |
| Hook local bảo đảm mọi người đều tuân thủ chính sách | Hook có thể chưa được cài hoặc bị bỏ qua; chính sách bắt buộc cần kiểm tra thêm trong CI/server. |

## 11. Tự kiểm tra

1. **Hook nào phù hợp để chạy lint trên phần đã stage?**
   - `pre-commit`.
2. **Hook nào có thể thêm thông tin vào file thông điệp trước khi mở editor?**
   - `prepare-commit-msg`.
3. **Hook nào phù hợp để kiểm tra quy ước subject cuối cùng?**
   - `commit-msg`.
4. **`prepare-commit-msg` nhận tham số nào?**
   - Đường dẫn file thông điệp, nguồn thông điệp nếu có và OID commit nguồn trong trường hợp phù hợp.
5. **`git commit --no-verify` bỏ qua những hook nào trong ba hook đang học?**
   - Bỏ qua `pre-commit` và `commit-msg`; không bỏ qua `prepare-commit-msg`.
6. **Vì sao cần kiểm tra thêm bằng CI hoặc server-side?**
   - Vì client-side hook có thể chưa được cài hoặc bị bỏ qua; CI/server là nơi kiểm tra chính sách chung cho repository.

## Kết luận

`pre-commit`, `prepare-commit-msg` và `commit-msg` được gọi ở ba thời điểm khác nhau trong quy trình tạo commit. Dùng `pre-commit` để kiểm tra mã nguồn và nội dung đã stage, `prepare-commit-msg` để chuẩn bị file thông điệp, và `commit-msg` để xác thực thông điệp cuối. Các hook có thể chặn commit bằng mã thoát khác `0`, nhưng `--no-verify` vẫn bỏ qua `pre-commit` và `commit-msg`. Vì vậy, hãy dùng hook để tăng phản hồi sớm cho lập trình viên và dùng CI hoặc chính sách phía server cho các yêu cầu bắt buộc của nhóm.
