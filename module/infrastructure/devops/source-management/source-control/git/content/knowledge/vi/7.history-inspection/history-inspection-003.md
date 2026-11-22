# Định dạng kết quả git log để đọc nhanh hoặc trích xuất dữ liệu

Lịch sử Git có thể chứa hàng trăm hoặc hàng nghìn commit. Nếu chỉ dùng `git log` mặc định, bạn thường phải đọc nhiều thông tin hơn mức cần thiết; còn nếu muốn tạo changelog, báo cáo hoặc đưa dữ liệu vào script, đầu ra cần có cấu trúc nhất quán.

Git cung cấp các preset như `--oneline`, `--stat`, `--graph`, cùng tùy chọn `--pretty=format:` để tự định dạng từng commit. Bạn có thể chọn trường cần hiển thị như OID, tác giả, ngày, subject, parent và ref đang trỏ tới commit. Bài viết tập trung vào cách định dạng và kiểm soát đầu ra, đồng thời phân biệt việc chọn commit với việc trình bày commit.

## 1. Tách việc chọn commit khỏi việc định dạng kết quả

Một lệnh `git log` thường có hai phần:

- **Revision và bộ lọc** quyết định commit nào được đưa vào kết quả.
- **Tùy chọn trình bày** quyết định mỗi commit được hiển thị như thế nào.

Ví dụ:

```bash
git log --since="2026-01-01" --author="Lan" --pretty=oneline
```

`--since` và `--author` lọc tập commit. `--pretty=oneline` định dạng kết quả của những commit đã chọn.

Một số bộ lọc thường dùng:

| Tùy chọn | Ý nghĩa |
|---|---|
| `-n 10` hoặc `-10` | Giới hạn tối đa 10 commit |
| `--since="2 weeks ago"` | Chọn commit có ngày committer từ mốc thời gian trở đi |
| `--until="2026-11-01"` | Giới hạn tới mốc thời gian |
| `--author="Lan"` | Lọc theo author identity |
| `--committer="Maintainer"` | Lọc theo committer identity |
| `--grep="fix"` | Tìm chuỗi trong commit message |
| `--all` | Duyệt commit reachable từ các refs được biết |
| `-- path/to/file` | Giới hạn lịch sử theo đường dẫn |

Ví dụ xem 15 commit gần nhất của một file:

```bash
git log -15 --oneline -- src/auth/LoginService.java
```

Ví dụ tìm commit của một tác giả có message nhắc tới parser:

```bash
git log --author="Lan" --grep="parser" --oneline
```

Nếu không có commit phù hợp, Git không in kết quả. Việc đổi format không làm thay đổi tập commit đã chọn.

## 2. Các preset giúp đọc nhanh

Git có các kiểu trình bày dựng sẵn. Những kiểu phổ biến:

| Tùy chọn | Nội dung |
|---|---|
| `--oneline` | OID rút gọn và subject trên một dòng |
| `--pretty=short` | Thông tin author và commit message |
| `--pretty=medium` | Dạng mặc định, có author, ngày và message |
| `--pretty=full` | Bổ sung committer |
| `--pretty=fuller` | Hiển thị cả author date và committer date |
| `--pretty=reference` | Dạng tham chiếu ngắn gọn, phù hợp trích dẫn commit |
| `--pretty=raw` | Hiển thị nội dung commit object ở dạng raw |

Xem lịch sử ngắn gọn:

```bash
git log --oneline -10
```

Ví dụ đầu ra:

```text
a31f8d2 Add login validation
c2e14b9 Fix token expiration
7a9d310 Create authentication service
```

`--oneline` tương đương kiểu `oneline` kết hợp với OID rút gọn. Nó rất hữu ích khi xem nhanh, nhưng không đủ trường để làm báo cáo chi tiết.

Xem đầy đủ thông tin tác giả và người tạo commit:

```bash
git log --pretty=fuller -5
```

`author` là người được ghi nhận tạo ra thay đổi; `committer` là người tạo commit object hiện tại. Hai người và hai ngày có thể khác nhau, ví dụ khi maintainer cherry-pick commit do người khác viết.

## 3. Hiển thị branch và quan hệ commit bằng graph

Khi nhiều branch phát triển song song, danh sách tuyến tính có thể che mất quan hệ merge. Kết hợp `--graph`, `--decorate` và `--oneline`:

```bash
git log --graph --oneline --decorate --all
```

Ví dụ:

