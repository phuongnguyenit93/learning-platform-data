# Bảo trì định kỳ bằng `git maintenance`

Khi repository hoạt động lâu ngày, Git có thể tích lũy nhiều loose object, pack file nhỏ, ref và dữ liệu lịch sử cần được tối ưu. Điều này có thể làm một số thao tác như đọc log, tìm merge base, fetch hoặc kiểm tra object chậm hơn. Git cung cấp **`git maintenance`** để chạy các công việc bảo trì theo từng nhiệm vụ, có thể chạy thủ công hoặc lên lịch nền.

`git maintenance` giúp tổ chức việc cập nhật commit-graph, prefetch dữ liệu từ remote, đóng gói loose object và sắp xếp pack file. Nó cũng có thể chạy tác vụ `gc` theo cấu hình. Hiểu từng task giúp chọn đúng công việc cần làm, theo dõi tác động và tránh xóa nhầm object đang cần phục hồi.

Trong module SOURCE_CONTROL_GIT, bảo trì định kỳ là một phần của việc giữ repository khỏe mạnh khi cộng tác lâu dài. Bài này tập trung vào cách dùng `git maintenance`, phân biệt nó với `git gc`, kiểm tra kết quả và thiết lập lịch chạy phù hợp.

## 1. Vì sao repository cần bảo trì?

Git lưu dữ liệu trong object database. Khi commit, fetch, merge hoặc thao tác khác, Git tạo thêm object và cập nhật ref. Theo thời gian, repository có thể phát sinh:

- Nhiều **loose object** nằm riêng lẻ trong object database.
- Nhiều **pack file** nhỏ do fetch, repack hoặc các đợt cập nhật khác nhau.
- Commit graph cần được cập nhật để tăng tốc duyệt lịch sử.
- Ref ở dạng loose cần được đóng gói.
- Dữ liệu từ remote chưa được tải về local dù sắp cần cho công việc.
- Object không còn reachable sau reset, rebase hoặc xóa branch; một số object sẽ được giữ một thời gian trước khi có thể prune.

Những yếu tố này không nhất thiết làm repository hỏng. Chúng có thể chỉ làm tăng dung lượng hoặc giảm hiệu năng. Bảo trì giúp tổ chức lại dữ liệu để Git truy cập hiệu quả hơn.

### 1.1. Loose object và pack file

Khi Git tạo object, object có thể ban đầu được lưu dưới dạng loose object. Nhiều loose object có thể được gom vào pack file để giảm số lượng file và tận dụng nén delta.

Pack file thường đi kèm index file `.idx` giúp Git tìm object trong pack. Repository có nhiều pack nhỏ có thể tốn thêm công sức tìm kiếm và quản lý. Các tác vụ bảo trì có thể gom và sắp xếp chúng lại.

### 1.2. Commit graph và multi-pack-index

Commit graph là dữ liệu tăng tốc việc duyệt quan hệ commit, chẳng hạn ancestry và lịch sử. Multi-pack-index (MIDX) là chỉ mục giúp tìm object qua nhiều pack file mà không cần xử lý từng index pack theo cách kém hiệu quả.

Đây là dữ liệu hỗ trợ hiệu năng. Commit và object gốc vẫn nằm trong object database; tạo hoặc cập nhật các chỉ mục này không thay đổi nội dung commit.

### 1.3. Bảo trì không thay thế backup

Maintenance là công việc tối ưu và dọn dẹp repository. Nó không phải công cụ sao lưu và không đảm bảo phục hồi mọi thay đổi chưa commit. Trước khi xử lý repository đang có sự cố, hãy bảo vệ working tree, index, refs và Git metadata cần thiết.

Nếu đang điều tra commit bị mất hoặc object unreachable, không vội chạy tác vụ có thể prune object. Hãy tìm commit bằng reflog/fsck và tạo ref cứu hộ trước khi dọn dẹp.

## 2. `git maintenance` hoạt động như thế nào?

`git maintenance` chia công việc bảo trì thành các task nhỏ. Có thể chạy một task cụ thể, chạy các task được cấu hình hoặc để scheduler chạy định kỳ.

Các lệnh thường dùng:

```bash
# Chạy các task được cấu hình
git maintenance run

# Chạy khi Git xác định có ngưỡng cần bảo trì
git maintenance run --auto

# Chạy riêng một task
git maintenance run --task=commit-graph

# Xem trợ giúp và các tùy chọn của phiên bản Git hiện tại
git maintenance run --help
```

`git maintenance run` không có nghĩa là luôn chạy mọi task có thể có. Tập task phụ thuộc `maintenance.strategy`, cấu hình `maintenance.<task>.enabled`, lịch chạy và tùy chọn truyền vào. Nếu chỉ định `--task=<task>`, Git chạy các task được nêu theo thứ tự và không dựa vào cờ enabled để chọn chúng. Dùng `git config --show-origin --get-regexp '^maintenance\.'` để xem cấu hình thực tế.

