# Sửa liên kết sau khi di chuyển thư mục bằng git worktree repair

Git worktree cho phép một repository có nhiều thư mục làm việc cùng lúc. Mỗi worktree có working tree riêng, có thể checkout branch khác nhau, trong khi chia sẻ object database và phần lớn metadata của repository. Cách tổ chức này rất tiện khi cần sửa lỗi khẩn cấp trong một thư mục riêng mà vẫn giữ nguyên công việc đang làm ở thư mục khác.

Khi di chuyển thủ công một thư mục worktree bằng File Explorer, `mv` hoặc công cụ quản lý tệp, các đường dẫn trong metadata có thể vẫn trỏ đến vị trí cũ. Git khi đó có thể báo worktree bị thiếu, không nhận ra thư mục mới hoặc không thể thao tác với worktree đã di chuyển. Lệnh `git worktree repair` cập nhật lại các liên kết quản trị để Git nhận đúng vị trí mới.

## 1. Worktree liên kết hoạt động như thế nào?

Một repository có thể có main worktree và nhiều linked worktree. Main worktree thường là thư mục được tạo khi clone hoặc init repository. Linked worktree được tạo thêm bằng `git worktree add`.

Ví dụ:

```text
project/                         # main worktree
├── .git/                        # common Git directory
├── src/
└── README.md

../project-hotfix/               # linked worktree
├── .git                         # file trỏ đến metadata riêng của worktree
├── src/
└── README.md

../project-feature/              # linked worktree
├── .git                         # file trỏ đến metadata riêng của worktree
├── src/
└── README.md
```

Khác với main worktree, `.git` trong linked worktree thường là một **tệp văn bản** chứa đường dẫn đến thư mục metadata riêng của worktree bên trong common Git directory. Metadata này liên kết ngược đến thư mục làm việc. Nhờ đó, Git biết mỗi thư mục đang checkout branch nào và dùng chung object database ở đâu.

Thông tin quản trị của các linked worktree thường nằm trong:

```text
.git/worktrees/<worktree-id>/
```

Trong đó có các tệp như `gitdir`, `HEAD`, `commondir` và dữ liệu liên quan đến trạng thái riêng của worktree. Đường dẫn trong các tệp này giúp Git kết nối thư mục làm việc với metadata tương ứng.

Khi di chuyển thư mục thủ công, filesystem đã thay đổi vị trí nhưng metadata có thể vẫn chứa đường dẫn cũ. `git worktree repair` đồng bộ lại các liên kết đó. Không nên tự sửa các tệp trong `.git/worktrees/` hoặc nội dung tệp `.git` bằng tay nếu chưa hiểu đầy đủ cấu trúc nội bộ.

## 2. Nhận biết khi nào cần dùng git worktree repair

Giả sử bạn đã tạo linked worktree:

```bash
git worktree add ../project-feature feature/login
```

Sau đó, bạn di chuyển thư mục `project-feature` sang ổ đĩa hoặc vị trí khác, ví dụ:

```text
Trước:  D:/workspace/project-feature
Sau:    E:/worktrees/project-feature
```

Git vẫn có thể lưu đường dẫn cũ trong metadata. Khi chạy:

```bash
git worktree list
```

worktree có thể được đánh dấu là `prunable`, hoặc Git có thể báo thư mục cũ không còn tồn tại. Khi truy cập thư mục mới, Git cũng có thể không nhận đúng repository nếu tệp `.git` bên trong vẫn trỏ đến metadata cũ.

Một số dấu hiệu khác:

- `git worktree list` hiển thị đường dẫn cũ dù thư mục đã được chuyển.
- Git báo không tìm thấy thư mục linked worktree hoặc metadata tương ứng.
- Thư mục mới còn tồn tại nhưng Git không nhận ra nó là linked worktree của repository.
- Một thao tác quản lý worktree thất bại vì đường dẫn trong metadata không còn đúng.

Nếu bạn chỉ đổi tên một tệp bên trong working tree, chuyển branch bằng `git switch`, hoặc tạo linked worktree mới bằng `git worktree add`, thông thường không cần `repair`. Lệnh này dành cho việc sửa liên kết sau khi **di chuyển thư mục worktree ở cấp filesystem**.

## 3. Kiểm tra danh sách worktree trước khi sửa

Từ một worktree còn hoạt động của repository, chạy:

```bash
git worktree list
```

Ví dụ:

```text
D:/workspace/project             abc1234 [main]
D:/workspace/project-feature     def5678 [feature/login] prunable
D:/workspace/project-hotfix      987abcd [hotfix/payment]
```

Output cho biết đường dẫn worktree, commit đang checkout, branch (nếu có) và trạng thái đặc biệt. `prunable` thường cho biết Git xem đăng ký worktree là có thể dọn vì thư mục liên quan không còn ở vị trí đã ghi nhận. Nếu bạn vừa di chuyển thư mục, đây có thể là dấu hiệu metadata chưa được cập nhật.

Để xem output dễ xử lý bằng script hoặc kiểm tra metadata, dùng:

```bash
git worktree list --porcelain
```

Ví dụ:

```text
worktree D:/workspace/project
HEAD abc1234...
branch refs/heads/main

worktree D:/workspace/project-feature
HEAD def5678...
branch refs/heads/feature/login
prunable
```

`--porcelain` hiển thị từng worktree thành một nhóm trường, giúp nhận diện rõ đường dẫn và branch. Ghi lại đường dẫn mới chính xác trước khi chạy repair. Nếu đường dẫn chứa dấu cách, đặt nó trong dấu nháy khi truyền vào lệnh.

## 4. Sửa linked worktree đã được di chuyển

Khi chỉ một linked worktree được di chuyển, hãy chạy `git worktree repair` từ main worktree hoặc một linked worktree khác vẫn còn ở vị trí cũ và hoạt động bình thường. Truyền vào đường dẫn **mới** của linked worktree cần sửa.

Ví dụ, linked worktree được chuyển từ `D:/workspace/project-feature` sang `E:/worktrees/project-feature`. Mở terminal tại main worktree rồi chạy:

```bash
git worktree repair "E:/worktrees/project-feature"
```

Git sẽ tìm linked worktree tại đường dẫn mới và cập nhật các tệp quản trị liên quan để liên kết giữa thư mục làm việc và common Git directory chính xác trở lại.

Nếu có nhiều linked worktree đã được di chuyển, có thể truyền nhiều đường dẫn trong một lần:

```bash
git worktree repair "E:/worktrees/project-feature" "E:/worktrees/project-hotfix"
```

Mỗi đối số là vị trí mới của một linked worktree. Hãy chắc chắn các đường dẫn này thực sự chứa worktree của repository đang sửa; không truyền thư mục dự án thông thường hoặc thư mục chưa được đăng ký làm linked worktree.

Sau khi repair, xác minh:

```bash
git worktree list --porcelain
git -C "E:/worktrees/project-feature" status
```

Đường dẫn trong danh sách phải là vị trí mới và lệnh `git status` từ thư mục đó phải nhận đúng repository cùng trạng thái working tree.

## 5. Sửa khi main worktree được di chuyển

Nếu bạn di chuyển **main worktree** (thư mục chứa common `.git` directory), metadata của linked worktree có thể vẫn trỏ đến vị trí main worktree cũ. Trong trường hợp này, hãy mở terminal tại vị trí mới của main worktree và chạy `git worktree repair` không kèm đường dẫn:

```bash
cd "E:/workspace/project"
git worktree repair
```

Lệnh chạy từ main worktree mới sẽ sửa các tệp quản trị của linked worktree để chúng tham chiếu đến common Git directory ở vị trí mới.

Ví dụ:

```text
Main worktree trước: D:/workspace/project
Main worktree sau:   E:/workspace/project
Linked worktree:     D:/workspace/project-feature
```

Sau khi di chuyển thư mục main từ `D:/workspace/project` sang `E:/workspace/project`, chạy repair trong thư mục `E:/workspace/project`. Các linked worktree vẫn ở vị trí cũ có thể tiếp tục được nhận diện sau khi liên kết metadata được cập nhật.

Nếu main worktree mới và một hoặc nhiều linked worktree cũng đã được di chuyển, chạy repair từ main worktree mới và truyền đường dẫn mới của từng linked worktree:

```bash
cd "E:/workspace/project"
git worktree repair "F:/worktrees/project-feature" "F:/worktrees/project-hotfix"
```

Sau đó kiểm tra lại toàn bộ danh sách bằng `git worktree list --porcelain` và xác minh từng thư mục mới bằng `git -C <path> status`.

## 6. Phân biệt repair với prune

`git worktree repair` và `git worktree prune` đều liên quan đến metadata worktree nhưng mục tiêu hoàn toàn khác nhau.

