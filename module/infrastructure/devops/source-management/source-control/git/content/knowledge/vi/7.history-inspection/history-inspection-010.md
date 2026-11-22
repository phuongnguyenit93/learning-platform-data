# Tìm nội dung trong phiên bản đã theo dõi bằng `git grep`

Khi cần tìm một hàm, tên biến, thông báo lỗi hoặc TODO trong repository, bạn không nhất thiết phải mở từng tệp. Lệnh **`git grep`** tìm nội dung theo pattern trong các tệp Git đang theo dõi. Điểm quan trọng là Git có thể tìm ở ba trạng thái khác nhau: nội dung trong working tree, nội dung đã stage trong index và snapshot của một commit hoặc tree cụ thể.

Chọn đúng trạng thái giúp tránh kết luận sai. Ví dụ, working tree có thể đã sửa một hàm nhưng commit `HEAD` vẫn giữ phiên bản cũ; `git grep` mặc định sẽ đọc nội dung hiện tại trong working tree, còn `git grep <pattern> HEAD` tìm trong snapshot đã commit.

Bài này thuộc chương **Tra cứu lịch sử** của SOURCE_CONTROL_GIT. Nội dung tập trung vào cách tìm nội dung trong phiên bản được Git theo dõi, chọn pattern và pathspec, đọc kết quả, xử lý mã thoát và phân biệt tìm trong một snapshot với tìm qua toàn bộ lịch sử.

## 1. `git grep` dùng để làm gì?

`git grep` tìm các dòng khớp với một pattern trong nội dung tệp. Theo mặc định, lệnh tìm trong các tệp được Git theo dõi ở working tree hiện tại.

Ví dụ tìm tên hàm:

```bash
git grep "calculateTotal"
```

Kết quả thường hiển thị đường dẫn, số dòng và dòng nội dung khớp. Lệnh này hữu ích khi:

- Tìm nơi một hàm hoặc biến được định nghĩa và sử dụng.
- Tìm thông báo lỗi hoặc mã trạng thái.
- Tìm TODO, FIXME hoặc feature flag.
- Tìm cấu hình hay tên API trong source code.
- Kiểm tra một pattern có xuất hiện trong snapshot của commit/tag không.
- So sánh nội dung đang sửa với nội dung đã stage hoặc đã commit.

`git grep` tìm nội dung tệp trong một trạng thái xác định. Nó không tự động duyệt mọi commit trong lịch sử. Nếu mục tiêu là tìm commit mà một chuỗi được thêm, xóa hoặc thay đổi, dùng các công cụ truy vấn lịch sử như `git log -S` hoặc `git log -G`.

## 2. Ba nơi có thể tìm kiếm

Git có thể đọc nội dung từ working tree, index hoặc một tree-ish. Đây là khác biệt quan trọng nhất khi dùng `git grep`.

| Cách gọi | Nguồn nội dung được tìm | Dùng khi nào? |
|---|---|---|
| `git grep <pattern>` | Tệp tracked trong working tree hiện tại | Tìm trên nội dung bạn đang nhìn thấy/chỉnh sửa. |
| `git grep --cached <pattern>` | Blob được ghi nhận trong index | Kiểm tra nội dung đã stage sẽ đi vào commit. |
| `git grep <pattern> <tree-ish>` | Snapshot của commit, tag hoặc tree được chỉ định | Tìm trong phiên bản đã commit hoặc một mốc lịch sử cụ thể. |

### 2.1. Tìm trong working tree mặc định

```bash
git grep -n "timeout"
```

Lệnh tìm trong nội dung hiện có của các tệp tracked trong working tree. Nếu bạn sửa một tệp nhưng chưa stage, `git grep` mặc định có thể tìm thấy nội dung mới đó.

Các tệp untracked không được đưa vào tìm kiếm mặc định. Tệp bị xóa khỏi working tree cũng không còn nội dung để lệnh đọc ở trạng thái này, dù đường dẫn vẫn có thể tồn tại trong index hoặc commit.