Trong Git hiện đại, strategy mặc định cho bảo trì thủ công có thể là `geometric`, còn lịch nền chưa được cấu hình strategy thường không chạy task. Khi đăng ký repository bằng `register` hoặc `start`, Git đặt `incremental` nếu chưa có strategy. Vì mặc định và strategy có thể khác giữa phiên bản, hãy xem giá trị `maintenance.strategy` thực tế.

### 2.1. `--auto` và ngưỡng bảo trì

```bash
git maintenance run --auto
```

Tùy chọn `--auto` yêu cầu Git chỉ thực hiện bảo trì khi các điều kiện/ngưỡng tự động tương ứng được đáp ứng. Đây là cơ chế phù hợp để gọi từ script hoặc sau một số thao tác Git mà không bắt buộc chạy toàn bộ bảo trì mỗi lần.

Ngưỡng cụ thể có thể phụ thuộc task và cấu hình Git. Không nên coi `--auto` là lịch chạy nền hay cam kết rằng mọi task đều được chạy. Nếu cần lịch rõ ràng, cấu hình schedule và dùng scheduler.

### 2.2. Chạy task theo lịch

Git hỗ trợ các tần suất `hourly`, `daily` và `weekly` cho những task có lịch tương ứng:

```bash
git maintenance run --schedule=hourly
git maintenance run --schedule=daily
git maintenance run --schedule=weekly
```

Lệnh chỉ chạy những task được cấu hình cho tần suất được chọn. Giá trị hợp lệ của `maintenance.<task>.schedule` là `hourly`, `daily` hoặc `weekly`; nếu chưa cấu hình lịch cho task, việc gọi `--schedule` không tự động biến mọi task thành task của lịch đó. `--auto` và `--schedule` không dùng cùng nhau.

## 3. Các maintenance task thường gặp

Git có nhiều task chuyên biệt. Tên và hỗ trợ cụ thể có thể phụ thuộc phiên bản Git; xem `git maintenance run --help` và tài liệu `git-maintenance` trên máy đang dùng.

| Task | Công việc chính | Lợi ích |
|---|---|---|
| `commit-graph` | Ghi/cập nhật commit-graph từ các commit reachable. | Tăng tốc một số thao tác duyệt lịch sử và ancestry. |
| `prefetch` | Fetch dữ liệu từ remote vào namespace prefetch. | Chuẩn bị commit/object từ xa trước khi người dùng cần. |
| `loose-objects` | Gom loose object thành pack và dọn bản loose trùng khi phù hợp. | Giảm số file object riêng lẻ. |
| `incremental-repack` | Tổ chức lại pack file theo chiến lược repack tăng dần, thường kết hợp MIDX. | Giảm số pack nhỏ và cải thiện truy cập object. |
| `pack-refs` | Đóng gói các ref phù hợp vào `packed-refs`. | Giảm số file ref riêng lẻ. |
| `reflog-expire` | Xóa các entry reflog đã quá ngưỡng hết hạn. | Giảm dữ liệu reflog cũ; có thể làm mất một dấu vết phục hồi đã hết hạn. |
| `rerere-gc` | Dọn các mục cũ trong cache `rerere` lưu kết quả giải quyết conflict. | Giảm dữ liệu cache không còn cần thiết. |
| `worktree-prune` | Xóa metadata của linked worktree đã stale hoặc hỏng. | Dọn các đăng ký worktree không còn hợp lệ. |
| `gc` | Chạy garbage collection theo cấu hình Git. | Thực hiện các công việc tổng hợp như repack và prune object đã hết thời hạn giữ. |

Không phải mọi phiên bản hoặc mọi chiến lược đều bật tất cả task ở cùng lịch. Hãy kiểm tra cấu hình hiện tại thay vì giả định danh sách task đang chạy.

### 3.1. Task `commit-graph`

```bash
git maintenance run --task=commit-graph
```

Task này cập nhật commit-graph cho các commit reachable. Commit graph giúp Git tránh phải đọc và phân tích nhiều commit object chỉ để xác định quan hệ cha hoặc tính toán ancestry.

Có thể kiểm tra dữ liệu commit-graph:

```bash
git commit-graph verify
```

Commit graph là dữ liệu tăng tốc, không phải lịch sử độc lập. Nếu thiếu hoặc cần xây dựng lại, Git vẫn có thể đọc commit object gốc, nhưng thao tác có thể chậm hơn.

### 3.2. Task `prefetch`

```bash
git maintenance run --task=prefetch
```

