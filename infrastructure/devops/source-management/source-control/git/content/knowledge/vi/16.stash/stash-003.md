# Đưa tệp chưa theo dõi hoặc tệp bị bỏ qua vào stash bằng -u, -a

Lệnh `git stash` thông thường cất các thay đổi của những tệp đã được Git theo dõi. Nếu bạn vừa tạo tệp mới hoặc có tệp đang bị `.gitignore` bỏ qua, các tệp đó có thể vẫn nằm trong working tree sau khi stash. Hai tùy chọn `-u` và `-a` mở rộng phạm vi stash để bạn có thể chuyển nhánh hoặc xử lý công việc khác mà vẫn giữ lại các tệp này. Cần hiểu rõ sự khác nhau vì `-a` còn đưa cả tệp bị ignore vào stash và dọn chúng khỏi working tree.

## 1. Phân biệt tracked, untracked và ignored

Git phân loại tệp trong working tree theo trạng thái quản lý:

| Trạng thái | Ý nghĩa | Ví dụ |
|---|---|---|
| Tracked | Tệp đã được Git biết qua commit hoặc đã được đưa vào index | `src/main/App.java` |
| Untracked | Tệp chưa được Git theo dõi, chưa được đưa vào commit hoặc index | `src/main/NewService.java` vừa tạo |
| Ignored | Tệp chưa được theo dõi và khớp quy tắc bỏ qua trong `.gitignore`, `.git/info/exclude` hoặc cấu hình exclude toàn cục | `build/`, `.env.local`, file log |

Một tệp mới không tự động trở thành tracked chỉ vì nó nằm trong thư mục repository. Bạn cần `git add` để đưa tệp vào index. Nếu tệp mới khớp quy tắc ignore, Git thường không liệt kê nó như untracked trong trạng thái thông thường.

Kiểm tra trạng thái trước khi stash:

```bash
git status --short
git status --short --ignored
```

Lệnh thứ hai hiển thị thêm các mục ignored, thường được đánh dấu `!!`. Để biết quy tắc nào đang bỏ qua một tệp cụ thể:

```bash
git check-ignore -v .env.local
```

Lệnh này cho biết file quy tắc và dòng đã khớp nếu tệp bị ignore. Việc một tệp bị ignore không có nghĩa nó vô hại hoặc có thể xóa; đó có thể là cấu hình local, dữ liệu sinh tự động hoặc thông tin nhạy cảm.

## 2. Stash mặc định lưu những gì?

Khi chạy:

```bash
git stash push
```

Git lưu các thay đổi của tệp tracked trong index và working tree vào một stash entry, sau đó đưa các tệp tracked trở lại trạng thái của `HEAD` theo cách stash hỗ trợ. Tệp untracked và ignored mặc định không được đưa vào stash nên vẫn còn trong working tree.

Ví dụ, trước khi stash bạn có:

- Sửa `src/main/App.java` (tracked).
- Tạo `src/main/NewService.java` (untracked).
- Có `build/output.log` đang bị ignore.

Sau `git stash push`, thay đổi của `App.java` được cất, nhưng `NewService.java` và `build/output.log` vẫn còn. Nếu mục tiêu là làm sạch working tree để chuyển sang nhánh khác, hai tệp còn lại có thể vẫn gây vướng hoặc bị nhầm với công việc trên nhánh mới.

## 3. Dùng `-u` để stash tệp untracked

Tùy chọn `-u` là viết tắt của `--include-untracked`. Nó yêu cầu Git đưa cả tệp untracked vào stash cùng với thay đổi tracked:

```bash
git stash push -u -m "WIP: add report service"
```

Sau lệnh này:

- Thay đổi trong các tệp tracked được lưu vào stash.
- Tệp untracked được lưu cùng stash entry.
- Tệp ignored vẫn nằm trong working tree.

Ví dụ, nếu `src/main/NewService.java` là tệp mới chưa được add, `-u` giúp cất tệp đó để bạn có thể chuyển nhánh mà không phải commit một phần công việc dở dang.

Có thể dùng dạng dài tương đương:

```bash
git stash push --include-untracked -m "WIP: add report service"
```

`-u` không có nghĩa là đưa mọi tệp mới bất kể quy tắc ignore. Những tệp đã bị ignore không được bao gồm bởi tùy chọn này.

## 4. Dùng `-a` để stash cả tệp ignored

Tùy chọn `-a` là viết tắt của `--all`. Nó đưa cả tệp untracked và ignored vào stash:

```bash
git stash push -a -m "WIP: local build and config files"
```

Dạng dài:

```bash
git stash push --all -m "WIP: local build and config files"
```