### 2.2. Tìm trong index bằng `--cached`

```bash
git grep --cached -n "timeout"
```

`--cached` yêu cầu Git tìm trong nội dung blob mà index đang tham chiếu. Đây là cách kiểm tra phần đã stage, kể cả khi working tree đã tiếp tục thay đổi sau lần `git add` cuối.

Ví dụ:

1. Bạn sửa `src/session.js` để thêm thông báo `refresh timeout`.
2. Chạy `git add src/session.js`.
3. Sửa tiếp working tree thành `refresh deadline` nhưng chưa stage lại.

Khi đó:

```bash
git grep -n "refresh deadline" -- src/session.js
git grep --cached -n "refresh timeout" -- src/session.js
```

Lệnh đầu tìm nội dung working tree; lệnh thứ hai tìm nội dung đã stage trong index. Hai kết quả có thể khác nhau vì index và working tree là hai trạng thái độc lập.

### 2.3. Tìm trong một commit hoặc tag

Đưa tree-ish sau pattern để tìm trong snapshot cụ thể:

```bash
git grep -n "timeout" HEAD
git grep -n "timeout" HEAD~2
git grep -n "timeout" v1.4.0
```

- `HEAD`: snapshot của commit hiện tại.
- `HEAD~2`: snapshot của tổ tiên thứ nhất cách HEAD hai commit.
- `v1.4.0`: snapshot được tag đó trỏ tới (Git sẽ phân giải tag object nếu là annotated tag).

Nếu muốn giới hạn trong thư mục `src/`:

```bash
git grep -n "timeout" HEAD -- src/
```

Các đường dẫn sau `--` là pathspec, dùng để giới hạn tập tệp trong snapshot được tìm.

### 2.4. So sánh ba trạng thái trong cùng một lần điều tra

Khi kết quả tìm kiếm khác nhau, chạy lần lượt:

```bash
# Nội dung đang có trên working tree
git grep -n "legacyToken"

# Nội dung đã stage
git grep --cached -n "legacyToken"

# Nội dung của commit hiện tại
git grep -n "legacyToken" HEAD
```

Ba lệnh giúp xác định chuỗi chỉ xuất hiện trong sửa đổi chưa stage, đã stage hay đã có trong commit. Đây là cách nhanh để kiểm tra một thay đổi trước khi commit.

## 3. Pattern: tìm chuỗi, từ và biểu thức chính quy

Mặc định, `git grep` diễn giải pattern theo basic regular expression (BRE). Có thể chọn chế độ khác tùy mục tiêu.

| Tùy chọn | Cách so khớp | Ví dụ |
|---|---|---|
| Mặc định / `-G` | Basic regular expression | `git grep 'foo.*bar'` |
| `-E` | Extended regular expression | `git grep -E 'foo|bar'` |
| `-F` | Chuỗi cố định, không diễn giải regex | `git grep -F 'a.b()'` |
| `-P` | Perl-compatible regular expression, nếu Git được build hỗ trợ PCRE | `git grep -P '\\btoken_[0-9]+\\b'` |

### 3.1. Tìm chuỗi literal bằng `-F`

Nếu muốn tìm đúng ký tự, không cần regex:

```bash
git grep -n -F "user.id"
```

Lệnh tìm chuỗi `user.id` với dấu chấm đúng nghĩa ký tự chấm. Nếu dùng regex mặc định, dấu `.` có ý nghĩa wildcard và có thể khớp ký tự khác.

### 3.2. Tìm nhiều lựa chọn bằng `-E`

```bash
git grep -n -E "timeout|connection refused|access denied" -- src/
```

`|` trong extended regex biểu diễn lựa chọn. Có thể dùng ngoặc để nhóm pattern:

```bash
git grep -n -E "(TODO|FIXME):" -- src/
```

### 3.3. Không phân biệt chữ hoa/thường bằng `-i`