```text
* a31f8d2 (HEAD -> main, origin/main) Merge feature/login
|\
| * 51c3e90 (feature/login) Add login validation
| * 82ad1f4 Add token service
* | c2e14b9 Fix token expiration
|/
* 7a9d310 Initial project
```

Ý nghĩa:

- `--graph` vẽ các nhánh bằng ký tự ASCII.
- `--decorate` hiển thị tên branch, tag và ref liên quan tới commit.
- `--all` yêu cầu duyệt commit reachable từ tất cả refs được biết trong repository.
- `--oneline` giữ mỗi commit trên một dòng để graph dễ đọc.

Có thể chọn cách hiển thị decoration:

```bash
git log --decorate=short --oneline --all
git log --decorate=full --oneline --all
git log --no-decorate --oneline -10
```

`short` thường hiển thị tên như `main` hoặc `origin/main`; `full` hiển thị tên ref đầy đủ như `refs/heads/main`. Dùng `--no-decorate` khi cần đầu ra không có nhãn ref.

Nếu chỉ muốn xem lịch sử đi theo first parent của branch chính:

```bash
git log --first-parent --oneline --graph main
```

Tùy chọn này chỉ đi theo parent thứ nhất ở các merge commit, giúp xem các mốc tích hợp chính. Nó không phải toàn bộ lịch sử của mọi nhánh đã merge.

## 4. Tự định dạng bằng --pretty=format

Khi cần kiểm soát chính xác trường thông tin, dùng:

```bash
git log --pretty=format:"<format>"
```

`--format` là dạng viết ngắn của `--pretty=format:`. Bạn có thể kết hợp văn bản cố định và placeholder bắt đầu bằng `%`.

Ví dụ hiển thị OID rút gọn, ngày, author và subject:

```bash
git log -10 --date=short --pretty=format:"%h %ad | %an | %s"
```

Kết quả minh họa:

```text
a31f8d2 2026-10-20 | Lan Nguyen | Add login validation
c2e14b9 2026-10-18 | Minh Tran | Fix token expiration
7a9d310 2026-10-15 | Lan Nguyen | Create authentication service
```

Format này phù hợp để đọc nhanh vì mỗi commit có cùng thứ tự trường. Khi dùng trong script, nên chỉ định rõ format thay vì dựa vào output mặc định có thể thay đổi theo cấu hình.

## 5. Các placeholder quan trọng

Placeholder giúp lấy trường cụ thể từ commit. Những trường thường dùng:

| Placeholder | Giá trị |
|---|---|
| `%H` | OID đầy đủ của commit |
| `%h` | OID rút gọn |
| `%T` / `%t` | OID tree đầy đủ / rút gọn |
| `%P` / `%p` | OID các parent đầy đủ / rút gọn |
| `%an` / `%aN` | Tên author / tên author đã áp dụng mailmap |
| `%ae` / `%aE` | Email author / email author đã áp dụng mailmap |
| `%cn` / `%cN` | Tên committer / tên committer đã áp dụng mailmap |
| `%ce` / `%cE` | Email committer / email committer đã áp dụng mailmap |
| `%s` | Subject, tức dòng đầu của commit message |
| `%f` | Subject đã được chuẩn hóa để dùng trong tên file |
| `%b` | Phần body của commit message |
| `%B` | Toàn bộ commit message, gồm subject và body |
| `%N` | Notes gắn với commit |
| `%d` | Decoration của ref, thường có dấu ngoặc |
| `%D` | Decoration không có dấu ngoặc |
| `%n` | Xuống dòng |
| `%xNN` | In byte có mã hex NN, ví dụ `%x09` là tab |

Ví dụ:

```bash
git log -5 --pretty=format:"%H%nParents: %P%nAuthor: %an <%ae>%nSubject: %s%n"
```

Kết quả có OID, parent, danh tính author và subject trên các dòng riêng.

Một số placeholder dùng mailmap như `%aN` hoặc `%aE` giúp chuẩn hóa danh tính khi cùng một người có nhiều cách ghi tên/email. Nếu repository không có mailmap phù hợp, kết quả có thể giống trường gốc.

Không nhầm author với committer: dùng `%an`, `%ae`, `%aI` cho author; dùng `%cn`, `%ce`, `%cI` cho committer.

## 6. Định dạng ngày tháng

Git lưu timestamp cho author và committer. Placeholder ngày có thể hiển thị theo nhiều cách:

| Placeholder | Ý nghĩa |
|---|---|
| `%ad` | Author date theo định dạng được chọn bởi `--date` |
| `%aD` | Author date dạng RFC2822 |
| `%ar` | Author date tương đối, ví dụ `2 weeks ago` |
| `%at` | Author timestamp dạng Unix |
| `%aI` | Author date dạng ISO 8601 strict |
| `%as` | Author date dạng `YYYY-MM-DD` |
| `%cd` | Committer date theo `--date` |
| `%cD` | Committer date dạng RFC2822 |
| `%cr` | Committer date tương đối |
| `%ct` | Committer timestamp dạng Unix |
| `%cI` | Committer date dạng ISO 8601 strict |
| `%cs` | Committer date dạng `YYYY-MM-DD` |

Chọn định dạng ngày bằng `--date`:

```bash
git log -5 --date=short --pretty=format:"%h %ad %s"
git log -5 --date=relative --pretty=format:"%h %ad %s"
git log -5 --date=iso-strict --pretty=format:"%h %ad %s"
```

- `short` hiển thị ngày dạng năm-tháng-ngày.
- `relative` hiển thị khoảng thời gian tương đối so với thời điểm chạy lệnh.
- `iso-strict` hiển thị dạng ISO 8601 có múi giờ.

Nếu cần dữ liệu nhất quán giữa máy và pipeline, ưu tiên `%aI` hoặc `%cI` thay vì ngày tương đối. `relative` thay đổi theo thời điểm truy vấn nên không thích hợp làm dữ liệu đối chiếu lâu dài.

Ví dụ dùng author date và committer date cạnh nhau:

```bash
git log -5 --pretty=format:"%h | author=%aI | committer=%cI | %s"
```

Điều này hữu ích khi điều tra commit được tạo từ một thay đổi cũ nhưng được cherry-pick hoặc áp dụng lại vào thời điểm khác.

## 7. Tạo định dạng có nhiều dòng và phân tách record

Có thể dùng `%n` để xuống dòng và `%xNN` để chèn ký tự điều khiển:

```bash
git log -3 --pretty=format:"Commit: %H%nAuthor: %an <%ae>%nDate: %aI%nSubject: %s%n"
```

Nếu muốn mỗi commit cách nhau bằng một dòng trống:

```bash
git log -3 --pretty=format:"%h %s%nAuthor: %an%nDate: %aI%n"
```

`format:<format>` và `tformat:<format>` có khác biệt về ký tự phân tách record:

- `format:<format>` dùng chuỗi format và đặt dấu phân cách giữa các commit.
- `tformat:<format>` dùng chuỗi format nhưng đặt ký tự kết thúc sau mỗi commit (terminator). Nếu format không tự thêm newline, `tformat` vẫn kết thúc record bằng newline.

Ví dụ:

```bash
git log -3 --pretty=tformat:"%h %s"
```

Với đầu ra dòng, `tformat` thường dễ xử lý hơn vì mỗi commit có dòng kết thúc riêng, kể cả commit cuối cùng.

Bạn cũng có thể viết:

```bash
git log -3 --format="%h %s"
```

Đây là alias của `--pretty=format:`; không nên nhầm tên tùy chọn `--format` với một định dạng dữ liệu chuẩn như JSON hoặc CSV. Nó chỉ là cơ chế thay placeholder của Git.

## 8. Kết hợp màu sắc và căn chỉnh

Git có thể tô màu placeholder để dễ quét kết quả:

```bash
git log -10 --pretty=format:"%C(yellow)%h%C(reset) %C(green)%ad%C(reset) %s" --date=short
```

Một số cách dùng:

- `%C(yellow)`, `%C(green)`, `%C(red)`: chọn màu.
- `%C(bold)`: bật chữ đậm.
- `%C(reset)`: trả về màu mặc định.
- `%C(auto)`: để Git tự quyết định khi nào dùng màu.

Có thể dùng căn chỉnh trong custom format:

```bash
git log -10 --pretty=format:"%C(yellow)%<(8)%h%C(reset) %<(12,trunc)%an %s"
```

Các placeholder căn chỉnh như `%<`, `%>` hoặc `%><` giúp dành độ rộng cho trường kế tiếp. Tùy chọn `trunc` cho phép rút gọn nội dung khi vượt độ rộng đã đặt.

Màu sắc hữu ích cho terminal tương tác. Khi redirect output vào file hoặc pipeline, nên tắt màu:

```bash
git log --no-color --pretty=format:"%h %ad %s" --date=short
```

Không nên đưa mã ANSI màu vào file CSV hoặc dữ liệu máy đọc nếu không chủ đích.

## 9. Kết hợp format với thống kê file

