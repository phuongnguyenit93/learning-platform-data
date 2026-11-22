# Vòng lặp làm việc: sửa tệp, kiểm tra, đưa vào chỉ mục và commit

Một thay đổi được quản lý tốt trong Git thường đi qua một vòng lặp ngắn: xem trạng thái hiện tại, sửa tệp, kiểm tra phần vừa sửa, chọn nội dung cần đưa vào staging area, xem lại nội dung đã chọn rồi tạo commit. Lặp lại vòng này cho từng phần việc giúp lịch sử Git phản ánh những thay đổi có chủ đích, dễ đọc và dễ truy tìm.

Sau bài này, bạn có thể:

- Phân biệt working tree, staging area (index) và repository.
- Đọc trạng thái tệp để biết thay đổi đang ở bước nào.
- Xem và kiểm tra diff trước khi đưa thay đổi vào chỉ mục.
- Stage toàn bộ hoặc chọn từng phần của một tệp.
- Xác minh chính xác nội dung sẽ được lưu trong commit.
- Tạo commit có ý nghĩa và kiểm tra kết quả sau commit.

## 1. Hiểu ba nơi Git quản lý thay đổi

Khi làm việc trong một repository, Git theo dõi nội dung qua ba khu vực chính:

| Khu vực | Ý nghĩa | Thao tác thường gặp |
| --- | --- | --- |
| Working tree (thư mục làm việc) | Các tệp bạn đang mở, tạo, sửa hoặc xóa trên máy. | Sửa mã nguồn, tài liệu, cấu hình; chạy ứng dụng và kiểm tra. |
| Staging area (index, vùng chuẩn bị) | Bản chụp những thay đổi bạn chọn cho commit kế tiếp. | `git add`, `git restore --staged`, `git diff --cached`. |
| Repository (cơ sở dữ liệu Git) | Các commit đã được ghi nhận cùng lịch sử và quan hệ giữa chúng. | `git commit`, `git log`, `git show`. |

Luồng dữ liệu cơ bản:

```text
Working tree  -- git add -->  Staging area  -- git commit -->  Repository
     ^                              |
     |                              |
     +------ chỉnh sửa tiếp --------+
```

Sửa tệp chỉ làm thay đổi working tree. `git add` chụp nội dung tại thời điểm chạy lệnh và đưa bản chụp đó vào staging area. `git commit` ghi những gì đang có trong staging area thành một commit. Vì vậy, một tệp có thể vừa có phần đã stage, vừa có phần sửa thêm chưa stage.

Commit được tạo trên máy cục bộ. Việc commit không tự gửi thay đổi lên remote; chia sẻ commit với nhóm là bước riêng, thường thực hiện bằng `git push`.

## 2. Bắt đầu bằng cách xem trạng thái repository

Trước khi sửa hoặc stage bất kỳ thứ gì, hãy xem repository đang ở trạng thái nào:

```bash
git status
git status --short --branch
```

Lệnh đầu tiên đưa ra mô tả dễ đọc. Lệnh thứ hai hiển thị dạng rút gọn, thuận tiện khi kiểm tra thường xuyên. Trong kết quả rút gọn, hai ký tự ở đầu mỗi dòng biểu thị trạng thái tại index và working tree:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| ` M file` | Tệp đã sửa trong working tree nhưng chưa stage. |
| `M  file` | Thay đổi của tệp đã được stage. |
| `MM file` | Tệp có thay đổi đã stage và còn có thay đổi mới chưa stage. |
| `A  file` | Tệp mới đã được stage. |
| ` D file` | Tệp bị xóa trong working tree nhưng thao tác xóa chưa stage. |
| `D  file` | Thao tác xóa đã được stage. |
| `?? file` | Tệp mới, chưa được Git theo dõi. |

Ký tự thứ nhất mô tả index; ký tự thứ hai mô tả working tree. Ví dụ ` M` có nghĩa là working tree khác index, còn `M ` có nghĩa là index khác commit hiện tại. Khi thấy `MM`, hãy hiểu rằng nội dung trong index và nội dung hiện có trên đĩa không giống nhau.

Nếu `git status` báo working tree sạch, nghĩa là Git không thấy thay đổi chưa commit trong các tệp được theo dõi và không có tệp mới chưa được theo dõi. Bạn có thể bắt đầu một công việc mới với trạng thái rõ ràng.

## 3. Sửa tệp và xem phần thay đổi

