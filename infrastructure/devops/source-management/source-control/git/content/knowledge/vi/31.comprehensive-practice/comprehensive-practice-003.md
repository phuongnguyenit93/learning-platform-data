# Làm việc với hai bản clone để quan sát fetch, pull và nhánh phân kỳ

## Mục tiêu bài thực hành

Trong bài này, bạn sẽ mô phỏng hai thành viên cùng làm việc trên một repository bằng hai bản clone độc lập. Một repository bare đóng vai trò remote trung tâm để cả hai clone trao đổi commit.

Bài thực hành giúp bạn quan sát trực tiếp:

- Vì sao hai bản clone không tự biết thay đổi của nhau.
- `git fetch` tải commit và cập nhật remote-tracking branch nhưng không tích hợp vào branch hiện tại.
- `git pull` thực hiện fetch rồi tích hợp lịch sử bằng fast-forward, merge hoặc rebase tùy tùy chọn/cấu hình.
- Vì sao branch local có thể vừa ahead vừa behind sau khi hai người cùng commit.
- Khi nào `git pull --ff-only` thành công hoặc từ chối.
- Cách tích hợp nhánh phân kỳ bằng merge và rebase.
- Cách giải quyết conflict khi hai clone sửa cùng một dòng.
- Cách kiểm tra đồ thị commit để biết lịch sử đã được tích hợp đúng.

Toàn bộ thao tác được thực hiện trong thư mục lab mới. Không dùng repository công việc thật để thử các bước tạo conflict, merge hoặc rebase.

## Mô hình lab

Ta tạo một remote bare tên `central.git`, sau đó tạo hai bản clone là `clone-a` và `clone-b`.

~~~text
                    central.git
                   (bare remote)
                    /        \
                   /          \
                  v            v
             clone-a          clone-b
           Developer A      Developer B
~~~

`central.git` chỉ lưu Git object và refs, không có working tree để chỉnh sửa file trực tiếp. Hai thành viên làm việc trong hai thư mục clone riêng. Khi một người push, remote được cập nhật; clone còn lại chỉ biết thay đổi sau khi fetch hoặc pull.

Một repository `seed` được dùng một lần để tạo commit ban đầu cho remote. Sau khi hai clone được tạo, mọi tình huống cộng tác đều diễn ra giữa `clone-a`, `clone-b` và `central.git`.

## Chuẩn bị môi trường

Cần có Git cài đặt và có thể chạy từ terminal:

~~~bash
git --version
~~~

Các ví dụ khởi tạo dùng tùy chọn `--initial-branch=main`, có trong Git từ phiên bản 2.28. Nếu Git cũ hơn, hãy cập nhật Git hoặc tạo branch `main` theo cách tương ứng trước khi push commit đầu tiên.

Ví dụ bên dưới dùng PowerShell để tạo file, phù hợp với Windows. Các lệnh Git có thể chạy trong PowerShell, Git Bash, macOS hoặc Linux; nếu dùng shell khác, thay lệnh tạo file/thư mục theo shell đó.

Tạo một thư mục riêng cho lab và đi vào đó:

~~~powershell
New-Item -ItemType Directory -Force git-two-clones-lab | Out-Null
Set-Location git-two-clones-lab
~~~

Mọi đường dẫn trong bài được tính từ thư mục `git-two-clones-lab`.

## Bước 1: Tạo remote bare và commit ban đầu

Tạo remote bare:

~~~bash
git init --bare --initial-branch=main central.git
~~~

Tạo repository `seed` với branch `main`:

~~~bash
git init --initial-branch=main seed
~~~

Cấu hình danh tính local cho repository seed:

~~~bash
git -C seed config user.name "Lab Seed"
git -C seed config user.email "seed@example.test"
~~~

Tạo file ban đầu và commit:

~~~powershell
Set-Content -NoNewline seed/README.md "Project status: initialized"
~~~

~~~bash
git -C seed add README.md
git -C seed commit -m "chore: initialize demo project"
~~~

Kết nối seed tới remote bare và push branch `main`:

~~~bash
git -C seed remote add origin ../central.git
git -C seed push -u origin main
~~~

Kiểm tra remote có branch `main`:

~~~bash
git --git-dir=central.git branch --list
git --git-dir=central.git symbolic-ref HEAD
~~~