Prefetch tải thông tin/object từ các remote được cấu hình và lưu ref vào namespace `refs/prefetch/`. Nó giúp chuẩn bị dữ liệu từ xa cho lần làm việc sau.

Prefetch không có nghĩa là merge hoặc pull thay đổi vào branch đang làm việc. Nó không tự sửa working tree và không nên được hiểu là đã tích hợp code mới vào branch local.

Task này cần mạng và credential truy cập remote. Prefetch ghi ref vào `refs/prefetch/`; nó không cập nhật remote-tracking branch thông thường và không cập nhật tag. Trong môi trường offline, prefetch có thể thất bại hoặc không có dữ liệu mới để tải. Nếu repository có nhiều remote hoặc nhiều branch, prefetch cũng có thể tiêu tốn bandwidth và dung lượng. Có thể loại một remote khỏi prefetch bằng `remote.<name>.skipFetchAll`.

### 3.3. Task `loose-objects`

```bash
git maintenance run --task=loose-objects
```

Task này gom loose object thành pack file và loại bỏ bản loose trùng khi phù hợp. Mục tiêu là giảm số lượng file riêng lẻ trong object database.

Việc đóng gói không làm thay đổi OID của object. Commit và blob vẫn giữ cùng nội dung logic; cách lưu vật lý được tổ chức lại.

### 3.4. Task `incremental-repack`

```bash
git maintenance run --task=incremental-repack
```

Task này sắp xếp lại pack file theo hướng tăng dần, thay vì luôn repack toàn bộ object database thành một pack lớn. Git có thể dùng multi-pack-index và chiến lược geometric để giảm số pack nhỏ theo từng đợt.

Với repository lớn, repack tăng dần giúp phân bổ chi phí bảo trì qua nhiều lần chạy. Nó không có nghĩa mọi object sẽ được viết lại trong một lần.

Về cơ bản, task này dùng MIDX để xác định pack có thể loại khỏi chỉ mục, sau đó repack một nhóm pack nhỏ hơn thành pack lớn hơn và cập nhật MIDX. Các bước được chia thành nhiều lần chạy để giảm thời gian mỗi đợt.

### 3.5. Task `pack-refs`

```bash
git maintenance run --task=pack-refs
```

Git có thể lưu ref dưới dạng file riêng lẻ hoặc gom nhiều ref vào `packed-refs`. Task này giúp giảm số file ref rời rạc. Branch và tag vẫn được truy cập bằng tên như trước; thay đổi chủ yếu nằm ở cách lưu ref trên đĩa.

### 3.6. Task `gc`

```bash
git maintenance run --task=gc
```

Task `gc` gọi quy trình garbage collection của Git theo cấu hình. `git gc` có thể repack object, cập nhật dữ liệu phụ trợ và loại bỏ object unreachable đã quá thời hạn giữ.

Đây là task cần thận trọng hơn khi repository đang được dùng để điều tra hoặc phục hồi dữ liệu. Một commit bị reset khỏi branch có thể vẫn còn trong reflog/object database trong một thời gian; sau khi hết thời hạn và được prune, việc phục hồi có thể khó hoặc không còn khả thi.

Task `gc` có thể gom toàn bộ object vào một pack lớn và tốn thời gian với repository lớn. Không nên bật đồng thời task `gc` và `loose-objects`: quy trình GC có thể tạo loose object unreachable để một lượt loose-objects sau đó dọn tiếp, nên hai task này không được khuyến nghị chạy cùng lúc.

Mỗi `git maintenance run` lấy khóa trên object database để ngăn hai tiến trình maintenance chạy đồng thời trên cùng repository. Tuy nhiên, `git gc` gọi trực tiếp không dùng cùng cơ chế khóa như `git maintenance run`. Tránh chạy `git gc` song song với maintenance; nếu cần GC, ưu tiên `git maintenance run --task=gc` để nằm trong cơ chế khóa của maintenance.

### 3.7. Các task dọn dữ liệu phụ trợ

```bash
git maintenance run --task=reflog-expire
git maintenance run --task=rerere-gc
git maintenance run --task=worktree-prune
```

- `reflog-expire` loại các entry reflog đã quá ngưỡng hết hạn. Nếu đang phục hồi commit, hãy tạo branch/tag cứu hộ trước khi để reflog bị expire.
- `rerere-gc` dọn cache cũ của cơ chế `rerere` (reuse recorded resolution), nơi Git ghi nhớ cách giải quyết conflict.
- `worktree-prune` dọn metadata của linked worktree không còn tồn tại hoặc không còn hợp lệ. Trước khi chạy, kiểm tra các worktree mà nhóm vẫn cần.