Hãy thực hiện thay đổi có phạm vi cụ thể: sửa lỗi, bổ sung một hành vi, cập nhật tài liệu hoặc điều chỉnh cấu hình. Sau đó dùng `git diff` để xem Git ghi nhận điều gì:

```bash
git diff
git diff -- path/to/file
git diff --stat
```

- `git diff` so sánh working tree với staging area, nên hiển thị các thay đổi chưa stage của tệp đã được theo dõi.
- `git diff -- path/to/file` giới hạn kết quả vào một đường dẫn.
- `git diff --stat` tóm tắt số tệp và số dòng thay đổi.

Một đoạn diff thường có dạng:

```diff
diff --git a/src/Greeter.java b/src/Greeter.java
index 12ab345..67cd890 100644
--- a/src/Greeter.java
+++ b/src/Greeter.java
@@ -4,7 +4,7 @@ public class Greeter {
     public String greeting(String name) {
-        return "Hello " + name;
+        return "Hello, " + name + "!";
     }
 }
```

Các dòng bắt đầu bằng `-` là nội dung cũ bị loại bỏ; các dòng bắt đầu bằng `+` là nội dung mới được thêm vào. Phần `@@` cho biết vùng dòng được so sánh. Hãy đọc diff như một bản xem trước của thay đổi: tên tệp có đúng không, logic có đúng không, có dòng debug hoặc chỉnh sửa ngoài phạm vi nào lọt vào không?

Lưu ý: `git diff` thông thường không hiển thị nội dung của tệp mới chưa được theo dõi. Git chưa có phiên bản trước đó để so sánh. Hãy kiểm tra tệp đó trong trình soạn thảo và xác nhận nó xuất hiện trong `git status`; sau khi stage, bạn có thể xem nội dung bằng `git diff --cached`.

## 4. Kiểm tra trước khi stage

Diff giúp kiểm tra nội dung, còn các lệnh kiểm tra của dự án giúp xác nhận thay đổi không làm hỏng hành vi hiện có. Tùy loại dự án, hãy chạy các bước phù hợp, chẳng hạn:

```bash
# Phát hiện khoảng trắng thừa và lỗi định dạng whitespace trong diff
git diff --check

# Ví dụ: chạy bộ kiểm tra do dự án cung cấp
./gradlew test
```

`./gradlew test` chỉ là ví dụ cho dự án dùng Gradle Wrapper; hãy dùng lệnh kiểm tra thực tế của repository bạn đang làm việc. Với thay đổi tài liệu, có thể cần kiểm tra liên kết, chính tả hoặc bộ kiểm tra Markdown. Với thay đổi mã nguồn, hãy chạy test liên quan và thêm kiểm tra rộng hơn khi phạm vi thay đổi yêu cầu.

Nếu kiểm tra thất bại, đọc thông báo lỗi, sửa nguyên nhân rồi chạy lại bước kiểm tra liên quan. Sau mỗi lần sửa tiếp, xem lại `git diff` vì nội dung working tree đã thay đổi.

## 5. Đưa đúng thay đổi vào staging area

Staging area là nơi bạn chọn nội dung cho commit tiếp theo. Hãy stage theo phạm vi công việc:

```bash
# Stage một tệp cụ thể
git add src/Greeter.java

# Stage một số tệp cụ thể
git add src/Greeter.java docs/usage.md

# Stage tất cả thay đổi trong repository: thêm, sửa và xóa
git add -A
```

`git add -A` rất tiện khi bạn đã xem toàn bộ thay đổi và muốn đưa tất cả vào cùng một commit. Nếu repository có nhiều phần việc độc lập, hãy ưu tiên chỉ rõ đường dẫn để tránh stage nhầm. `git add .` cũng là cách stage theo thư mục hiện tại; phạm vi của nó phụ thuộc vị trí bạn đang đứng, vì vậy hãy hiểu pathspec trước khi dùng.

Bạn cũng có thể stage từng phần của một tệp:

```bash
git add -p src/Greeter.java
```

Git sẽ lần lượt hiển thị các khối thay đổi (hunk) và hỏi bạn có muốn stage từng khối hay không. Cách này hữu ích khi một tệp chứa nhiều thay đổi nhưng bạn muốn tách chúng thành các commit riêng. Đọc nội dung từng hunk trước khi chọn; có thể yêu cầu Git chia nhỏ hunk hoặc bỏ qua hunk hiện tại.