Khác với `-u`, `-a` bao gồm các tệp bị ignore và dọn chúng khỏi working tree sau khi lưu. Điều này hữu ích khi bạn cần làm sạch toàn bộ khu vực làm việc, bao gồm cả file sinh tự động hoặc cấu hình local đang bị `.gitignore` bỏ qua.

Ví dụ:

| Tệp | Trạng thái | `stash push` | `stash push -u` | `stash push -a` |
|---|---|---|---|---|
| `src/main/App.java` đã sửa | Tracked | Có | Có | Có |
| `src/main/NewService.java` mới tạo | Untracked | Không | Có | Có |
| `build/output.log` bị ignore | Ignored | Không | Không | Có |

`-a` có phạm vi rộng hơn. Trước khi dùng, hãy xem `git status --short --ignored` để biết những tệp nào sẽ được đưa vào stash. Thư mục build lớn có thể làm stash tăng đáng kể; file cache hoặc dữ liệu sinh tự động có thể không cần lưu.

## 5. Cẩn trọng với tệp nhạy cảm và tệp sinh tự động

`.gitignore` thường được dùng để loại khỏi lịch sử commit các file như mật khẩu local, token, file cấu hình riêng, log, cache hoặc thư mục build. Dùng `-a` sẽ đưa các tệp ignored vào đối tượng stash trong repository local. Stash không mã hóa nội dung và không phải kho lưu trữ bí mật.

Trước khi chạy `git stash push -a`, hãy cân nhắc:

- Không đưa private key, mật khẩu, token hoặc bí mật không cần thiết vào stash.
- Kiểm tra dung lượng của thư mục build, cache và dữ liệu sinh tự động.
- Chỉ dùng `-a` khi thật sự cần giữ các tệp ignored để khôi phục sau đó.
- Nếu tệp ignored là dữ liệu có giá trị, bảo đảm có phương án lưu trữ phù hợp và được phép.

Đừng mặc định rằng tệp ignored có thể bị xóa an toàn. Tùy chọn `-a` dọn các tệp đó khỏi working tree sau khi stash; hãy hiểu phạm vi trước khi chạy.

## 6. Đặt tên và kiểm tra stash entry

Nên thêm thông điệp ngắn để nhận biết mục đích của mỗi stash:

```bash
git stash push -u -m "WIP: report endpoint"
git stash push -a -m "WIP: local config before branch switch"
```

Liệt kê các stash hiện có:

```bash
git stash list
```

Ví dụ:

```text
stash@{0}: On feature/report: WIP: local config before branch switch
stash@{1}: On main: WIP: report endpoint
```

`stash@{0}` là entry mới nhất tại thời điểm xem. Khi tạo stash khác hoặc xóa entry, chỉ số có thể thay đổi. Vì vậy, hãy đọc lại `git stash list` trước khi thao tác với một entry cụ thể.

Xem tóm tắt thay đổi:

```bash
git stash show --stat stash@{0}
```

Xem diff chi tiết:

```bash
git stash show --patch stash@{0}
```

Để xem thêm nội dung của các tệp untracked được lưu trong stash:

```bash
git stash show --include-untracked --stat stash@{0}
git stash show --include-untracked --patch stash@{0}
```

Với stash tạo bằng `-a`, hãy kiểm tra nội dung ignored đã được lưu bằng cách xem entry và xác minh tệp cụ thể sau khi khôi phục trong một working tree an toàn. Không in nội dung file bí mật ra terminal hoặc chia sẻ log kiểm tra nếu không cần thiết.

## 7. Khôi phục stash bằng apply hoặc pop

Có hai cách khôi phục phổ biến:

```bash
git stash apply stash@{0}
```

`apply` áp dụng nội dung stash trở lại working tree nhưng mặc định không cố khôi phục trạng thái staged ban đầu trong index; các thay đổi có thể xuất hiện dưới dạng chưa staged. Entry vẫn được giữ trong danh sách để bạn kiểm tra hoặc áp dụng lại khi cần.

```bash
git stash pop stash@{0}
```

`pop` áp dụng stash rồi xóa entry nếu áp dụng thành công. Nếu xảy ra xung đột hoặc thao tác áp dụng thất bại, Git thường giữ entry để bạn còn có thể thử lại sau khi xử lý.

Nếu cần khôi phục cả trạng thái staged đã lưu trong stash, dùng `--index`:

```bash
git stash apply --index stash@{0}
```

Tùy chọn này yêu cầu Git cố gắng khôi phục trạng thái index, gồm các thay đổi đã staged trước khi stash. Việc khôi phục có thể thất bại nếu nội dung hiện tại không còn tương thích.

Sau khi khôi phục, kiểm tra:

```bash
git status --short --ignored
```

Với stash có untracked hoặc ignored files, kiểm tra thêm các đường dẫn đã được khôi phục và xác nhận không ghi đè dữ liệu mới đang tồn tại.