```bash
git grep -n -i "authorization"
```

Tùy chọn `-i` giúp tìm cả `Authorization`, `AUTHORIZATION` và `authorization`. Khi tên symbol có phân biệt hoa/thường, chỉ dùng tùy chọn này nếu muốn tìm rộng hơn.

### 3.4. Tìm từ hoàn chỉnh bằng `-w`

```bash
git grep -n -w "id"
```

`-w` giới hạn kết quả ở những match nằm trên ranh giới từ. Nó giúp tránh việc tìm `id` đồng thời khớp trong `identity` hoặc `grid`, tùy định nghĩa word character của regex engine.

### 3.5. Đảo điều kiện bằng `-v`

```bash
git grep -n -v "deprecated" -- config/
```

`-v` hiển thị các dòng không khớp pattern. Đây là phép lọc theo từng dòng trong các tệp được tìm, không phải cách loại toàn bộ file khỏi tập tìm kiếm.

### 3.6. Truyền pattern bằng `-e`

`-e` chỉ rõ đối số tiếp theo là pattern. Dùng nó khi pattern bắt đầu bằng dấu `-` hoặc khi truyền nhiều pattern:

```bash
git grep -n -e "TODO" -e "FIXME" -- src/
git grep -n -e "-draft" -- docs/
```

Có thể đọc pattern từ file bằng `-f`:

```bash
git grep -n -f patterns.txt -- src/
```

Mỗi dòng trong file pattern được dùng làm một pattern tìm kiếm. Hãy lưu ý quy tắc regex đang được chọn; nếu cần tìm literal, cân nhắc `-F`.

## 4. Giới hạn phạm vi bằng pathspec

Pattern quyết định **nội dung nào** được tìm; pathspec quyết định **những đường dẫn nào** được quét. Hai khái niệm này khác nhau.

Ví dụ:

```bash
git grep -n -F "PaymentService" -- src/
```

- `PaymentService` là pattern nội dung.
- `src/` là pathspec giới hạn thư mục.

### 4.1. Tìm trong một tệp hoặc thư mục

```bash
git grep -n "connect" -- src/api/client.js
git grep -n "connect" -- src/api/
```

### 4.2. Tìm từ gốc repository bằng `:(top)`

Pathspec thông thường được tính từ thư mục hiện tại. Nếu script hoặc terminal có thể chạy từ thư mục con, dùng magic `top` để tính đường dẫn từ gốc repository:

```bash
git grep -n "connect" -- ':(top)src/api/'
```

Dạng rút gọn:

```bash
git grep -n "connect" -- :/src/api/
```

### 4.3. Dùng glob để chọn nhiều tệp

Quote pattern để shell không mở rộng trước khi Git nhận:

```bash
git grep -n "TODO" -- ':(glob)**/*.js'
git grep -n "password" -- ':(glob)config/**/*.yml'
```

Trong glob pathspec, `*` và `?` khớp trong một thành phần đường dẫn; `**` hỗ trợ khớp qua nhiều cấp thư mục.

### 4.4. Loại trừ thư mục

Có thể kết hợp pathspec dương với pathspec exclude:

```bash
git grep -n "TODO" -- ':(top)src' ':(exclude,top)src/generated'
```

Lệnh tìm trong `src/` nhưng loại `src/generated/`. Kiểm tra cú pháp pathspec nếu dùng nhiều pattern loại trừ hoặc wildcard phức tạp.

### 4.5. Xử lý tên đường dẫn bắt đầu bằng dấu `-`

Đặt `--` trước danh sách pathspec để Git không hiểu tên tệp là option:

```bash
git grep -n -F -e "TODO" -- -draft.txt
```

Nếu tên có wildcard nhưng cần khớp literal, dùng `:(literal)`:

```bash
git grep -n -F -e "draft" -- ':(literal)[draft].txt'
```

## 5. Đọc kết quả tìm kiếm