| Lệnh | Mục đích | Khi nên dùng |
|---|---|---|
| `git worktree repair [<path>...]` | Cập nhật liên kết quản trị sau khi worktree được di chuyển thủ công | Thư mục worktree vẫn tồn tại ở vị trí mới và bạn muốn tiếp tục sử dụng |
| `git worktree prune` | Xóa metadata đăng ký của worktree đã không còn tồn tại hoặc đã hết hạn theo quy tắc prune | Worktree thực sự bị xóa và bạn muốn dọn đăng ký cũ |
| `git worktree list` | Liệt kê worktree và trạng thái đăng ký | Kiểm tra trước và sau khi sửa |

Không dùng `prune` chỉ vì danh sách hiển thị `prunable` sau khi bạn di chuyển thư mục. Metadata đó có thể vẫn cần thiết để Git nhận ra worktree ở vị trí mới. Hãy chạy `repair` với đúng đường dẫn trước. Nếu bạn thực sự không còn cần worktree và thư mục đã bị xóa, khi đó mới cân nhắc `prune`.

Có thể xem trước những metadata mà prune sẽ loại bỏ bằng:

```bash
git worktree prune --dry-run --verbose
```

Lệnh này chỉ mô phỏng việc dọn metadata. Nếu kết quả chứa worktree bạn muốn giữ, dừng lại và kiểm tra đường dẫn hoặc chạy repair trước khi thực hiện prune thật.

## 7. Quy trình đầy đủ khi di chuyển worktree

Giả sử bạn chuyển linked worktree `feature/login` sang ổ đĩa khác. Quy trình có thể thực hiện như sau:

### Bước 1: Xác nhận repository và trạng thái worktree

Từ main worktree còn hoạt động:

```bash
git rev-parse --show-toplevel
git worktree list --porcelain
```

Ghi lại branch, commit và đường dẫn cũ của worktree cần di chuyển. Nếu thư mục có thay đổi chưa commit, giữ nguyên chúng; `repair` không nhằm mục đích lưu commit hoặc dọn nội dung làm việc.

### Bước 2: Di chuyển thư mục bằng công cụ filesystem

Ví dụ di chuyển:

```text
D:/workspace/project-feature
    -> E:/worktrees/project-feature
```

Di chuyển toàn bộ thư mục worktree, bao gồm tệp `.git` bên trong. Không chỉ sao chép riêng source code và bỏ tệp `.git`, vì tệp này là liên kết đến metadata quản trị của worktree.

### Bước 3: Repair từ một worktree còn hoạt động

```bash
git worktree repair "E:/worktrees/project-feature"
```

Nếu main worktree cũng đã di chuyển, chạy lệnh từ main worktree mới. Nếu cả main và linked worktree đều di chuyển, truyền các đường dẫn linked worktree mới như ví dụ ở phần trước.

### Bước 4: Xác minh liên kết và nội dung

```bash
git worktree list --porcelain
git -C "E:/worktrees/project-feature" status --short --branch
git -C "E:/worktrees/project-feature" rev-parse --show-toplevel
```

Kiểm tra đường dẫn, branch và trạng thái có đúng như trước khi di chuyển không. Nội dung source, commit hiện tại và các thay đổi chưa commit phải vẫn ở trong thư mục mới.

### Bước 5: Tiếp tục làm việc

Sau khi liên kết được sửa, có thể tiếp tục dùng các lệnh Git bình thường trong linked worktree:

```bash
git -C "E:/worktrees/project-feature" status
git -C "E:/worktrees/project-feature" log --oneline -5
```

Không cần tạo lại worktree bằng `git worktree add` nếu thư mục đã di chuyển vẫn chứa dữ liệu và metadata hợp lệ; tạo thêm một worktree mới có thể gây nhầm lẫn hoặc xung đột branch đang được checkout.

## 8. Các lỗi thường gặp khi repair

### Truyền đường dẫn cũ thay vì đường dẫn mới

`git worktree repair` cần biết vị trí hiện tại của thư mục đã di chuyển. Nếu truyền đường dẫn cũ, Git không thể tìm thấy `.git` file của linked worktree ở vị trí đó. Hãy kiểm tra đường dẫn trong File Explorer hoặc dùng lệnh filesystem trước khi chạy.

### Chạy lệnh từ một thư mục không thuộc repository

Nếu chạy repair từ thư mục không có quan hệ với repository, Git có thể báo không phải repository. Hãy chuyển đến main worktree hoặc một linked worktree còn hoạt động, rồi xác minh bằng:

```bash
git rev-parse --show-toplevel
```