Các task này có thể không xuất hiện hoặc có hành vi khác ở phiên bản Git cũ. Xem `git maintenance run --help` để xác nhận task được hỗ trợ.

## 4. Chạy bảo trì thủ công

### 4.1. Kiểm tra trước khi chạy

Trước khi bảo trì một repository, xem trạng thái và cấu hình:

```bash
git status --short --branch
git count-objects -vH
git config --show-origin --get-regexp '^maintenance\.'
```

- `git status` giúp phát hiện thay đổi đang làm và trạng thái merge/rebase.
- `git count-objects -vH` cho biết số loose object, số pack và dung lượng ước tính.
- `git config` cho biết các task, schedule hoặc strategy đã cấu hình ở đâu.

Bảo trì thường không làm thay đổi nội dung working tree, nhưng nếu đang xử lý sự cố, có object unreachable hoặc repository đang có thao tác ghi khác, hãy sao lưu và hiểu trạng thái trước khi chạy task dọn dẹp.

### 4.2. Chạy các task cần thiết

Ví dụ repository có nhiều loose object và commit graph cũ:

```bash
git maintenance run --task=loose-objects
git maintenance run --task=commit-graph
```

Nếu có nhiều pack nhỏ, có thể chạy incremental repack:

```bash
git maintenance run --task=incremental-repack
```

Không cần chạy mọi task theo thói quen sau mỗi commit. Chọn task dựa trên tình trạng repository và cấu hình nhóm.

### 4.3. Xác minh sau bảo trì

```bash
git count-objects -vH
git commit-graph verify
git multi-pack-index verify
git fsck --full
git status --short --branch
```

Một số lệnh verify chỉ có ý nghĩa nếu repository có commit-graph hoặc multi-pack-index tương ứng. Nếu chưa có file chỉ mục, Git có thể báo không tìm thấy dữ liệu để kiểm tra; điều đó không tự chứng minh object database bị hỏng.

So sánh `git count-objects -vH` trước và sau để quan sát loose object, pack count và dung lượng. Không kỳ vọng mọi con số đều giảm: prefetch có thể tải thêm object; repack có thể tạm cần thêm dung lượng; commit graph/MIDX tạo thêm file chỉ mục.

## 5. Thiết lập bảo trì nền

Với repository được dùng thường xuyên, có thể đăng ký repository để Git quản lý bảo trì định kỳ.

### 5.1. Đăng ký repository

```bash
git maintenance register
```

Lệnh này đăng ký repository hiện tại vào danh sách repository được bảo trì nền của người dùng. Danh sách đăng ký thường được lưu trong cấu hình global dưới khóa nhiều giá trị `maintenance.repo`.

Nếu `maintenance.strategy` chưa được đặt, `register` đặt nó thành `incremental`. Chiến lược này ưu tiên các công việc nhỏ, an toàn cho chạy nền: `prefetch` và `commit-graph` theo giờ; `loose-objects` và `incremental-repack` theo ngày; `pack-refs` theo tuần; không lên lịch task `gc`. `register` cũng đặt `maintenance.auto=false` trong cấu hình local để tắt foreground auto-maintenance của repository. Thiết lập này vẫn còn sau khi `unregister`, nên hãy kiểm tra trước khi thay đổi cách bảo trì.

`maintenance.auto` điều khiển việc một số lệnh Git tự gọi `git maintenance run --auto` sau khi ghi dữ liệu; mặc định là `true`. Vì vậy, sau `unregister`, nếu muốn khôi phục hành vi auto-maintenance trước đó, cần xem và đặt lại giá trị này có chủ đích, ví dụ:

```bash
git config --local maintenance.auto true
```

Kiểm tra danh sách:

```bash
git config --global --get-all maintenance.repo
```

Một người dùng có thể đăng ký nhiều repository. Hãy kiểm tra danh sách nếu scheduler đang bảo trì những repository không còn sử dụng.

### 5.2. Khởi động scheduler

```bash
git maintenance start
```

Lệnh này thiết lập cơ chế chạy bảo trì nền theo scheduler mà Git hỗ trợ trên hệ điều hành hiện tại. Tùy nền tảng và bản Git, scheduler có thể dựa trên cron, systemd, launchd hoặc Windows Task Scheduler.

`start` thực hiện các cập nhật cấu hình giống `register`, sau đó tạo hoặc cập nhật scheduler để gọi `git maintenance run --scheduled` theo lịch. Vì vậy, có thể chạy `git maintenance start` trực tiếp mà không cần gọi `register` trước; gọi `register` riêng hữu ích khi chỉ muốn thêm repository vào danh sách trước.