Sau khi stage, kiểm tra lại:

```bash
git status --short
```

Đừng coi việc `git add` chạy thành công là bằng chứng rằng bạn đã stage đúng. Trạng thái repository mới cho biết đường dẫn nào đã vào index; bước tiếp theo là xem nội dung thực tế trong index.

## 6. Xem lại chính xác nội dung sẽ được commit

Lệnh `git diff` và `git diff --cached` trả lời hai câu hỏi khác nhau:

```bash
# Phần đã sửa nhưng chưa stage
git diff

# Phần đã stage, sẽ được đưa vào commit kế tiếp
git diff --cached

# Kiểm tra whitespace trong phần đã stage
git diff --cached --check

# Tóm tắt phần đã stage
git diff --cached --stat
```

`git diff --cached` cũng có thể viết là `git diff --staged`. Đây là lần rà soát quan trọng trước commit. Hãy xác nhận:

1. Tất cả tệp cần có đều xuất hiện.
2. Không có tệp tạm, log, file build hoặc thông tin bí mật.
3. Nội dung staged tạo thành một thay đổi có mục đích rõ ràng.
4. Các phần sửa còn lại trong `git diff` là có chủ đích và sẽ được xử lý sau.

Một tệp có thể ở trạng thái `MM` nếu bạn stage nó rồi tiếp tục sửa. Trong trường hợp đó, `git diff --cached` hiển thị phiên bản đã stage; `git diff` hiển thị phần sửa thêm sau lần stage. Commit chỉ ghi phiên bản trong index. Nếu muốn đưa phần sửa mới vào cùng commit, chạy `git add` lại rồi xem lại staged diff.

Nếu stage nhầm một tệp nhưng vẫn muốn giữ nội dung đã sửa trong working tree, bỏ tệp khỏi index bằng:

```bash
git restore --staged path/to/file
```

Lệnh này gỡ nội dung khỏi staging area và giữ các chỉnh sửa trong working tree. Sau đó, stage lại đúng phần cần thiết. Ngược lại, `git restore path/to/file` có thể thay nội dung working tree bằng phiên bản trong index và làm mất các chỉnh sửa chưa stage của tệp; chỉ dùng khi bạn hiểu rõ phần nội dung sẽ bị loại bỏ.

## 7. Tạo commit

Khi staged diff đã đúng và các kiểm tra cần thiết đã đạt, tạo commit:

```bash
git commit -m "Fix greeting punctuation"
```

Git tạo một commit từ nội dung đang có trong staging area. Các thay đổi chưa stage không được đưa vào commit đó. Nếu không có gì trong index, Git thường báo không có thay đổi để commit.

Một thông điệp commit tốt giúp người đọc hiểu mục đích của thay đổi. Hãy viết ngắn gọn, dùng động từ rõ nghĩa và mô tả kết quả chính. Ví dụ:

```text
Add validation for empty usernames
Fix incorrect timeout calculation
Document the local setup workflow
```

Tránh các thông điệp không cung cấp thông tin như `update`, `fix`, `changes` hoặc `test`. Nếu thay đổi cần giải thích thêm, có thể dùng phần thân commit để nêu lý do, cách tiếp cận và tác động cần lưu ý.

Sau khi commit, xác minh kết quả:

```bash
git show --stat --oneline HEAD
git status --short --branch
```

`git show` cho biết commit vừa tạo và các tệp được ghi nhận. `git status` giúp xác nhận working tree còn thay đổi nào chưa commit hay không. Nếu còn thay đổi, hãy xác định đó là phần việc tiếp theo hay phần vô tình bị bỏ sót.

## 8. Một vòng lặp hoàn chỉnh trong thực tế

Giả sử bạn cần sửa cách tạo lời chào trong `src/Greeter.java` và cập nhật hướng dẫn sử dụng trong `docs/usage.md`. Có thể làm theo trình tự:

```bash
# 1. Xem trạng thái trước khi bắt đầu
git status --short --branch

# 2. Sửa hai tệp trong trình soạn thảo

# 3. Xem thay đổi trong working tree
git diff -- src/Greeter.java docs/usage.md

# 4. Chạy kiểm tra phù hợp
git diff --check
./gradlew test

# 5. Stage đúng hai tệp
git add src/Greeter.java docs/usage.md

# 6. Rà soát nội dung sẽ được commit
git diff --cached
git diff --cached --check

# 7. Tạo commit
git commit -m "Improve greeting behavior and usage docs"

# 8. Kiểm tra kết quả
git show --stat --oneline HEAD
git status --short --branch
```