`git log` có thể hiển thị thông tin commit cùng thống kê thay đổi:

```bash
git log --stat -5
git log --shortstat -5
git log --numstat -5
```

| Tùy chọn | Nội dung |
|---|---|
| `--stat` | Tên file và biểu đồ số dòng thêm/xóa |
| `--shortstat` | Một dòng tổng số file, dòng thêm và dòng xóa |
| `--numstat` | Số dòng thêm/xóa theo từng file, thuận tiện cho script hơn |
| `--summary` | Tóm tắt create/delete mode, rename và thay đổi metadata |

Nếu chỉ cần danh sách file thay đổi:

```bash
git log --name-only --format="%h %s" -5
```

Nếu cần cả trạng thái file:

```bash
git log --name-status --format="%h %s" -5
```

Các mã trạng thái thường gặp gồm `A` (added), `M` (modified), `D` (deleted), `R` (renamed) và `C` (copied). Rename/copy detection dựa trên độ tương đồng nội dung và tùy chọn Git, vì vậy không phải metadata rename cố định được lưu trong commit.

Có thể bỏ phần patch và chỉ giữ metadata:

```bash
git log --no-patch --format="%h %ad %s" --date=short -5
```

Nếu cần thống kê file, dùng `--stat` riêng:

```bash
git log --stat -5
```

`--no-patch` hữu ích khi muốn báo cáo commit mà không in toàn bộ diff.

## 10. Chỉ lấy những trường cần cho báo cáo

Ví dụ báo cáo commit gồm OID, ngày, tác giả và subject:

```bash
git log -20 --date=short --format="%H,%ad,%an,%s"
```

Đầu ra trông giống CSV nhưng chưa phải CSV an toàn trong mọi trường hợp. Tên tác giả hoặc subject có thể chứa dấu phẩy, dấu ngoặc kép hoặc ký tự xuống dòng; nếu đưa thẳng vào spreadsheet, trường có thể bị tách sai.

Nếu dùng dấu phân cách tab:

```bash
git log -20 --format="%H%x09%aI%x09%an%x09%s"
```

`%x09` chèn ký tự tab. Đây là TSV thuận tiện cho dữ liệu nội bộ có nội dung trường được kiểm soát. Tuy nhiên, tab cũng có thể xuất hiện trong dữ liệu commit; hãy chọn delimiter phù hợp và escape/quote dữ liệu nếu cần độ tin cậy cao.

Một ví dụ khác lấy OID, parent và subject để phục vụ phân tích lịch sử:

```bash
git log -20 --format="%H%x09%P%x09%s"
```

Nếu cần định dạng dễ parse hơn, có thể dùng byte phân tách hiếm gặp như NUL:

```bash
git log -20 --pretty=tformat:"%H%x00%P%x00%aI%x00%an%x00%s"
```

`%x00` chèn byte NUL giữa các trường. Công cụ đọc kết quả phải hỗ trợ dữ liệu nhị phân và tách trường theo NUL; không dùng shell command substitution thông thường để giữ byte NUL vì nhiều shell loại bỏ hoặc không thể biểu diễn chúng trong biến. `tformat` vẫn thêm terminator cho mỗi record, nên parser cần tính đến ký tự kết thúc record.

Đối với tích hợp dài hạn, hãy coi `git log --format` là giao diện văn bản có cấu trúc do bạn định nghĩa, không phải JSON schema tự động. Chọn trường rõ ràng, delimiter rõ ràng, quy tắc encoding và cách xử lý message nhiều dòng.

## 11. Tạo changelog ngắn từ commit message

Một changelog đơn giản có thể lấy subject của commit kể từ tag gần nhất:

```bash
git log v2.3.0..HEAD --no-merges --pretty=format:"- %s"
```

- `v2.3.0..HEAD` chọn commit reachable từ HEAD nhưng không reachable từ tag `v2.3.0`.
- `--no-merges` bỏ qua merge commit.
- `%s` lấy subject của mỗi commit.

Nếu muốn hiển thị OID rút gọn và tác giả:

```bash
git log v2.3.0..HEAD --no-merges --date=short --pretty=format:"- %s (%h, %an, %ad)"
```

Đây chỉ là changelog cơ bản. Chất lượng phụ thuộc vào quy ước commit message của dự án. Nếu subject không mô tả rõ thay đổi, định dạng đẹp không thể tự tạo nội dung release note chính xác.

Nếu cần lịch sử theo thứ tự cũ tới mới:

```bash
git log --reverse v2.3.0..HEAD --no-merges --pretty=format:"- %s"
```