Scheduler chạy tiến trình kiểm tra theo giờ; task `daily` được chạy cùng lượt vào nửa đêm và task `weekly` được chạy vào lượt tương ứng đầu tuần. Git chọn các task dựa trên schedule đã cấu hình cho từng repository. Việc start scheduler không có nghĩa mọi task chạy ngay lập tức tại thời điểm gọi lệnh.

Có thể chỉ định scheduler nếu cần:

```bash
git maintenance start --scheduler=auto
```

Các lựa chọn hiện đại gồm `auto`, `crontab`, `systemd-timer`, `launchctl` và `schtasks`; danh sách hỗ trợ phụ thuộc phiên bản Git và hệ điều hành. `auto` chọn cơ chế phù hợp trên máy.

Nếu cần xem lựa chọn scheduler hoặc cách vận hành trên phiên bản cụ thể:

```bash
git maintenance start --help
git maintenance run --help
```

Không tự tạo thêm cron job hoặc scheduled task trùng lặp nếu Git đã cài scheduler cho người dùng; các lịch trùng có thể chạy bảo trì đồng thời và tiêu tốn tài nguyên không cần thiết.

### 5.3. Dừng scheduler

```bash
git maintenance stop
```

Lệnh này dừng cơ chế chạy bảo trì nền đã được Git thiết lập. Việc dừng scheduler khác với bỏ đăng ký repository; nếu muốn repository không còn nằm trong danh sách được bảo trì, dùng `unregister`.

`stop` dừng lịch nền do Git thiết lập cho người dùng, nên các repository khác trong danh sách cũng không được chạy theo lịch đó cho tới khi scheduler được khởi động lại. Nó không xóa các mục `maintenance.repo`.

### 5.4. Bỏ đăng ký repository

```bash
git maintenance unregister
```

Lệnh này gỡ repository hiện tại khỏi danh sách maintenance repository. Nó không xóa repository, commit, branch hoặc object. Nó chỉ thay đổi việc repository có được scheduler bảo trì theo danh sách đăng ký hay không.

`unregister` không dừng scheduler và không hủy một tiến trình bảo trì đang chạy. Scheduler vẫn hoạt động cho các repository còn lại trong danh sách. Nếu muốn dừng lịch nền của người dùng, dùng `git maintenance stop`; nếu chỉ muốn loại một repository, dùng `unregister`.

### 5.5. Kiểm tra trạng thái cấu hình

```bash
git config --show-origin --show-scope --get-regexp '^maintenance\.'
```

Kết quả giúp kiểm tra `maintenance.repo`, task enabled, schedule và strategy nếu các khóa đó được cấu hình. Cấu hình có thể đến từ global hoặc local tùy khóa; dùng `--show-origin` để biết chính xác nguồn.

## 6. Cấu hình task và lịch chạy

Git cho phép cấu hình task được bật và tần suất chạy. Các khóa có dạng `maintenance.<task>.enabled` và `maintenance.<task>.schedule`.

### 6.1. Chọn maintenance strategy

`maintenance.strategy` là cấu hình tổng hợp quyết định nhóm task nào được dùng khi không truyền `--task`. Các chiến lược thường gặp trong Git hiện đại:

| Strategy | Mục tiêu |
|---|---|
| `none` | Không chạy task theo lịch; thường là mặc định của scheduled maintenance khi chưa có strategy phù hợp. |
| `gc` | Chạy task garbage collection tổng hợp. |
| `geometric` | Tối ưu pack theo chiến lược geometric, cập nhật dữ liệu phụ trợ và dọn một số dữ liệu hết hạn; phù hợp repository lớn. |
| `incremental` | Chạy các task nhỏ theo lịch để giảm chi phí mỗi lần và tránh task `gc` trong lịch nền. |

`register` đặt strategy thành `incremental` nếu chưa có giá trị. Một cấu hình có sẵn sẽ được giữ lại. Tùy strategy và kiểu chạy (manual, auto hoặc scheduled), task được chọn có thể khác nhau; các khóa `maintenance.<task>.enabled` và `maintenance.<task>.schedule` có thể điều chỉnh lựa chọn.

Với `incremental`, lịch khuyến nghị là `prefetch` và `commit-graph` theo giờ; `loose-objects` và `incremental-repack` theo ngày; `pack-refs` theo tuần; task `gc` không được lên lịch. Khi chạy bảo trì thủ công với strategy này, Git dùng task `gc`. Với `geometric`, Git tối ưu pack theo cấp số nhân, cập nhật cấu trúc phụ trợ và có thể expire reflog hoặc prune worktree stale; strategy này được thiết kế cho repository lớn và cần hiểu tác động dọn dẹp trước khi dùng.

Xem strategy hiện tại:

```bash
git config --show-origin --get maintenance.strategy
```

Không nên đổi strategy chỉ để ép chạy một task đơn lẻ. Dùng `--task=<task>` cho yêu cầu cụ thể; đổi strategy khi muốn thay đổi chính sách bảo trì lâu dài.