Các dòng chú thích mô tả thao tác thủ công trong trình soạn thảo và ý nghĩa từng bước. Hãy thay đường dẫn, lệnh test và thông điệp commit bằng nội dung thực tế của công việc. Nếu bước kiểm tra phát hiện lỗi, quay lại sửa tệp và bắt đầu rà soát diff từ đầu; nếu bạn sửa tệp sau khi stage, hãy stage lại phần cần đưa vào commit.

## 9. Xử lý một số tình huống thường gặp

### Đã sửa tệp nhưng `git diff` không hiển thị nội dung mong đợi

Chạy `git status --short` để xác định tệp đang được theo dõi hay chưa. Tệp mới có trạng thái `??` nên không xuất hiện trong diff thông thường. Nếu tệp bị ignore, kiểm tra quy tắc ignore đang áp dụng trước khi quyết định có cần thêm tệp đó vào repository hay không.

### Đã stage nhưng sửa thêm, commit không chứa phần sửa mới

Đó là hành vi bình thường: index giữ bản chụp tại thời điểm `git add`. Chạy `git diff` để xem phần mới sửa, sau đó `git add` lại tệp và kiểm tra `git diff --cached`.

### Stage nhầm tệp

Dùng `git restore --staged path/to/file` để bỏ tệp khỏi index nhưng giữ nội dung trong working tree. Kiểm tra lại bằng `git status --short` và staged diff trước khi stage phần đúng.

### Một tệp không xuất hiện trong trạng thái Git

Tệp có thể nằm ngoài repository, khớp quy tắc trong `.gitignore`, hoặc chưa được lưu từ trình soạn thảo xuống đĩa. Kiểm tra đường dẫn hiện tại, trạng thái tệp và quy tắc ignore. `.gitignore` chủ yếu ngăn tệp chưa được theo dõi xuất hiện như tệp mới; nó không tự ngừng theo dõi một tệp đã được commit trước đó.

### Commit bị từ chối bởi hook hoặc thiếu thông tin tác giả

Đọc thông báo Git trả về. Hook có thể yêu cầu sửa định dạng, chạy test hoặc tuân thủ quy tắc commit của dự án. Nếu Git chưa biết tên hoặc email tác giả, cấu hình danh tính theo chính sách của môi trường làm việc rồi thử commit lại. Không bỏ qua hook chỉ để làm cho commit thành công khi chưa hiểu lý do hook thất bại.

### Muốn bỏ các chỉnh sửa trong working tree

Trước tiên xem `git diff` để biết nội dung nào sẽ mất. `git restore path/to/file` khôi phục tệp theo phiên bản trong index và có thể xóa phần sửa chưa stage. Nếu thay đổi cần giữ lại, hãy sao lưu hoặc commit/stash theo quy trình phù hợp trước khi khôi phục. Tránh dùng các lệnh diện rộng như `git reset --hard` khi chưa xác định rõ phạm vi và hậu quả.

## 10. Thói quen giúp commit an toàn và dễ xem lại

- Kiểm tra `git status` trước khi bắt đầu và trước khi commit.
- Sửa theo từng mục tiêu nhỏ; tránh gom nhiều việc không liên quan vào một commit.
- Đọc diff sau khi sửa và đọc lại staged diff sau khi stage.
- Chạy kiểm tra phù hợp với loại thay đổi và xử lý lỗi trước khi commit.
- Stage theo đường dẫn hoặc theo hunk khi repository có nhiều thay đổi.
- Không đưa mật khẩu, token, khóa riêng, tệp môi trường cá nhân hoặc sản phẩm build không cần thiết vào commit.
- Viết thông điệp commit mô tả mục đích và kết quả thay đổi.
- Kiểm tra commit mới bằng `git show` và trạng thái còn lại bằng `git status`.

Hãy nhớ rằng staging area là bản nội dung Git sẽ ghi vào commit kế tiếp. Vì vậy, vòng lặp đáng tin cậy luôn có hai lần xem diff: một lần sau khi sửa để hiểu thay đổi trong working tree, và một lần sau khi stage để xác nhận chính xác nội dung chuẩn bị lưu vào lịch sử.