## 8. Xử lý khi tệp untracked hoặc ignored đã tồn tại

Một stash có thể chứa tệp `src/main/NewService.java`. Trong lúc stash đang được cất, bạn hoặc một công cụ khác có thể tạo một tệp cùng đường dẫn trên nhánh hiện tại. Khi áp dụng stash, Git không thể tự ghi đè tệp đang tồn tại một cách an toàn và thao tác có thể thất bại hoặc cần xử lý thủ công.

Trước khi apply/pop, kiểm tra trạng thái và các đường dẫn có nguy cơ trùng. Nếu tệp hiện tại có giá trị, hãy lưu hoặc đổi vị trí nó theo quy trình phù hợp trước khi khôi phục. Không dùng lệnh dọn dẹp diện rộng như `git clean -fdx` chỉ để ép stash áp dụng; lệnh đó có thể xóa tệp untracked và ignored không nằm trong stash.

Nếu apply tạo xung đột ở các tệp tracked, giải quyết như một xung đột Git thông thường, xem xét cả nội dung hiện tại và nội dung stash. Sau khi xử lý, kiểm tra diff và test trước khi tiếp tục làm việc.

## 9. Tạo nhánh mới từ một stash

Nếu stash được tạo trên một nhánh cũ nhưng bạn muốn tiếp tục công việc ở nhánh riêng, có thể dùng:

```bash
git stash branch feature/report-wip stash@{0}
```

Git tạo và chuyển sang nhánh mới tại commit mà stash được tạo, sau đó áp dụng stash lên nhánh đó. Cách này thường giảm xung đột khi stash được tạo trên một nền khác với nhánh hiện tại. Nếu áp dụng thành công, entry được dùng sẽ được xóa khỏi danh sách stash.

Hãy kiểm tra `git status` sau khi tạo nhánh. Nếu cần giữ stash để dùng lại hoặc chưa chắc thao tác đã khôi phục đầy đủ, dùng `apply` trước và chỉ `drop` sau khi xác nhận kết quả.

## 10. Xóa stash sau khi xác nhận

Khi đã khôi phục và xác nhận công việc đầy đủ, bạn có thể xóa một entry cụ thể:

```bash
git stash drop stash@{0}
```

Lệnh `drop` xóa entry khỏi danh sách stash. Đọc `git stash list` ngay trước khi chạy vì chỉ số có thể đã thay đổi.

Lệnh sau xóa toàn bộ stash entry:

```bash
git stash clear
```

`clear` có phạm vi rộng và khó khôi phục hơn; chỉ dùng khi bạn đã kiểm tra và chắc chắn không còn stash nào cần giữ. Đừng xóa stash ngay sau khi `apply` nếu chưa kiểm tra file untracked/ignored đã trở lại đúng vị trí.

## 11. Ví dụ thực hành: chuyển nhánh khi có file mới và file ignored

Bạn đang làm trên `feature/report` với tình trạng:

- Sửa `src/main/ReportService.java` (tracked).
- Tạo `src/main/ReportMapper.java` (untracked).
- Có `build/generated/report-schema.json` bị ignore.

Nếu chỉ cần giữ thay đổi tracked và tệp mới, nhưng không cần giữ output build, dùng:

```bash
git status --short --ignored
git stash push -u -m "WIP: report mapper"
git status --short --ignored
git switch main
```

`ReportService.java` và `ReportMapper.java` được cất; file build ignored vẫn còn. Nếu mục tiêu là cất cả file build ignored để làm sạch working tree, sau khi xác nhận nó không chứa bí mật hoặc dữ liệu cần giữ riêng, dùng `-a`:

```bash
git stash push -a -m "WIP: report work and local generated files"
```

Khi quay lại nhánh tính năng:

```bash
git switch feature/report
git stash list
git stash apply stash@{0}
git status --short --ignored
```

Xem lại file đã khôi phục và chạy kiểm tra cần thiết. Nếu mọi thứ đầy đủ, xóa entry đã dùng:

```bash
git stash drop stash@{0}
```

Trong thực tế, hãy đọc `git stash list` trước khi chọn `stash@{0}` vì có thể có stash mới hơn được tạo trong lúc bạn làm việc ở nhánh khác.

## 12. Ghi nhớ

`git stash push` mặc định lưu thay đổi tracked. Dùng `-u` (`--include-untracked`) để lưu thêm tệp untracked; dùng `-a` (`--all`) để lưu cả untracked và ignored, đồng thời dọn các tệp đó khỏi working tree. Hãy kiểm tra phạm vi trước khi stash, đặt thông điệp dễ nhận biết, xem lại entry trước khi khôi phục và chỉ xóa stash sau khi đã xác nhận dữ liệu trở lại đầy đủ.