### 5.1. Hiển thị số dòng

```bash
git grep -n "handleRequest"
```

`-n` thêm số dòng để bạn mở đúng vị trí trong editor.

### 5.2. Chỉ hiển thị tên tệp

```bash
git grep -l "TODO"
```

`-l` (lowercase L) chỉ liệt kê tệp có ít nhất một match. Tùy chọn này hữu ích khi cần biết những tệp nào chứa nội dung cần rà soát.

Ngược lại, `-L` liệt kê tệp không có match:

```bash
git grep -L "TODO" -- src/
```

### 5.3. Đếm số dòng khớp theo tệp

```bash
git grep -c "TODO" -- src/
```

`-c` in số dòng khớp trong từng tệp. Đây là số dòng có match, không nhất thiết là tổng số lần pattern xuất hiện nếu một dòng có nhiều match.

### 5.4. Chỉ in phần khớp

```bash
git grep -o -E "[A-Z][A-Z0-9_]{2,}" -- src/
```

`-o` chỉ in phần nội dung khớp pattern thay vì cả dòng. Có thể kết hợp với regex để liệt kê identifier hoặc mã lỗi.

### 5.5. Hiển thị ngữ cảnh quanh dòng khớp

```bash
git grep -n -C 2 "retry" -- src/
```

- `-C 2`: hiển thị hai dòng trước và sau.
- `-A 3`: hiển thị ba dòng phía sau.
- `-B 3`: hiển thị ba dòng phía trước.

Ngữ cảnh giúp hiểu cách biến hoặc hàm được dùng mà không cần mở ngay toàn bộ tệp.

### 5.6. Hiển thị tên hàm hoặc tiêu đề function context

```bash
git grep -n -p "throw new Error" -- src/
```

`-p` cố gắng hiển thị tên function chứa match theo quy tắc nhận diện của Git cho loại tệp/driver tương ứng. Kết quả phụ thuộc cấu hình function context và ngôn ngữ; không phải parser ngữ nghĩa đầy đủ.

### 5.7. Hiển thị theo nhóm và tiêu đề

```bash
git grep --heading --break -n "TODO" -- src/
```

`--heading` nhóm kết quả theo tên tệp; `--break` chèn dòng phân cách giữa các nhóm. Đây là định dạng tiện đọc trên terminal. Nếu cần xử lý tự động, dùng định dạng output phù hợp và không parse tiêu đề trình bày.

## 6. Tìm trong lịch sử cụ thể

### 6.1. Kiểm tra chuỗi trong một phiên bản cũ

Giả sử một lỗi xuất hiện ở bản release cũ:

```bash
git grep -n -F "legacyToken" v1.2.0 -- src/
```

Lệnh tìm chuỗi literal trong snapshot của tag `v1.2.0`, chỉ giới hạn ở `src/`. Nó không đọc nội dung working tree hiện tại.

Có thể so sánh hai phiên bản bằng cách chạy hai lệnh:

```bash
git grep -n -F "legacyToken" v1.2.0 -- src/
git grep -n -F "legacyToken" v2.0.0 -- src/
```

Nếu chuỗi có trong phiên bản cũ nhưng không có trong phiên bản mới, điều đó cho biết snapshot mới không chứa chuỗi trong phạm vi đã chọn. Nó chưa cho biết commit nào đã xóa chuỗi.

### 6.2. Tìm trong một nhánh khác

```bash
git grep -n "featureFlag" origin/main -- src/
```

Lệnh tìm trong snapshot mà remote-tracking ref `origin/main` hiện tại trỏ tới. Đây là ref local được cập nhật ở lần fetch gần nhất, không phải truy vấn trực tiếp server. Nếu cần kết quả mới nhất từ remote, fetch trước:

```bash
git fetch origin
git grep -n "featureFlag" origin/main -- src/
```

### 6.3. Tìm trong commit trước đó

```bash
git grep -n "oldApi" HEAD~5 -- src/
```