Kết quả mong đợi là branch `main` đã tồn tại và HEAD của bare repository tham chiếu tới `refs/heads/main`.

Nếu Git của bạn không hỗ trợ `git init --bare --initial-branch=main`, có thể tạo bare repository rồi đặt HEAD của nó:

~~~bash
git init --bare central.git
git --git-dir=central.git symbolic-ref HEAD refs/heads/main
~~~

Với cùng phiên bản Git cũ, tạo `seed` rồi chuyển sang nhánh orphan `main` trước commit đầu tiên:

~~~bash
git init seed
git -C seed checkout --orphan main
~~~

Sau đó cấu hình danh tính, tạo README, commit ban đầu và push như các bước tiếp theo.

## Bước 2: Tạo hai bản clone

Từ thư mục lab, clone remote hai lần:

~~~bash
git clone central.git clone-a
git clone central.git clone-b
~~~

Hai thư mục `clone-a` và `clone-b` là hai working copy độc lập. Mỗi clone có object database, branch local, index và working tree riêng. Chúng cùng cấu hình remote `origin` trỏ tới `central.git`.

Cấu hình danh tính cho từng clone:

~~~bash
git -C clone-a config user.name "Developer A"
git -C clone-a config user.email "developer-a@example.test"

git -C clone-b config user.name "Developer B"
git -C clone-b config user.email "developer-b@example.test"
~~~

Kiểm tra cả hai clone:

~~~bash
git -C clone-a status -sb
git -C clone-b status -sb

git -C clone-a remote -v
git -C clone-b remote -v

git -C clone-a branch -vv
git -C clone-b branch -vv
~~~

Cả hai clone cần đang ở branch `main`, working tree sạch và branch local theo dõi `origin/main`.

Kiểm tra commit ban đầu:

~~~bash
git -C clone-a log -1 --oneline --decorate
git -C clone-b log -1 --oneline --decorate
~~~

Hai clone phải có cùng commit ban đầu. Ghi lại mã commit đó để dễ đối chiếu khi cần.

## Bước 3: Quan sát fetch không tự tích hợp vào branch hiện tại

Trước tiên, Developer A tạo một file mới, commit và push:

~~~powershell
Set-Content -NoNewline clone-a/a-note.txt "Created by Developer A"
~~~

~~~bash
git -C clone-a add a-note.txt
git -C clone-a commit -m "docs: add note from developer A"
git -C clone-a push origin main
~~~

Lúc này `central.git` đã có commit mới. Tuy nhiên, `clone-b` chưa fetch nên remote-tracking ref `origin/main` trong clone B vẫn giữ mã commit cũ.

Kiểm tra trạng thái clone B trước fetch:

~~~bash
git -C clone-b status -sb
git -C clone-b rev-parse main
git -C clone-b rev-parse origin/main
~~~

Vì clone B chưa biết remote đã thay đổi, `git status` có thể vẫn báo branch đang up to date với `origin/main`. Đây là trạng thái so sánh với remote-tracking ref local đang lưu, không phải phép kiểm tra trực tiếp máy chủ ở mỗi lần chạy.

Thực hiện fetch:

~~~bash
git -C clone-b fetch origin
~~~

Fetch tải object còn thiếu và cập nhật remote-tracking ref `origin/main`. Nó không tự di chuyển branch local `main` và không cập nhật file trong working tree.

Kiểm tra lại:

~~~bash
git -C clone-b status -sb
git -C clone-b rev-parse main
git -C clone-b rev-parse origin/main
git -C clone-b log --oneline --decorate main..origin/main
~~~

Kết quả mong đợi:

- `main` vẫn trỏ tới commit cũ.
- `origin/main` trỏ tới commit mới từ Developer A.
- `git status -sb` báo branch local đang behind 1 commit.
- Lệnh `git log main..origin/main` liệt kê commit mà remote có nhưng branch local chưa có.

Bạn có thể xem thay đổi mà chưa tích hợp:

~~~bash
git -C clone-b diff --stat main..origin/main
git -C clone-b diff main..origin/main
~~~

Kiểm tra file `a-note.txt` chưa xuất hiện trong working tree clone B. Fetch chỉ cập nhật object và remote-tracking ref; file chỉ được cập nhật khi bạn tích hợp commit vào branch/working tree.

### Quan sát đồ thị sau fetch