### 6.2. `is-needed`: kiểm tra trước khi chạy

```bash
git maintenance is-needed --auto
```

Lệnh kiểm tra xem ngưỡng tự động có yêu cầu bảo trì hay không mà chưa chạy task. Exit status `0` nghĩa là cần chạy; `1` nghĩa là hiện chưa cần. Nó phù hợp cho script muốn quyết định có gọi maintenance hay không mà không phải chạy thử toàn bộ công việc.

`is-needed` cũng hiểu các task được chỉ định bằng `--task`. Hãy xem `git maintenance is-needed --help` nếu muốn kết hợp task cụ thể hoặc dùng trên phiên bản Git khác.

### 6.3. Cấu hình task và schedule

Ví dụ bật task commit-graph ở scope global:

```bash
git config --global maintenance.commit-graph.enabled true
```

Đặt lịch cho task:

```bash
git config --global maintenance.commit-graph.schedule daily
```

Tên task và giá trị schedule hợp lệ phụ thuộc phiên bản Git. Hãy kiểm tra tài liệu `git-maintenance` trước khi đặt cấu hình cho task ít dùng.

Có thể xem tất cả cấu hình liên quan:

```bash
git config --show-origin --show-scope --get-regexp '^maintenance\.'
```

Không nên bật tất cả task ở tần suất cao một cách máy móc. Chẳng hạn, prefetch hourly có thể phù hợp với repository làm việc liên tục và có mạng ổn định, nhưng không cần thiết với repository ít thay đổi hoặc remote có hạn mức bandwidth chặt.

## 7. Phân biệt `git maintenance` với `git gc`

Hai lệnh có liên quan nhưng cách tổ chức công việc khác nhau:

| Tiêu chí | `git maintenance` | `git gc` |
|---|---|---|
| Mục tiêu | Điều phối nhiều task bảo trì riêng biệt, có thể chạy tăng dần hoặc theo lịch. | Chạy quy trình garbage collection tổng hợp. |
| Phạm vi | Có thể chạy một task như prefetch, commit-graph, loose-objects, incremental-repack hoặc gc. | Tập trung vào đóng gói, dọn dẹp và tối ưu object database. |
| Lịch nền | Có lệnh register/start/stop để tích hợp scheduler. | Có thể được gọi thủ công hoặc tự động qua ngưỡng `gc.auto`; không tự thiết lập lịch nền theo cách `maintenance start` làm. |
| Object unreachable | Task `gc` có thể prune object đã hết thời hạn giữ theo cấu hình. | Có thể prune object unreachable đã quá thời hạn giữ. |
| Phù hợp | Bảo trì định kỳ, phân bổ chi phí và tác vụ chuyên biệt. | Dọn dẹp tổng hợp hoặc xử lý khi cần GC theo hiểu biết rõ ràng. |

`git gc --auto` là cơ chế GC tự động dựa trên ngưỡng cấu hình; nó không tương đương với việc khởi chạy scheduler bảo trì nền.

## 8. Cẩn thận với object unreachable và prune

### 8.1. Vì sao GC có thể ảnh hưởng tới recovery?

Khi branch bị reset hoặc xóa, commit cũ có thể không còn reachable từ branch/ref hiện tại. Tuy vậy, object có thể còn được giữ bởi reflog hoặc khoảng thời gian grace period trước khi prune.

Nếu đang cần tìm lại commit:

```bash
git reflog --all --date=iso
git fsck --full --no-reflogs --unreachable
```

Khi xác định được commit cần giữ, tạo branch cứu hộ:

```bash
git branch rescue/recovered <commit-id>
```

Sau đó mới cân nhắc bảo trì hoặc prune theo chính sách.

### 8.2. Không dùng `--prune=now` như cách tăng tốc

Lệnh:

```bash
git gc --prune=now
```

có thể loại bỏ object unreachable ngay, bỏ qua thời gian grace period thông thường. Nếu một tiến trình Git khác đang tạo object nhưng chưa kịp cập nhật ref, prune ngay có thể làm tăng nguy cơ mất dữ liệu hoặc hỏng repository.

Không chạy `git gc --prune=now` hoặc `git prune` theo thói quen. Chỉ dùng trong tình huống đã hiểu rõ trạng thái, có backup và bảo đảm không có tiến trình khác đang ghi repository.

### 8.3. Maintenance không phải công cụ xóa mọi dữ liệu cũ ngay lập tức

Git có chủ đích giữ một số object unreachable trong thời gian nhất định để hỗ trợ các thao tác vừa viết lại lịch sử. Vì vậy, sau khi xóa branch hoặc reset, dung lượng repository có thể chưa giảm ngay. Đây không nhất thiết là lỗi.