Lệnh tìm trong snapshot của tổ tiên thứ nhất cách HEAD năm commit. `~5` đi theo chuỗi parent thứ nhất; với merge commit, điều này không có nghĩa là đi qua mọi nhánh lịch sử.

### 6.4. `git grep` không tự quét mọi commit

Lệnh:

```bash
git grep -n "legacyToken" -- src/
```

chỉ tìm trong working tree hiện tại. Lệnh:

```bash
git grep -n "legacyToken" HEAD -- src/
```

chỉ tìm trong snapshot HEAD. Cả hai không tự động tìm qua tất cả commit, branch và tag.

Nếu câu hỏi là “commit nào đã thêm hoặc xóa chuỗi này?”, dùng pickaxe:

```bash
git log --all -S"legacyToken" --oneline -- src/
```

`-S` tìm commit làm thay đổi số lần xuất hiện của chuỗi. Nếu cần tìm các commit có dòng thêm/xóa khớp regex:

```bash
git log --all -G"legacyToken|oldToken" --oneline -- src/
```

`-G` kiểm tra các dòng thêm/xóa có khớp regex. Hai tùy chọn này trả về commit liên quan đến thay đổi nội dung; chúng khác với việc tìm tất cả snapshot đang chứa chuỗi bằng `git grep`.

## 7. Tìm trong submodule và tệp không tracked

### 7.1. Submodule

Mặc định, tìm kiếm trong repository cha không nhất thiết đi sâu vào nội dung repository con của submodule. Có thể yêu cầu tìm đệ quy:

```bash
git grep --recurse-submodules -n "TODO"
```

Submodule cần được khởi tạo và checkout để Git có thể tìm nội dung trong working tree của chúng. Nếu submodule chưa được tải, hãy kiểm tra:

```bash
git submodule status
```

Việc tìm trong submodule phụ thuộc commit mà submodule đang checkout và trạng thái local của nó.

### 7.2. Tệp untracked

`git grep` mặc định tập trung vào tệp được Git theo dõi. Nếu cần tìm cả tệp untracked trong working tree, dùng:

```bash
git grep --untracked -n "TODO"
```

Tùy chọn `--untracked` mở rộng phạm vi tìm tới các tệp chưa được theo dõi. Tệp bị ignore theo quy tắc chuẩn thường vẫn bị loại trừ; `--no-exclude-standard` có thể thay đổi việc áp dụng các quy tắc exclude/ignore trong trường hợp cần thiết.

Nếu muốn tìm trong các tệp của thư mục hiện tại mà không dùng cơ chế theo dõi của Git, có thể dùng `--no-index`:

```bash
git grep --no-index -n "TODO" .
```

`--no-index` chuyển sang tìm tệp trong filesystem như một công cụ grep thông thường. Nó không phải lựa chọn thay thế cho tìm kiếm snapshot đã commit.

## 8. Binary, encoding và giới hạn tìm kiếm

### 8.1. Tệp nhị phân

Các tệp nhị phân có thể chứa byte không phải văn bản và làm kết quả tìm kiếm khó đọc. `git grep` có các tùy chọn:

```bash
git grep -I "pattern"
git grep -a "pattern"
```

- `-I` bỏ qua nội dung tệp được nhận diện là binary.
- `-a` xử lý binary như văn bản.

Mặc định, Git có thể nhận diện binary và tránh in nội dung như văn bản thông thường. Chỉ dùng `-a` khi hiểu định dạng tệp và muốn tìm byte/text trong nội dung đó.

### 8.2. Attribute `binary` và textconv

`.gitattributes` có thể đánh dấu tệp là binary hoặc cấu hình `textconv` để chuyển nội dung sang dạng văn bản dễ tìm/so sánh. Hành vi cụ thể phụ thuộc lệnh, driver và cấu hình. `git grep` không phải lúc nào cũng áp dụng bộ chuyển đổi như công cụ diff; nếu cần tìm trong nội dung đã chuyển đổi, hãy kiểm tra khả năng hỗ trợ của phiên bản Git và driver đang dùng.