~~~bash
git -C clone-b log --graph --oneline --decorate --all
~~~

Trước khi pull, đồ thị có thể được hình dung như sau:

~~~text
S---A  origin/main
|
main
~~~

Trong đó S là commit ban đầu, A là commit Developer A vừa push. `main` của clone B vẫn ở S, còn `origin/main` đã ở A.

Đây là điểm khác biệt cốt lõi: fetch làm mới thông tin về remote, còn branch hiện tại vẫn giữ nguyên.

## Bước 4: Dùng pull để cập nhật khi branch chỉ bị behind

Trong clone B, branch local chưa có commit riêng và chỉ cần nhận commit A. Đây là trường hợp fast-forward.

Chạy:

~~~bash
git -C clone-b pull --ff-only origin main
~~~

`git pull` thực hiện fetch rồi tích hợp kết quả vào branch hiện tại. Tùy chọn `--ff-only` yêu cầu cập nhật theo fast-forward; nếu branch đã phân kỳ, Git sẽ từ chối thay vì tự tạo merge commit hoặc rebase.

Kiểm tra:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
git -C clone-b show --stat --oneline HEAD
~~~

Kết quả mong đợi:

- Branch `main` của clone B tiến lên commit A.
- File `a-note.txt` xuất hiện trong working tree.
- `main` và `origin/main` trỏ cùng commit.
- Working tree sạch.

Đồ thị lúc này:

~~~text
S---A  main, origin/main
~~~

Fast-forward chỉ di chuyển branch local tới commit mới vì commit cũ là tổ tiên của commit mới. Không cần tạo merge commit.

### Tóm tắt quan sát fetch và pull

| Thao tác | Remote-tracking ref | Branch local | Working tree |
|---|---|---|---|
| Trước fetch | Có thể đã cũ | Không đổi | Không đổi |
| Sau `git fetch` | Được cập nhật | Không đổi | Không đổi |
| Sau `git pull --ff-only` khi chỉ behind | Được cập nhật | Fast-forward | Cập nhật theo commit mới |

## Bước 5: Tạo nhánh phân kỳ từ hai clone

Bây giờ hai clone đã đồng bộ ở cùng commit A. Ta sẽ để hai thành viên cùng tạo commit từ điểm chung đó.

Developer A tạo file riêng và push:

~~~powershell
Set-Content -NoNewline clone-a/from-a.txt "Work committed by Developer A"
~~~

~~~bash
git -C clone-a add from-a.txt
git -C clone-a commit -m "docs: add work from developer A"
git -C clone-a push origin main
~~~

Developer B tạo một file khác và chỉ commit local, chưa push:

~~~powershell
Set-Content -NoNewline clone-b/from-b.txt "Work committed by Developer B"
~~~

~~~bash
git -C clone-b add from-b.txt
git -C clone-b commit -m "docs: add work from developer B"
~~~

Lúc này hai clone có lịch sử khác nhau:

- `clone-a` có commit của A đã push lên remote.
- `clone-b` có commit của B nhưng chưa push.
- `origin/main` trong clone B chưa được fetch nên vẫn đang trỏ tới commit A trước đó.

Kiểm tra clone B trước fetch:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
~~~

Vì remote-tracking ref chưa được cập nhật, trạng thái có thể chỉ báo local ahead 1. Chưa thể nhìn thấy commit mới của A trong clone B qua `origin/main`.

Fetch remote:

~~~bash
git -C clone-b fetch origin
~~~

Kiểm tra lại:

~~~bash
git -C clone-b status -sb
git -C clone-b log --left-right --graph --oneline main...origin/main
git -C clone-b log --graph --oneline --decorate --all
~~~

Lúc này `git status -sb` mong đợi hiển thị `ahead 1, behind 1` so với upstream.

Ý nghĩa:

- **Ahead 1:** branch local `main` có một commit mà `origin/main` chưa có: commit của B.
- **Behind 1:** `origin/main` có một commit mà branch local `main` chưa có: commit của A.

Đồ thị phân kỳ:

~~~text
       A  origin/main
      /
S----+
      \
       B  main
~~~

S là commit chung. A và B đều được tạo từ S, nhưng không commit nào là tổ tiên của commit còn lại.

### Đọc các commit chỉ có ở mỗi phía

Lệnh:

~~~bash
git -C clone-b log --left-right --graph --oneline main...origin/main
~~~

Ký hiệu:

- `<` là commit chỉ reachable từ đối số bên trái (`main`).
- `>` là commit chỉ reachable từ đối số bên phải (`origin/main`).

Bạn sẽ thấy commit của B ở phía local và commit của A ở phía remote. Đây là cách nhanh để xác định hai phía đang đóng góp những commit nào trước khi tích hợp.

Có thể xem merge base:

~~~bash
git -C clone-b merge-base main origin/main
~~~

Kết quả phải là commit S, tức tổ tiên chung trước khi hai clone phân kỳ.

## Bước 6: Quan sát pull --ff-only từ chối nhánh phân kỳ

Khi branch local có commit riêng và remote cũng có commit riêng, fast-forward không thể đưa branch local tới remote mà không bỏ qua commit B.

Thử:

~~~bash
git -C clone-b pull --ff-only origin main
~~~

Git sẽ từ chối với thông báo tương tự:

~~~text
fatal: Not possible to fast-forward, aborting.
~~~

Đây là hành vi có chủ đích. `--ff-only` không tự tạo merge commit và không viết lại commit local. Nó giúp bạn nhận ra branch đang phân kỳ để lựa chọn cách tích hợp.

Kiểm tra lại:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
~~~

Hai commit A và B vẫn còn. Remote-tracking ref `origin/main` đã được fetch và branch local vẫn trỏ tới commit B.

Khi gặp tình huống này, hai cách tích hợp phổ biến là merge hoặc rebase. Lựa chọn phụ thuộc quy ước lịch sử của nhóm.

## Bước 7: Tích hợp nhánh phân kỳ bằng merge

Trong bài lab, ta chọn merge để giữ lại hai nhánh phát triển và tạo một merge commit.

Chạy trong clone B:

~~~bash
git -C clone-b pull --no-rebase --no-ff origin main
~~~

Ý nghĩa:

- `--no-rebase`: yêu cầu tích hợp theo merge.
- `--no-ff`: tạo merge commit khi tích hợp, giữ lại điểm nối của hai nhánh.
- `origin main`: lấy branch `main` từ remote `origin` làm nguồn tích hợp.

Hai thành viên đã thêm file khác nhau nên ví dụ này không phát sinh conflict. Git có thể tự kết hợp hai snapshot và tạo merge commit.

Kiểm tra:

~~~bash
git -C clone-b status -sb
git -C clone-b rev-list --parents -n 1 HEAD
git -C clone-b log --graph --oneline --decorate --all
~~~

Merge commit có hai parent:

1. Commit B trên branch local trước khi merge.
2. Commit A trên `origin/main` được tích hợp vào.

Đồ thị sau merge có dạng:

~~~text
       A --------\
      /           \
S---+              M  main
      \           /
       B --------/
origin/main -> A
~~~

Sau khi merge, `main` trỏ tới M; `origin/main` vẫn trỏ tới A cho đến khi B push merge commit.

Đẩy kết quả lên remote:

~~~bash
git -C clone-b push origin main
~~~

Bây giờ remote `main` trỏ tới merge commit M. Clone A chưa tự biết điều đó. Fetch và fast-forward clone A:

~~~bash
git -C clone-a fetch origin
git -C clone-a status -sb
git -C clone-a pull --ff-only origin main
~~~

Kiểm tra cả hai clone:

~~~bash
git -C clone-a status -sb
git -C clone-b status -sb
git -C clone-a log --graph --oneline --decorate --all
~~~

Hai clone phải đồng bộ ở merge commit M.

### Nếu muốn dùng merge trực tiếp thay cho pull

`git pull --no-rebase` về bản chất là fetch rồi merge. Bạn cũng có thể tách hai bước để quan sát rõ:

~~~bash
git -C clone-b fetch origin
git -C clone-b merge --no-ff origin/main
~~~

Cách tách này hữu ích khi muốn review đồ thị sau fetch trước khi tích hợp. Không chạy cả hai quy trình liên tiếp trên cùng một trạng thái vì có thể tạo merge trùng hoặc không còn gì để merge.

## Bước 8: Tạo conflict khi hai clone sửa cùng một dòng