## 9. Theo dõi dung lượng và hiệu năng

### 9.1. Đếm object và pack

```bash
git count-objects -vH
```

Các trường thường gặp gồm:

- `count`: số loose object.
- `size`: dung lượng loose object.
- `in-pack`: số object trong pack.
- `packs`: số pack file.
- `size-pack`: dung lượng pack.
- `prune-packable`: object loose đã có bản tương ứng trong pack.
- `garbage`: dữ liệu không được nhận diện là object hợp lệ.
- `size-garbage`: dung lượng dữ liệu garbage.

Đây là số liệu giúp nhận biết xu hướng, không phải một ngưỡng duy nhất để kết luận repository cần GC.

### 9.2. Kiểm tra pack và multi-pack-index

```bash
git multi-pack-index verify
git verify-pack -v .git/objects/pack/*.idx
```

`git multi-pack-index verify` kiểm tra MIDX nếu repository có sử dụng. `git verify-pack` kiểm tra nội dung pack index được chỉ định; ví dụ glob `.git/objects/pack/*.idx` phù hợp với repository có Git directory dạng thư mục `.git` thông thường. Với linked worktree hoặc Git directory khác vị trí, cần xác định đường dẫn thực tế.

PowerShell không tự mở rộng wildcard cho chương trình native theo cách một số shell Unix làm. Nếu chạy trên PowerShell, có thể lấy danh sách `.idx` rồi gọi từng file:

```powershell
$packDir = git rev-parse --git-path objects/pack
Get-ChildItem -LiteralPath $packDir -Filter '*.idx' | ForEach-Object {
    git verify-pack -v $_.FullName
}
```

### 9.3. Kiểm tra commit graph

```bash
git commit-graph verify
```

Nếu commit-graph chưa tồn tại, có thể không có dữ liệu để verify. Có thể tạo dữ liệu bằng task tương ứng:

```bash
git maintenance run --task=commit-graph
```

## 10. Tác động tới remote, LFS và repository đặc biệt

### 10.1. Prefetch không thay thế fetch/pull của người dùng

Prefetch chuẩn bị dữ liệu từ remote vào namespace riêng. Nó không tự cập nhật branch đang checkout, không merge thay đổi và không thay thế quy trình review/pull. Trước khi tích hợp code, người dùng vẫn cần fetch/merge/rebase theo quy trình nhóm.

### 10.2. Git maintenance không quản lý quota LFS server

Git LFS lưu nội dung lớn trên LFS server. `git maintenance` tối ưu Git object database local và các refs; nó không tự xóa LFS object trên server, không giảm quota lưu trữ LFS và không thay thế `git lfs prune` đối với cache LFS local.

Không nhầm `git gc` hoặc `git maintenance run` với chính sách retention của LFS provider.

### 10.3. Linked worktree và submodule

Linked worktree có thể dùng chung object database với repository chính. Hãy hiểu Git directory và common directory trước khi thao tác bảo trì thủ công trên các đường dẫn vật lý.

Submodule là repository riêng. Bảo trì repository cha không đồng nghĩa mọi object database của submodule đều được bảo trì. Nếu submodule lớn hoặc hoạt động lâu ngày, cần kiểm tra và bảo trì riêng theo chính sách dự án.

### 10.4. Repository dùng chung trên server

Với repository bare hoặc repository trên server, lịch bảo trì nên do quản trị viên hoặc hệ thống vận hành quản lý. Không tự thiết lập scheduler trên một máy cá nhân nếu repository thực tế được nhiều tiến trình hoặc nhiều người truy cập qua storage dùng chung mà chưa hiểu cơ chế khóa và chính sách vận hành.

## 11. Quy trình bảo trì định kỳ mẫu

Với repository cá nhân được dùng thường xuyên:

**Bước 1: Kiểm tra trạng thái và cấu hình**

```bash
git status -sb
git count-objects -vH
git config --show-origin --show-scope --get-regexp '^maintenance\.'
```

**Bước 2: Đăng ký repository**

```bash
git maintenance register
```

**Bước 3: Khởi động scheduler**

```bash
git maintenance start
```

Có thể bỏ bước `register` riêng và chạy `git maintenance start` trực tiếp, vì `start` tự thực hiện các cập nhật cấu hình như `register` trước khi tạo lịch nền.

**Bước 4: Khi cần, chạy task cụ thể để kiểm tra**

```bash
git maintenance run --task=commit-graph
git maintenance run --task=loose-objects
```

**Bước 5: Xác minh dữ liệu và trạng thái**

```bash
git count-objects -vH
git commit-graph verify
git status -sb
```

**Bước 6: Khi không còn muốn scheduler bảo trì repository này**