`--reverse` đảo thứ tự hiển thị của các commit được chọn. Hãy kiểm tra tag nền và tập commit trước khi dùng đầu ra để phát hành.

## 12. Lọc và định dạng theo một file

Có thể kết hợp pathspec với custom format:

```bash
git log --format="%h %ad %an %s" --date=short -- src/auth/LoginService.java
```

Lệnh chỉ hiển thị lịch sử commit có ảnh hưởng tới đường dẫn đó theo quy tắc path history của Git.

Để theo dõi file qua một lần rename, có thể dùng `--follow`:

```bash
git log --follow --format="%h %ad %s" --date=short -- src/auth/LoginService.java
```

`--follow` chỉ hỗ trợ một path và có giới hạn với lịch sử phức tạp hoặc rename nhiều lần. Nó là cơ chế truy vết theo suy luận rename, không phải bảo đảm tìm mọi lịch sử đổi tên trong mọi đồ thị.

Nếu chỉ muốn xem commit đầu tiên hoặc gần nhất ảnh hưởng tới file:

```bash
git log -1 --format="%H %s" -- src/auth/LoginService.java
```

Có thể kết hợp `--author`, `--since` hoặc `--grep` để thu hẹp lịch sử trước khi định dạng.

## 13. Đầu ra cho script: những nguyên tắc cần giữ

Khi script đọc kết quả `git log`, tránh parse output mặc định của con người. Output mặc định có thể thay đổi theo cấu hình, locale, màu sắc hoặc phiên bản Git.

Nên:

1. Chỉ định placeholder cần dùng bằng `--format`.
2. Chọn OID đầy đủ (`%H`) nếu cần định danh commit ổn định; không dùng OID rút gọn làm khóa dữ liệu lâu dài.
3. Dùng `%aI` hoặc `%cI` khi cần timestamp có múi giờ ở dạng ISO strict.
4. Chọn delimiter không xung đột với dữ liệu hoặc dùng NUL nếu công cụ đọc hỗ trợ.
5. Tắt màu bằng `--no-color`.
6. Xác định rõ encoding và xử lý commit message nhiều dòng nếu lấy `%b` hoặc `%B`.
7. Xử lý trường hợp không có commit phù hợp.
8. Phân biệt output commit metadata với danh sách file thay đổi.

Ví dụ một lệnh log tối giản cho báo cáo máy đọc:

```bash
git log -100 --no-color --date=iso-strict --format="%H%x09%aI%x09%an%x09%s"
```

Nếu cần trạng thái file, dùng `--name-status` hoặc `--numstat` và đọc đúng cấu trúc nhiều dòng mà Git tạo ra. Không giả định mỗi commit luôn chỉ có một dòng khi bật các tùy chọn liệt kê file.

Đối với dữ liệu cần parse chính xác, hãy thử với repository có tên tác giả, subject và file path chứa dấu cách, dấu phẩy, tab, ký tự Unicode hoặc ký tự đặc biệt. Thiết kế parser theo delimiter và encoding thực tế, không dựa vào vị trí cột hiển thị bằng mắt.

## 14. Một số placeholder và modifier nâng cao

Ngoài các trường cơ bản, format string còn hỗ trợ một số modifier:

| Cú pháp | Ý nghĩa |
|---|---|
| `%C(...)` | Điều khiển màu |
| `%m` | Dấu chỉ commit ở ranh giới left/right/boundary trong một số kiểu duyệt |
| `%w(width,indent1,indent2)` | Điều khiển cách wrap nội dung message |
| `%<(N)` | Căn trường kế tiếp theo độ rộng tối thiểu N, đệm bên phải |
| `%<(N,trunc)` | Cắt nội dung trường kế tiếp khi vượt độ rộng N |
| `%>(N)` | Căn phải trường kế tiếp trong vùng rộng N |
| `%><(N)` | Căn giữa trường kế tiếp trong vùng rộng N |
| `%xNN` | Chèn byte có mã hex |
| `%n` | Xuống dòng |

Ví dụ wrap phần body:

```bash
git log -3 --pretty=format:"%h %s%n%w(72,4,4)%b%n"
```

Ví dụ căn trường OID và tên tác giả:

```bash
git log -10 --pretty=format:"%<(10)%h %<(20,trunc)%an %s"
```

Không phải mọi placeholder đều có ý nghĩa trong mọi chế độ duyệt. Ví dụ `%m` hữu ích khi kết hợp các tùy chọn chọn commit từ nhiều phía như `--left-right` hoặc `--boundary`; nếu dùng trong log thông thường, trường này có thể không cung cấp thông tin đáng kể.