Đến đây hai clone đã đồng bộ. Ta tạo một tình huống conflict có chủ đích bằng cách cho cả hai cùng sửa một dòng trong `README.md`.

Developer A sửa và push:

~~~powershell
Set-Content -NoNewline clone-a/README.md "Project status: updated by A"
~~~

~~~bash
git -C clone-a add README.md
git -C clone-a commit -m "docs: update project status from A"
git -C clone-a push origin main
~~~

Developer B chưa fetch commit của A. Trong clone B, sửa cùng dòng theo nội dung khác và commit local:

~~~powershell
Set-Content -NoNewline clone-b/README.md "Project status: updated by B"
~~~

~~~bash
git -C clone-b add README.md
git -C clone-b commit -m "docs: update project status from B"
~~~

Fetch và thử tích hợp bằng merge:

~~~bash
git -C clone-b fetch origin
git -C clone-b pull --no-rebase --no-ff origin main
~~~

Lần fetch riêng giúp bạn quan sát remote-tracking ref trước khi tích hợp. Lệnh pull vẫn fetch thêm một lần nữa; nếu remote không đổi trong khoảng thời gian đó thì không có commit mới nào được tải thêm.

Git không thể tự quyết định nên giữ nội dung của A hay B vì cả hai cùng thay đổi một dòng từ cùng phiên bản gốc. Pull dừng lại ở trạng thái conflict.

Kiểm tra:

~~~bash
git -C clone-b status
git -C clone-b diff --name-only --diff-filter=U
git -C clone-b diff --cc README.md
~~~

File `README.md` trong clone B sẽ có marker tương tự:

~~~text
<<<<<<< HEAD
Project status: updated by B
=======
Project status: updated by A
>>>>>>> origin/main
~~~

Ý nghĩa:

- `HEAD` là phiên bản trên branch local hiện tại của B.
- Phần sau dấu phân cách là phiên bản từ nhánh remote được merge vào.
- Các marker chỉ tồn tại trong working file khi conflict chưa được giải quyết; chúng không phải nội dung cần giữ trong file cuối.

### Giải quyết conflict

Mở `clone-b/README.md`, quyết định nội dung cuối cùng. Trong ví dụ, ta giữ thông tin từ cả hai người:

~~~powershell
Set-Content -NoNewline clone-b/README.md "Project status: updated by A and B"
~~~

Stage file đã giải quyết:

~~~bash
git -C clone-b add README.md
~~~

Xác nhận không còn unmerged path:

~~~bash
git -C clone-b diff --name-only --diff-filter=U
git -C clone-b status
git -C clone-b diff --cached
~~~

Nếu danh sách unmerged rỗng và nội dung staged đúng, hoàn tất merge commit:

~~~bash
git -C clone-b commit
~~~

Push merge commit:

~~~bash
git -C clone-b push origin main
~~~

Clone A cập nhật:

~~~bash
git -C clone-a pull --ff-only origin main
~~~

Kiểm tra file README và lịch sử ở cả hai clone. Merge commit vẫn giữ hai parent và kết quả cuối cùng chứa nội dung bạn đã chọn.

### Hủy merge nếu chưa muốn giải quyết

Nếu muốn dừng lần merge đang dang dở:

~~~bash
git -C clone-b merge --abort
~~~

Lệnh này đưa repository về trạng thái trước khi bắt đầu merge, trong giới hạn Git có thể khôi phục trạng thái đó. Hãy bắt đầu từ working tree sạch và lưu các thay đổi cần giữ trước khi thử merge.

Sau khi abort, kiểm tra:

~~~bash
git -C clone-b status
git -C clone-b log -1 --oneline --decorate
~~~

Không dùng `git reset --hard` để xử lý conflict theo phản xạ; lệnh đó có thể loại bỏ thay đổi local chưa được lưu.

## Bước 9: Tích hợp nhánh phân kỳ bằng rebase

Merge giữ lại hai nhánh và tạo merge commit. Rebase có cách khác: phát lại commit local trên nền commit mới từ remote, tạo lịch sử tuyến tính.

Ta tạo thêm một lần phân kỳ sau khi hai clone đã đồng bộ ở bước trước.

Developer A tạo commit mới trên main và push:

~~~powershell
Set-Content -NoNewline clone-a/from-a-rebase.txt "Remote work before rebase"
~~~