```bash
git maintenance unregister
```

Nếu muốn dừng scheduler nền của người dùng, dùng `git maintenance stop`. Hãy phân biệt việc dừng scheduler với việc bỏ đăng ký một repository.

Với repository lớn hoặc có dữ liệu đang cần phục hồi, hãy sao lưu, kiểm tra reflog/object trước và chọn task không prune trước. Chỉ chạy GC khi đã hiểu tác động và không còn cần giữ object unreachable để điều tra.

## 12. Những lỗi thường gặp

### 12.1. `git maintenance start` không tạo lịch như mong đợi

Kiểm tra phiên bản Git, scheduler được hỗ trợ trên hệ điều hành, quyền tạo tác vụ nền và cấu hình maintenance. Xem trợ giúp `git maintenance start --help`. Một số môi trường container, CI hoặc máy không có scheduler hệ thống phù hợp có thể không phải nơi thích hợp để chạy lịch nền.

Trên Windows, Git dùng Task Scheduler (`schtasks`) và các tác vụ có thể mở cửa sổ console khi chạy. Có thể kiểm tra task trong Task Scheduler; tên thường có dạng `Git Maintenance (hourly)`, `Git Maintenance (daily)` và `Git Maintenance (weekly)`. Nếu cần chạy khi người dùng không đăng nhập, tùy chọn tương ứng trong Task Scheduler có thể yêu cầu thông tin xác thực Windows.

### 12.2. `git maintenance run` không chạy task mong muốn

Kiểm tra `maintenance.<task>.enabled`, schedule và cách gọi. `--schedule=hourly` chỉ chọn task được cấu hình chạy hourly; `--task=<task>` yêu cầu task cụ thể.

### 12.3. Prefetch không cập nhật branch local

Đây là hành vi bình thường. Prefetch chỉ chuẩn bị dữ liệu từ remote; dùng `git fetch` để cập nhật remote-tracking refs theo refspec thông thường và merge/rebase để tích hợp.

### 12.4. Dung lượng không giảm sau bảo trì

Một task có thể tạo thêm pack hoặc chỉ mục, prefetch có thể tải thêm object, còn GC có thể giữ object unreachable trong grace period. So sánh `git count-objects -vH` và kiểm tra loại dữ liệu tăng thay vì chỉ nhìn tổng dung lượng.

### 12.5. Repository đang phục hồi nhưng object biến mất

Có thể một tác vụ prune/GC đã loại object unreachable. Trước khi chạy bảo trì trên repository đang điều tra, hãy tạo ref cứu hộ cho commit cần giữ và sao lưu. Nếu object đã bị prune khỏi mọi bản sao, cần tìm backup hoặc clone khác.

## 13. Ghi nhớ

- `git maintenance` chia bảo trì thành task nhỏ và hỗ trợ chạy thủ công hoặc theo lịch.
- `git maintenance run --task=<task>` chạy task cụ thể; `--auto` chỉ chạy khi điều kiện tự động được đáp ứng.
- `commit-graph` tăng tốc duyệt lịch sử; `prefetch` chuẩn bị dữ liệu từ remote; `loose-objects` và `incremental-repack` tổ chức object/pack; `pack-refs` đóng gói ref; `gc` thực hiện garbage collection.
- `register` đăng ký repository; `start` thiết lập scheduler; `stop` dừng scheduler; `unregister` gỡ repository khỏi danh sách.
- `git maintenance` và `git gc` có liên quan nhưng không phải cùng một giao diện hoặc cùng một mục đích.
- Object unreachable có thể cần thiết cho recovery; tạo branch/tag cứu hộ trước khi prune.
- Không dùng `git gc --prune=now` hoặc `git prune` theo thói quen, nhất là khi tiến trình khác đang ghi repository.
- `git count-objects -vH`, `git commit-graph verify`, `git multi-pack-index verify` giúp theo dõi và kiểm tra dữ liệu bảo trì.
- Prefetch không merge code; Git maintenance không quản lý quota LFS server.
- Linked worktree, submodule và repository dùng chung cần được xem xét theo cấu trúc object database thực tế.

Hãy xem `git maintenance` như lịch chăm sóc repository: chọn task theo dấu hiệu thực tế, chạy với tần suất phù hợp và xác minh sau khi hoàn tất. Đặc biệt, bảo toàn object cần phục hồi trước khi chạy GC giúp việc tối ưu không vô tình làm mất dữ liệu mà nhóm vẫn đang cần.

## 14. Tài liệu tham khảo

- [Git `maintenance`](https://git-scm.com/docs/git-maintenance)
- [Git `config`](https://git-scm.com/docs/git-config)
- [Git `gc`](https://git-scm.com/docs/git-gc)