## 15. Những lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Không thấy branch/tag trong log | Chỉ duyệt từ HEAD hoặc refs chưa fetch | Dùng `--all` và fetch remote nếu cần |
| OID bị cắt ngắn | Dùng `--oneline` hoặc `%h` | Dùng `%H` khi cần OID đầy đủ |
| Ngày author và committer khác nhau | Commit được cherry-pick, rebase hoặc tạo lại | Hiển thị cả `%aI` và `%cI` |
| Output nhiều dòng khó đọc | Format chưa có separator rõ ràng | Dùng `%n`, `format:` hoặc `tformat:` có chủ đích |
| CSV bị lệch cột | Subject/tên có dấu phẩy hoặc dấu ngoặc kép | Dùng delimiter phù hợp và quote/escape dữ liệu |
| Script không xử lý được NUL | Shell variable không lưu byte NUL | Dùng file/pipe và parser hỗ trợ binary |
| Có mã màu trong file output | Git tự tô màu terminal | Dùng `--no-color` |
| Thống kê file lẫn vào message | Kết hợp `--stat`/`--name-status` với format mà chưa hiểu cấu trúc output | Dùng `--no-patch` hoặc parse phần thống kê riêng |
| Changelog thiếu commit | Range sai, tag chưa fetch hoặc bộ lọc quá hẹp | Kiểm tra `git log <tag>..HEAD` và refs |
| `--follow` không tìm được lịch sử cũ | Rename detection có giới hạn | Kiểm tra từng mốc rename và diff tree liên quan |

## 16. Quy trình thực tế: tạo báo cáo lịch sử cho một lần phát hành

Giả sử nhóm cần báo cáo những commit kể từ `v2.3.0` để chuẩn bị phát hành.

**Bước 1: Cập nhật refs và xác minh tag.**

```bash
git fetch --all --tags
git show -s --format="%H %s" v2.3.0
```

**Bước 2: Xem danh sách commit được chọn.**

```bash
git log --oneline --decorate v2.3.0..HEAD
```

Xác nhận range đúng với branch phát hành và tag nền.

**Bước 3: Tạo báo cáo dễ đọc.**

```bash
git log --reverse --no-merges --date=short --format:"%h | %ad | %an | %s" v2.3.0..HEAD
```

**Bước 4: Xem thống kê file thay đổi.**

```bash
git log --stat --oneline v2.3.0..HEAD
```

**Bước 5: Xuất dữ liệu nhất quán cho script.**

```bash
git log --reverse --no-merges --no-color --format="%H%x09%cI%x09%an%x09%s" v2.3.0..HEAD
```

Nếu ghi dữ liệu ra file hoặc gửi sang hệ thống khác, hãy xác định encoding, delimiter, quy tắc quote và cách xử lý subject chứa ký tự phân tách trước khi tự động hóa.

## 17. Checklist trước khi dùng git log làm báo cáo

- [ ] Đã xác định revision range và bộ lọc commit.
- [ ] Đã fetch branch/tag cần thiết nếu dữ liệu đến từ remote.
- [ ] Đã chọn preset hay custom format phù hợp.
- [ ] Đã dùng `%H` nếu cần định danh commit đầy đủ.
- [ ] Đã phân biệt author và committer.
- [ ] Đã chọn ngày ISO nếu dữ liệu cần so sánh giữa môi trường.
- [ ] Đã kiểm tra `--graph`, `--decorate` hoặc `--all` nếu cần quan hệ branch/ref.
- [ ] Đã chọn `--stat`, `--numstat` hoặc `--name-status` khi cần thông tin file.
- [ ] Đã xác định delimiter và cách xử lý newline/NUL cho script.
- [ ] Đã tắt màu và kiểm tra trường hợp không có kết quả.

## Kết luận

Dùng `--oneline`, `--graph` và `--decorate` để đọc nhanh lịch sử; dùng `--pretty=fuller` khi cần phân biệt author/committer; dùng `--format` với placeholder như `%H`, `%an`, `%aI`, `%s` để kiểm soát trường dữ liệu. Kết hợp `--stat`, `--numstat` hoặc `--name-status` khi cần thống kê file. Nếu đầu ra được dùng trong script, hãy định nghĩa delimiter, encoding, ngày tháng và cách xử lý dữ liệu nhiều dòng một cách rõ ràng; đừng parse output mặc định dành cho con người.