~~~bash
git -C clone-a add from-a-rebase.txt
git -C clone-a commit -m "docs: add remote work before rebase"
git -C clone-a push origin main
~~~

Developer B tạo commit local trên main nhưng chưa push:

~~~powershell
Set-Content -NoNewline clone-b/from-b-rebase.txt "Local work to replay"
~~~

~~~bash
git -C clone-b add from-b-rebase.txt
git -C clone-b commit -m "docs: add local work for rebase"
~~~

Tích hợp bằng pull rebase:

~~~bash
git -C clone-b pull --rebase origin main
~~~

Lệnh thực hiện fetch rồi phát lại commit local của B trên commit mới nhất từ remote. Kết quả là commit A nằm trước commit B mới được tạo lại.

Đồ thị trước rebase:

Trong hai sơ đồ sau, S đại diện cho commit chung hiện tại sau lần merge/conflict ở bước trước; A và B là hai commit mới được tạo từ điểm đó.

~~~text
       A  origin/main
      /
S----+
      \
       B  main
~~~

Đồ thị sau rebase:

~~~text
S---A---B'  main
    ^
    origin/main
~~~

`B'` là commit mới được tạo khi phát lại thay đổi của B. Nội dung thay đổi có thể giống commit cũ, nhưng parent và committer metadata có thể khác nên commit ID thường thay đổi.

Kiểm tra:

~~~bash
git -C clone-b status -sb
git -C clone-b log --graph --oneline --decorate --all
git -C clone-b show --no-patch --pretty=raw HEAD
~~~

Push branch đã rebase:

~~~bash
git -C clone-b push origin main
~~~

Vì commit B cũ chưa từng được push và nhánh remote chỉ có commit A, kết quả rebase là fast-forward từ remote tới B'. Không cần force push.

Clone A cập nhật:

~~~bash
git -C clone-a pull --ff-only origin main
~~~

### Nếu rebase gặp conflict

Khi commit đang được phát lại không áp dụng sạch lên base mới, Git dừng để giải quyết conflict.

Kiểm tra trạng thái:

~~~bash
git -C clone-b status
~~~

Sửa file, stage kết quả rồi tiếp tục:

~~~bash
git -C clone-b add README.md
git -C clone-b rebase --continue
~~~

Lặp lại nếu còn commit khác gây conflict. Nếu muốn hủy toàn bộ rebase đang diễn ra:

~~~bash
git -C clone-b rebase --abort
~~~

Không dùng `git commit` để hoàn tất một rebase đang dừng vì conflict; dùng `git rebase --continue`. `git commit` là bước thường dùng để hoàn tất merge conflict, còn rebase có quy trình tiếp tục riêng.

### Chọn merge hay rebase?

| Tiêu chí | Merge | Rebase |
|---|---|---|
| Lịch sử | Giữ nhánh phân kỳ và tạo merge commit | Phát lại commit trên base mới, thường tuyến tính |
| Commit local | Giữ nguyên commit gốc | Tạo commit mới cho phần được phát lại |
| Dễ quan sát lịch sử cộng tác | Thấy rõ điểm hợp nhất | Lịch sử gọn hơn, ít merge commit |
| Conflict | Giải quyết trong lần merge | Có thể gặp ở từng commit được phát lại |
| Phù hợp | Nhánh chia sẻ hoặc nhóm muốn giữ lịch sử merge | Nhánh cá nhân chưa chia sẻ, nhóm yêu cầu lịch sử tuyến tính |

Không rebase các commit đã được người khác sử dụng nếu chưa phối hợp. Rebase viết lại commit và có thể buộc các thành viên khác phải xử lý lịch sử đã thay đổi.

## Hiểu trạng thái ahead và behind

`git status -sb` so sánh branch local với upstream/remote-tracking branch mà branch đang theo dõi.

| Trạng thái | Ý nghĩa |
|---|---|
| up to date | Local và upstream đang trỏ cùng commit theo thông tin local hiện có |
| ahead 1 | Local có một commit mà upstream chưa có |
| behind 1 | Upstream có một commit mà local chưa có |
| ahead 2, behind 3 | Hai phía có lịch sử riêng; local có 2 commit riêng và upstream có 3 commit riêng |
| không có upstream | Git không có nhánh theo dõi để tính ahead/behind |