### 8.3. Encoding

`git grep` làm việc với byte nội dung được lưu hoặc đọc từ working tree/index/tree. Nếu tệp dùng encoding khác UTF-8, ký tự hiển thị có thể khó đọc hoặc pattern Unicode không khớp như mong đợi. Kiểm tra encoding và các thuộc tính như `working-tree-encoding` khi kết quả bất thường.

### 8.4. Tệp bị xóa khỏi working tree

Nếu tệp tracked đã bị xóa khỏi working tree nhưng vẫn tồn tại trong HEAD hoặc index, tìm kiếm mặc định không thể đọc nội dung hiện tại của tệp đó. Hãy tìm trong trạng thái còn giữ nội dung:

```bash
git grep --cached -n "pattern" -- path/to/file
git grep -n "pattern" HEAD -- path/to/file
```

## 9. Mã thoát và cách dùng trong script

`git grep` dùng mã thoát để phân biệt có match, không có match và lỗi thực thi:

| Exit status | Ý nghĩa |
|---:|---|
| `0` | Có ít nhất một match. |
| `1` | Không tìm thấy match. |
| Lớn hơn `1` | Có lỗi thực thi hoặc lỗi truy cập/đọc dữ liệu. |

Vì `1` là kết quả tìm kiếm bình thường, không nên coi mọi mã khác `0` đều là lỗi nghiêm trọng.

### 9.1. Kiểm tra pattern có tồn tại không

Trong Bash/POSIX shell:

```bash
if git grep -q -F -e "TODO" -- src/; then
    printf '%s\n' "Có TODO trong src/."
else
    rc=$?
    if [ "$rc" -eq 1 ]; then
        printf '%s\n' "Không có TODO trong src/."
    else
        printf '%s\n' "Không thể tìm kiếm trong repository." >&2
        exit "$rc"
    fi
fi
```

`-q` dừng sau khi tìm thấy match và không in kết quả thông thường. Script vẫn cần phân biệt mã `1` (không match) với mã lớn hơn `1` (lỗi).

### 9.2. Kiểm tra trong PowerShell

```powershell
git grep -q -F -e 'TODO' -- src/
$gitExitCode = $LASTEXITCODE

if ($gitExitCode -eq 0) {
    Write-Output 'Có TODO trong src/.'
}
elseif ($gitExitCode -eq 1) {
    Write-Output 'Không có TODO trong src/.'
}
else {
    [Console]::Error.WriteLine("Không thể tìm kiếm. Git exit code: $gitExitCode")
    exit $gitExitCode
}
```

Lưu `$LASTEXITCODE` ngay sau lệnh Git vì chương trình native tiếp theo có thể ghi đè giá trị.

### 9.3. Không parse output trình bày nếu có định dạng phù hợp hơn

Nếu script cần danh sách tệp, dùng tùy chọn chỉ tên tệp hoặc output phù hợp; không dựa vào cách xuống dòng hoặc tiêu đề terminal. Tên tệp có thể chứa dấu cách, tab hoặc newline. Khi chuyển danh sách đường dẫn qua các lệnh khác, ưu tiên cơ chế NUL-safe và parser hỗ trợ byte NUL.

## 10. Quy trình tìm kiếm trong một phiên bản được theo dõi

Giả sử cần xác định `refreshToken` đang được dùng ở đâu và liệu thay đổi mới đã được stage chưa.

**Bước 1: Tìm trong working tree**

```bash
git grep -n -F -e "refreshToken" -- src/
```

**Bước 2: Tìm trong index**

```bash
git grep --cached -n -F -e "refreshToken" -- src/
```

**Bước 3: Tìm trong commit hiện tại**

```bash
git grep -n -F -e "refreshToken" HEAD -- src/
```

**Bước 4: Tìm trong release cũ**