### Di chuyển thiếu tệp .git

Linked worktree thường dùng tệp `.git` để trỏ đến metadata riêng. Nếu chỉ copy thư mục source và bỏ tệp này, `git worktree repair` không thể tự tái tạo mọi trạng thái làm việc bị bỏ lại. Hãy kiểm tra bản di chuyển có chứa tệp `.git` hay không và so sánh với bản sao lưu trước khi can thiệp metadata.

### Thư mục mới không phải worktree của repository này

Đường dẫn truyền vào phải là thư mục linked worktree đã di chuyển. Nếu bạn truyền nhầm một clone độc lập, một thư mục source được copy thủ công hoặc một repository khác, repair không thể biến nó thành linked worktree của repository hiện tại.

### Dùng prune trước khi repair

Nếu đăng ký worktree đã bị prune, Git có thể không còn metadata cần thiết để liên kết lại branch và trạng thái riêng của worktree. Khi phát hiện đường dẫn cũ không tồn tại nhưng thư mục mới vẫn có dữ liệu, hãy thử repair trước và tránh prune trong quá trình điều tra.

## 9. Kiểm tra metadata mà không chỉnh sửa thủ công

Để xác định main Git directory và common Git directory từ một worktree:

```bash
git rev-parse --git-dir
git rev-parse --git-common-dir
```

Trong main worktree, hai đường dẫn thường cùng trỏ đến thư mục `.git`. Trong linked worktree, `--git-dir` thường trỏ đến thư mục metadata riêng bên trong `.git/worktrees/<id>`, còn `--git-common-dir` trỏ đến common Git directory dùng chung.

Có thể đọc nội dung tệp `.git` trong linked worktree để hiểu liên kết:

```text
gitdir: D:/workspace/project/.git/worktrees/project-feature
```

Đường dẫn trong ví dụ là minh họa. Nếu main worktree đã di chuyển, đường dẫn này có thể vẫn là vị trí cũ trước khi repair. Dù có thể đọc để chẩn đoán, không nên chỉnh sửa trực tiếp tệp `.git`, `gitdir` hay `commondir`; dùng `git worktree repair` để Git cập nhật nhất quán các liên kết liên quan.

## 10. Những hiểu nhầm thường gặp

| Hiểu nhầm | Cách hiểu đúng |
|---|---|
| `git worktree repair` tạo lại source code bị thiếu | Lệnh sửa metadata và liên kết quản trị; nó không khôi phục các tệp đã mất khỏi filesystem |
| Chỉ cần chạy repair từ bất kỳ thư mục nào | Cần chạy từ main worktree hoặc một worktree còn hoạt động, tùy trường hợp di chuyển |
| Linked worktree chuyển chỗ thì phải xóa rồi add lại | Nếu thư mục mới còn nguyên metadata, repair có thể nối lại đăng ký hiện có |
| `prunable` luôn có nghĩa worktree không còn cần thiết | Có thể chỉ vì thư mục đã được chuyển mà metadata chưa cập nhật |
| `git worktree repair` và `git worktree prune` giống nhau | Repair cập nhật liên kết; prune xóa metadata đăng ký không còn được dùng |
| Repair làm thay đổi commit hoặc branch | Lệnh sửa liên kết quản trị, không phải thao tác tích hợp hoặc viết lại lịch sử |
| Có thể xóa tệp metadata cũ bằng tay để Git nhận đường dẫn mới | Nên để `git worktree repair` cập nhật các liên kết có liên quan |

## 11. Ghi nhớ

Khi di chuyển thư mục worktree bằng filesystem, metadata Git có thể vẫn giữ đường dẫn cũ. `git worktree repair` dùng để sửa các liên kết quản trị sau khi di chuyển:

- Nếu linked worktree di chuyển, chạy từ main worktree hoặc một worktree khác còn hoạt động và truyền đường dẫn mới.
- Nếu main worktree di chuyển, chạy repair từ vị trí mới của main worktree.
- Nếu cả main và linked worktree đều di chuyển, chạy từ main worktree mới và chỉ rõ các đường dẫn linked worktree mới.

Trước khi repair, kiểm tra `git worktree list --porcelain` và xác định đúng đường dẫn. Sau khi repair, kiểm tra lại danh sách cùng `git status` từ từng thư mục mới. Dùng `prune` chỉ khi muốn loại bỏ đăng ký worktree thực sự không còn sử dụng; không dùng nó để xử lý một worktree vừa được di chuyển.