Điểm cần nhớ: trạng thái ahead/behind chỉ chính xác theo remote-tracking ref local gần nhất. Nếu chưa fetch, `origin/main` có thể cũ và Git chưa biết remote đã nhận commit mới.

Kiểm tra upstream:

~~~bash
git branch -vv
git status -sb
~~~

Kiểm tra commit chỉ có ở local và remote sau khi fetch:

~~~bash
git log --left-right --oneline main...origin/main
~~~

## Phân biệt fetch, pull, merge và rebase

| Lệnh | Tác dụng chính | Tự cập nhật working tree? |
|---|---|---|
| `git fetch origin` | Lấy object và cập nhật remote-tracking refs | Không |
| `git pull --ff-only` | Fetch rồi chỉ tích hợp nếu fast-forward được | Có nếu branch tiến lên |
| `git pull --no-rebase` | Fetch rồi merge | Có; có thể dừng ở conflict |
| `git pull --rebase` | Fetch rồi rebase commit local | Có; có thể dừng ở conflict |
| `git merge origin/main` | Tích hợp remote-tracking branch vào branch hiện tại | Có; có thể dừng ở conflict |
| `git rebase origin/main` | Phát lại commit local trên base remote | Có; có thể dừng ở conflict |

Một GUI có thể đặt tên các thao tác là Sync, Update, Pull, Rebase hoặc Integrate. Trước khi bấm, hãy xác định công cụ đang fetch, merge hay rebase.

## Cấu hình chiến lược pull

Nếu chạy `git pull` mà Git báo cần chỉ định cách xử lý nhánh phân kỳ, có thể chọn chiến lược rõ ràng ngay trên lệnh:

~~~bash
git pull --ff-only
git pull --no-rebase
git pull --rebase
~~~

Hoặc cấu hình mặc định theo quy ước cá nhân/repository:

~~~bash
# Mặc định pull theo merge
git config --local pull.rebase false

# Hoặc mặc định pull theo rebase
git config --local pull.rebase true

# Chỉ cho phép fast-forward
git config --local pull.ff only
~~~

Đây là các lựa chọn thay thế nhau theo chính sách mong muốn; không cần đặt cả ba một cách máy móc. Kiểm tra cấu hình có hiệu lực và nguồn cấu hình:

~~~bash
git config --show-origin --show-scope --get pull.rebase
git config --show-origin --show-scope --get pull.ff
~~~

Trong lab, nên dùng tùy chọn tường minh trên từng lệnh để kết quả dễ dự đoán và không phụ thuộc cấu hình global của máy.

## Xử lý các tình huống thường gặp

| Hiện tượng | Nguyên nhân có thể | Cách kiểm tra và xử lý |
|---|---|---|
| Clone B không thấy commit A vừa push | Chưa fetch, remote-tracking ref còn cũ | Chạy `git fetch origin` rồi xem `git log --all` |
| `git status` vẫn báo up to date dù remote đã có commit mới | Upstream local chưa được cập nhật | Fetch trước khi đọc ahead/behind |
| `pull --ff-only` từ chối | Branch local và remote đã phân kỳ | Xem graph rồi chọn merge hoặc rebase |
| Push bị non-fast-forward | Remote có commit mà local chưa tích hợp | Fetch, tích hợp lịch sử rồi push |
| Pull dừng ở conflict | Hai phía sửa cùng vùng hoặc có thay đổi không thể tự kết hợp | Sửa file, stage, rồi commit hoặc `rebase --continue` theo thao tác |
| Không thấy ahead/behind | Branch chưa cấu hình upstream | Kiểm tra `git branch -vv`, thiết lập upstream nếu cần |
| Pull báo cần chọn strategy | Chưa có cấu hình hoặc hai nhánh phân kỳ | Dùng `--ff-only`, `--no-rebase` hoặc `--rebase` tường minh |
| Authentication failed | Credential hoặc quyền truy cập remote không hợp lệ | Kiểm tra remote URL, SSH key hoặc credential manager |
| File cục bộ sẽ bị ghi đè khi pull | Working tree có thay đổi xung đột với nội dung cần checkout | Commit/stash thay đổi cần giữ rồi thử lại |

### Kiểm tra nhanh khi không chắc trạng thái

Chạy các lệnh sau trước khi quyết định pull, merge hoặc rebase:

~~~bash
git status -sb
git branch -vv
git remote -v
git fetch origin
git status -sb
git log --graph --oneline --decorate --all
git log --left-right --oneline main...origin/main
~~~

## Bài tập tự kiểm tra

### Bài 1: Fetch có làm branch local tiến lên không?

1. Tạo commit trong clone A và push.
2. Chạy `git status -sb` trong clone B trước fetch.
3. Chạy `git fetch origin`.
4. So sánh `git rev-parse main` và `git rev-parse origin/main`.

Kết quả cần giải thích: fetch cập nhật remote-tracking ref, còn branch local vẫn giữ commit cũ.

### Bài 2: Khi nào pull fast-forward thành công?

1. Để clone B không có commit local riêng.
2. Push một commit mới từ clone A.
3. Chạy `git pull --ff-only origin main` trong clone B.

Kết quả cần giải thích: branch local có thể tiến thẳng tới commit remote vì commit cũ là tổ tiên của commit mới.

### Bài 3: Vì sao branch vừa ahead vừa behind?

1. Đồng bộ hai clone.
2. Tạo và commit một thay đổi trong clone A rồi push.
3. Tạo và commit một thay đổi khác trong clone B nhưng chưa push.
4. Fetch trong clone B.
5. Đọc `git status -sb` và `git log --left-right`.

Kết quả cần giải thích: mỗi phía có commit riêng được tạo từ cùng một tổ tiên.

### Bài 4: So sánh merge và rebase

Từ một trạng thái phân kỳ đã sao lưu:

1. Tích hợp bằng merge và xem số parent của commit mới.
2. Tạo lại trạng thái phân kỳ trong một lab khác.
3. Tích hợp bằng rebase và xem graph.
4. So sánh commit ID trước và sau rebase.

Kết quả cần giải thích: merge tạo điểm nối có nhiều parent; rebase phát lại commit và thường tạo ID mới.

### Bài 5: Giải quyết conflict

1. Cho cả hai clone sửa cùng một dòng trong README.
2. Commit ở cả hai phía, push một phía.
3. Pull ở phía còn lại để tạo conflict.
4. Kết hợp nội dung hai phía, stage và hoàn tất merge.
5. Push kết quả rồi cập nhật clone còn lại.

Kết quả cần giải thích: Git cần người dùng quyết định nội dung cuối cùng khi không thể tự kết hợp thay đổi.

## Checklist hoàn thành lab

- [ ] Đã tạo bare remote `central.git`.
- [ ] Đã tạo hai clone `clone-a` và `clone-b`.
- [ ] Đã xác nhận hai clone bắt đầu từ cùng commit.
- [ ] Đã quan sát trạng thái remote-tracking ref trước và sau fetch.
- [ ] Đã xác minh fetch không tự cập nhật branch local hoặc working tree.
- [ ] Đã dùng pull fast-forward để cập nhật clone đang behind.
- [ ] Đã tạo commit độc lập ở hai clone.
- [ ] Đã quan sát trạng thái ahead/behind sau fetch.
- [ ] Đã thấy `pull --ff-only` từ chối khi branch phân kỳ.
- [ ] Đã tích hợp một lần bằng merge và kiểm tra hai parent.
- [ ] Đã giải quyết conflict khi hai clone sửa cùng một dòng.
- [ ] Đã tích hợp một lần bằng rebase và quan sát commit được tạo lại.
- [ ] Đã push kết quả và cập nhật clone còn lại.
- [ ] Đã kiểm tra graph và xác nhận hai clone đồng bộ.

## Ghi nhớ

Hai bản clone có working tree, branch và remote-tracking refs độc lập. Khi một clone push, clone còn lại không tự thay đổi. `git fetch` cập nhật object và thông tin remote-tracking nhưng giữ nguyên branch hiện tại; `git pull` fetch rồi tích hợp bằng fast-forward, merge hoặc rebase. Khi cả hai clone cùng commit từ một tổ tiên, branch sẽ phân kỳ và có thể hiện ahead/behind sau fetch. `--ff-only` từ chối trạng thái đó để bạn chủ động chọn merge hoặc rebase. Hãy quan sát `git status -sb`, `git log --graph` và `git log --left-right` trước khi tích hợp, xử lý conflict theo đúng thao tác đang chạy, rồi push và cập nhật clone còn lại.