```bash
git grep -n -F -e "refreshToken" v1.3.0 -- src/
```

**Bước 5: Nếu cần biết commit nào đã thay đổi chuỗi**

```bash
git log --all -S"refreshToken" --oneline -- src/
```

Kết quả bốn bước đầu cho biết chuỗi hiện diện trong từng snapshot nào. Bước cuối chuyển câu hỏi sang lịch sử thay đổi và liệt kê các commit làm số lần xuất hiện của chuỗi thay đổi.

## 11. Các lỗi thường gặp

### 11.1. Tìm không thấy dù editor đang hiển thị chuỗi

Kiểm tra bạn đang tìm trong đúng trạng thái chưa. Nếu tệp untracked, mặc định có thể không được tìm; dùng `--untracked` hoặc stage tệp nếu đó là nội dung sẽ commit. Nếu tệp đã bị xóa khỏi working tree, tìm trong `--cached` hoặc `HEAD`.

### 11.2. Kết quả khác với commit đã push

`git grep` mặc định tìm working tree hiện tại, không phải remote. Dùng tree-ish như `origin/main` sau khi fetch nếu muốn kiểm tra remote-tracking snapshot.

### 11.3. Pattern có dấu chấm hoặc ký tự regex

Nếu muốn tìm đúng chuỗi literal, dùng `-F`. Nếu muốn regex, chọn `-E`, `-G` hoặc `-P` phù hợp. Không giả định dấu chấm, dấu ngoặc hoặc dấu `*` luôn được hiểu là ký tự thường.

### 11.4. Pathspec không khớp

Kiểm tra thư mục hiện tại, quote pattern và dùng `:(top)` nếu muốn tính từ gốc repository. Dấu `--` phân tách pathspec khỏi các đối số trước đó.

### 11.5. Script coi không có match là lỗi

Mã `1` có nghĩa là không có match. Xử lý riêng mã `1`; chỉ coi mã lớn hơn `1` là lỗi thực thi.

### 11.6. Nghĩ `git grep` đã quét toàn bộ lịch sử

Không. Chỉ định tree-ish để tìm trong một snapshot. Dùng `git log -S` hoặc `git log -G` khi cần tìm commit đã thêm/xóa/thay đổi pattern.

## 12. Ghi nhớ

- `git grep` tìm nội dung theo pattern trong các tệp Git theo dõi.
- Mặc định tìm nội dung working tree; `--cached` tìm index; `<tree-ish>` tìm snapshot của commit/tag/tree.
- `git grep` không tự quét mọi commit trong lịch sử.
- Pattern nội dung khác pathspec chọn đường dẫn; `--` phân tách pathspec.
- Dùng `-F` cho chuỗi literal, `-E` cho extended regex, `-i` không phân biệt hoa/thường, `-w` tìm từ hoàn chỉnh.
- Dùng `-n`, `-l`, `-L`, `-c`, `-o`, `-A`, `-B`, `-C` để điều khiển kết quả.
- Quote wildcard pathspec; dùng `:(top)`, `:(glob)` và `:(exclude)` để kiểm soát phạm vi.
- `--untracked` mở rộng tìm kiếm tới tệp untracked; `--no-index` tìm trong filesystem không dựa vào index Git.
- `--recurse-submodules` tìm thêm trong submodule đã được checkout.
- Exit status `0` là có match, `1` là không match, lớn hơn `1` là lỗi.
- Dùng `git log -S` hoặc `git log -G` khi câu hỏi là commit nào đã thay đổi chuỗi qua lịch sử.

Khi tìm một symbol hoặc thông báo, hãy xác định trước bạn cần nội dung đang sửa, nội dung đã stage hay snapshot của commit nào. Chọn đúng nguồn dữ liệu rồi mới chọn pattern và pathspec; như vậy kết quả `git grep` sẽ trả lời đúng câu hỏi thay vì trộn lẫn các phiên bản khác nhau.
