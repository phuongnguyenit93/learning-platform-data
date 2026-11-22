# Dùng Git trong script với git status --porcelain và dấu phân cách NUL

Script tự động hóa thường cần biết repository có file nào thay đổi, file nào chưa được theo dõi và có xung đột hay không. Lệnh `git status` dành cho người dùng hiển thị thông tin dễ đọc, nhưng định dạng đó có thể thay đổi theo cấu hình, màu sắc, cách trích dẫn đường dẫn và độ rộng terminal. Khi viết script, hãy dùng **porcelain format** được thiết kế cho máy đọc.

Với tên file có dấu cách, tab, dấu nháy hoặc ký tự xuống dòng, phân tích đầu ra theo từng dòng vẫn có thể làm sai dữ liệu. Tùy chọn `-z` yêu cầu Git kết thúc mỗi trường đường dẫn bằng byte NUL. Vì tên file trên các hệ thống file thông thường không thể chứa byte NUL, đây là dấu phân cách an toàn để script đọc nguyên vẹn đường dẫn.

## 1. Vì sao script nên dùng porcelain?

Đầu ra mặc định của:

```bash
git status
```

được tối ưu cho con người. Git có thể nhóm file theo khu vực, tô màu, rút gọn thông tin hoặc trích dẫn tên file tùy cấu hình. Script dựa vào câu chữ như `Changes to be committed` hay `Untracked files` rất dễ hỏng khi Git thay đổi cách trình bày hoặc khi môi trường dùng ngôn ngữ/cấu hình khác.

Dùng:

```bash
git status --porcelain
```

Git trả về định dạng ngắn, ổn định hơn dành cho script. `--porcelain` hiện tương đương với `--porcelain=v1`. Khi viết automation, nên chỉ rõ phiên bản:

```bash
git status --porcelain=v1
```

Việc pin phiên bản giúp người đọc biết chính xác cấu trúc record mà script đang phân tích. Git cũng có porcelain v2 với nhiều trường metadata hơn; chọn v1 hoặc v2 có chủ đích và viết parser theo đúng phiên bản đó.

Porcelain chỉ thay đổi định dạng đầu ra. Nó không tự stage file, không commit, không sửa working tree và không thay thế các lệnh kiểm tra nội dung.

## 2. Đọc cấu trúc porcelain v1

Một record thông thường của porcelain v1 có dạng:

```text
XY PATH
```

Hai ký tự `X` và `Y` mô tả trạng thái của đường dẫn:

- `X`: trạng thái trong index, so với commit `HEAD`.
- `Y`: trạng thái trong working tree, so với index.

Ví dụ:

```text
 M src/App.java
M  README.md
A  src/NewService.java
?? tmp/output.txt
D  old-config.yml
```

Diễn giải:

| Mã | Ý nghĩa |
|---|---|
| ` M` | File tracked bị sửa trong working tree, chưa stage thay đổi đó |
| `M ` | Thay đổi file đã được stage trong index |
| `MM` | File đã stage một phần thay đổi và sau đó tiếp tục bị sửa trong working tree |
| `A ` | File mới đã được stage |
| `D ` | File đã bị xóa và việc xóa đã được stage |
| ` D` | File tracked bị xóa trong working tree, chưa stage |
| `??` | File chưa được theo dõi |
| `!!` | File bị ignore; chỉ xuất hiện khi yêu cầu hiển thị ignored files |

Các ký tự trạng thái thường gặp gồm:

- Dấu cách: không có thay đổi ở phía tương ứng.
- `M`: modified.
- `A`: added.
- `D`: deleted.
- `R`: renamed.
- `C`: copied.
- `U`: unmerged.
- `?`: untracked hoặc trạng thái đặc biệt theo định dạng.
- `!`: ignored.

Với conflict, porcelain v1 có thể trả các cặp như `DD`, `AU`, `UD`, `UA`, `DU`, `AA` và `UU`. Chúng cho biết tình trạng xung đột giữa index và working tree; script thường nên coi mọi trạng thái có `U` hoặc các mã unmerged đã biết là cần xử lý thủ công.

Đừng chỉ kiểm tra một ký tự cố định ở vị trí đầu. Hãy đọc cả hai cột để phân biệt thay đổi đã stage với thay đổi chưa stage.

## 3. Vì sao cần dấu phân cách NUL?

Tên file hợp lệ có thể chứa dấu cách, tab và ký tự xuống dòng. Ví dụ các tên sau đều có thể xuất hiện trong repository:

```text
notes meeting.txt
reports/line
break.txt
quotes/"draft".md
```

Nếu script tách đầu ra theo dòng, file có newline trong tên sẽ bị hiểu nhầm thành hai record. Nếu tách theo khoảng trắng, tên file có dấu cách sẽ bị chia thành nhiều phần.

Dùng tùy chọn `-z`:

```bash
git status --porcelain=v1 -z
```

Khi đó:

- Mỗi record được kết thúc bằng byte NUL (`\0`), không phải newline.
- Đường dẫn không được quote hoặc escape theo `core.quotePath`; Git ghi nguyên byte của pathname.
- Với record rename/copy, dấu `->` bị bỏ và thứ tự hai pathname được đảo so với dạng hiển thị thông thường: đường dẫn đích đứng trước, đường dẫn nguồn đứng sau, mỗi đường dẫn kết thúc bằng NUL.

Byte NUL không thể xuất hiện trong tên file trên các hệ thống file mà Git hỗ trợ theo cách thông thường, nên parser có thể dùng nó làm ranh giới rõ ràng. Điều này giúp xử lý đúng tên file chứa newline, tab, dấu cách, dấu nháy hoặc byte không phải UTF-8.

Lệnh thường dùng trong script:

```bash
git status --porcelain=v1 -z --untracked-files=all
```

`--untracked-files=all` yêu cầu liệt kê từng file chưa theo dõi thay vì chỉ hiển thị thư mục untracked ở dạng gộp. Điều này hữu ích nếu automation cần quyết định theo từng file.

## 4. Hiểu record rename và copy khi dùng -z

Không có `-z`, record rename thường được hiển thị theo dạng:

```text
R  old-name.txt -> new-name.txt
```

Khi dùng `-z`, Git không xuất chuỗi `->` và đảo thứ tự hai đường dẫn:

```text
R  new-name.txt\0old-name.txt\0
```

Trong biểu diễn trên, `\0` là ký hiệu minh họa cho một byte NUL thực tế. Đường dẫn đầu tiên là tên mới/đích; đường dẫn tiếp theo là tên cũ/nguồn.

Vì vậy, parser không thể giả định mỗi record luôn chỉ chứa một pathname. Khi hai ký tự trạng thái có `R` hoặc `C`, cần đọc thêm một pathname NUL-delimited để lấy đường dẫn nguồn.

Git có thể phát hiện rename dựa trên cấu hình và nội dung file. Nếu automation không cần phân biệt rename và muốn nhận các thay đổi xóa/thêm đơn giản hơn, có thể tắt rename detection:

```bash
git status --porcelain=v1 -z --no-renames
```

Đây là lựa chọn về logic của script. Nếu cần giữ quan hệ đổi tên để đồng bộ hoặc audit, hãy bật rename detection và xử lý đủ hai pathname.

## 5. Các tùy chọn status hữu ích cho automation

| Tùy chọn | Mục đích |
|---|---|
| `--porcelain=v1` | Chọn định dạng máy đọc v1 |
| `--porcelain=v2` | Chọn định dạng máy đọc v2 có metadata phong phú hơn |
| `-z` | Dùng NUL làm dấu kết thúc pathname/record |
| `--untracked-files=all` | Liệt kê từng file untracked |
| `--ignored` | Bao gồm cả file ignored |
| `--ignore-submodules=none` | Hiển thị mọi thay đổi submodule khi kiểm tra |
| `--no-renames` | Không phát hiện rename; thay đổi được biểu diễn đơn giản hơn |
| `--branch` | Thêm thông tin branch vào porcelain v2 |
| `--` | Kết thúc tùy chọn và bắt đầu pathspec |

Ví dụ chỉ kiểm tra một thư mục:

```bash
git status --porcelain=v1 -z --untracked-files=all -- src/
```

Ví dụ bao gồm cả file ignored:

```bash
git status --porcelain=v1 -z --untracked-files=all --ignored
```

Ví dụ buộc hiển thị trạng thái bên trong submodule:

```bash
git status --porcelain=v1 -z --ignore-submodules=none
```

Chỉ thêm tùy chọn phù hợp với mục tiêu. Ví dụ, nếu script chỉ muốn biết thay đổi được theo dõi để chạy test, có thể không cần liệt kê file ignored. Nếu cần dọn hoặc báo cáo file untracked, hãy dùng `--untracked-files=all`.

## 6. Phân tích NUL-delimited output bằng Bash

Trong Bash, `read` có thể đọc tới byte NUL bằng `-d ''`. Kết hợp `-r` để giữ nguyên dấu gạch chéo ngược trong tên file.

Ví dụ script đọc porcelain v1, nhận diện untracked/ignored và xử lý rename/copy:

```bash
#!/usr/bin/env bash
set -euo pipefail

repo=${1:-.}
tmp=$(mktemp)
trap 'rm -f "$tmp"' EXIT

# Ghi output dạng byte vào file; không lưu NUL trong biến shell.
git -C "$repo" status --porcelain=v1 -z \
  --untracked-files=all --ignored > "$tmp"

while IFS= read -r -d '' record; do
  # Hai ký tự đầu là XY; ký tự thứ ba là dấu cách phân cách.
  xy=${record:0:2}
  path=${record:3}

  case "$xy" in
    "??")
      printf 'untracked: %q\n' "$path"
      ;;
    "!!")
      printf 'ignored: %q\n' "$path"
      ;;
    *R*|*C*)
      # Với -z, pathname đầu là đích; pathname kế tiếp là nguồn.
      if ! IFS= read -r -d '' source_path; then
        printf 'Missing source pathname for rename/copy\n' >&2
        exit 1
      fi
      printf '%s: %q -> %q\n' "$xy" "$source_path" "$path"
      ;;
    *)
      printf '%s %q\n' "$xy" "$path"
      ;;
  esac
done < "$tmp"
```

Một số điểm cần chú ý:

- Script ghi output ra file tạm trước để kiểm tra mã thoát của `git status`. Nếu Git thất bại, `set -e` dừng script trước khi parser chạy.
- Không dùng command substitution như `output=$(git status -z)` vì shell không thể lưu byte NUL trong biến.
- `IFS= read -r -d ''` đọc nguyên pathname tới NUL; `-r` tránh diễn giải dấu gạch chéo ngược.
- `%q` hiển thị pathname theo dạng escape an toàn trong log Bash, giúp nhìn thấy newline hoặc tab.
- Với rename/copy, parser đọc thêm trường pathname thứ hai. Nếu bỏ qua trường này, lần đọc tiếp theo sẽ hiểu nhầm source path thành một record mới.

Nếu không cần phân biệt rename/copy, có thể thêm `--no-renames` vào lệnh status và bỏ nhánh đọc pathname thứ hai. Khi đó mỗi record chỉ có một pathname.

## 7. Phân tích bằng Python mà vẫn giữ nguyên pathname

Python nên nhận stdout dưới dạng bytes thay vì chuyển thành chuỗi rồi tách theo dòng. `subprocess.run` với `stdout=subprocess.PIPE` giữ nguyên byte NUL và byte pathname.

Ví dụ parser porcelain v1:

```python
import os
import subprocess

result = subprocess.run(
    [
        "git", "status",
        "--porcelain=v1",
        "-z",
        "--untracked-files=all",
        "--ignored",
    ],
    check=True,
    stdout=subprocess.PIPE,
)

# Mỗi phần tử là bytes; pathname không bị tách theo newline.
records = result.stdout.split(b"\0")
if records and records[-1] == b"":
    records.pop()

i = 0
while i < len(records):
    record = records[i]
    i += 1

    if len(record) < 3 or record[2:3] != b" ":
        raise ValueError(f"Unexpected porcelain record: {record!r}")

    xy = record[:2].decode("ascii")
    path = record[3:]

    if "R" in xy or "C" in xy:
        if i >= len(records):
            raise ValueError("Missing source path for rename/copy")
        source_path = records[i]
        i += 1
        print(
            f"{xy}: {os.fsdecode(source_path)!r} "
            f"-> {os.fsdecode(path)!r}"
        )
    else:
        print(f"{xy} {os.fsdecode(path)!r}")
```

`check=True` làm Python báo lỗi nếu Git trả mã thoát khác 0. `split(b"\0")` chia theo byte NUL, không phụ thuộc newline trong pathname. `os.fsdecode` chuyển pathname bytes theo filesystem encoding của môi trường; dùng `repr` trong ví dụ để newline và ký tự đặc biệt được hiển thị rõ.

Nếu ứng dụng cần lưu hoặc truyền pathname tiếp cho một lệnh khác, hãy giữ dữ liệu ở dạng bytes hoặc dùng API nhận danh sách argument thay vì ghép pathname vào một chuỗi lệnh shell.

## 8. Porcelain v2: khi cần thêm metadata

Porcelain v2 cung cấp cấu trúc chi tiết hơn v1. Có thể yêu cầu:

```bash
git status --porcelain=v2 -z --branch
```

Đầu ra có các loại record chính:

| Loại record | Ý nghĩa |
|---|---|
| `#` | Header metadata, ví dụ branch OID, tên branch, upstream và ahead/behind |
| `1` | Thay đổi thông thường của một đường dẫn |
| `2` | Rename hoặc copy; record có thêm thông tin nguồn/đích |
| `u` | Đường dẫn đang ở trạng thái unmerged, có metadata cho các stage |
| `?` | Đường dẫn untracked |
| `!` | Đường dẫn ignored khi được yêu cầu |

Record loại `1` chứa trạng thái XY, thông tin submodule, mode và OID liên quan. Record loại `2` có thêm score cho rename/copy và pathname thứ hai. Record `u` chứa các mode/OID của các phía xung đột. Header `#` xuất hiện khi yêu cầu metadata như `--branch`.

Porcelain v2 hữu ích nếu automation cần phân biệt loại record, trạng thái submodule hoặc lấy thông tin ahead/behind mà không chạy nhiều lệnh riêng. Tuy nhiên, parser phải hiểu đúng từng loại record; không được áp dụng parser v1 cho v2 vì v2 có tiền tố record và số trường khác nhau.

Khi dùng `-z`, pathname trong các record v2 vẫn được kết thúc bằng NUL. Với rename/copy, pathname đích và nguồn được tách riêng. Hãy đọc tài liệu định dạng v2 và viết parser theo từng record type thay vì tách chuỗi theo khoảng trắng một cách tùy tiện.

Nếu chỉ cần biết file nào thay đổi để chạy formatter hoặc test, porcelain v1 thường đủ và parser đơn giản hơn. Nếu cần báo cáo trạng thái branch, submodule và conflict chi tiết, cân nhắc v2.

## 9. Những cách parse không an toàn

Tránh các cách sau:

```bash
# Không an toàn: tên file có dấu cách/newline sẽ bị tách
for file in $(git status --short); do
  echo "$file"
done

# Không an toàn: đọc theo dòng, pathname có thể chứa newline
git status --porcelain | while read line; do
  ...
done

# Không an toàn: biến shell không lưu được byte NUL
output=$(git status --porcelain -z)
```

Các vấn đề cụ thể:

- Command substitution loại bỏ newline ở cuối và shell word splitting có thể chia pathname.
- `read` mặc định đọc tới newline, không phải NUL.
- Tên file có thể chứa ký tự tab hoặc newline, nên một dòng không tương đương một file.
- Byte NUL không thể được giữ trong biến shell thông thường.
- Nếu parser giả định record luôn có một pathname, rename/copy sẽ làm lệch toàn bộ dữ liệu phía sau.

Cách an toàn là dùng `-z`, đọc tới NUL và xử lý đầy đủ cấu trúc record. Nếu không muốn tự viết parser, hãy gọi Git qua API hoặc thư viện có hỗ trợ định dạng porcelain/NUL và giữ pathname dưới dạng mảng argument.

## 10. Exit code của git status không phải trạng thái sạch/bẩn

Một lỗi phổ biến trong automation là coi mã thoát `0` của `git status` có nghĩa working tree sạch. Thực tế, `git status` thường trả mã thoát `0` cả khi có file modified, staged, untracked hoặc conflict. Nội dung stdout mới cho biết trạng thái repository.

Ví dụ:

```bash
if git status --porcelain=v1 -z > status.bin; then
  # Lệnh status chạy thành công; cần đọc status.bin để biết có thay đổi không.
  :
else
  echo "Không thể đọc trạng thái Git" >&2
  exit 1
fi
```

Nếu file output rỗng, không có record nào trong phạm vi tùy chọn đã yêu cầu. Nếu có record, cần phân tích trạng thái để biết đó là thay đổi nào. Ví dụ, khi dùng `--ignored`, file ignored cũng tạo record `!!`; vì vậy “output không rỗng” không nhất thiết có nghĩa có thay đổi cần commit.

Tốt nhất là xác định rõ mục tiêu trước khi kiểm tra:

- Muốn biết có thay đổi tracked/untracked cần xử lý? Không thêm `--ignored`, hoặc lọc `!!`.
- Muốn biết có file ignored? Thêm `--ignored` và nhận diện `!!`.
- Muốn chặn pipeline nếu có conflict? Phân tích XY và nhận diện trạng thái unmerged.
- Muốn biết Git có chạy lệnh status thành công không? Kiểm tra exit code riêng.

Không dùng một điều kiện boolean duy nhất cho mọi mục đích.

## 11. Phạm vi kiểm tra và ảnh hưởng của cấu hình

Kết quả status phụ thuộc vào các tùy chọn bạn truyền vào và một số cấu hình repository:

- `status.showUntrackedFiles` ảnh hưởng cách hiển thị file chưa theo dõi khi không chỉ định rõ.
- `status.renames` ảnh hưởng phát hiện rename.
- Cấu hình `submodule.<name>.ignore` có thể ảnh hưởng cách `git status` hiển thị thay đổi submodule; cấu hình `diff.ignoreSubmodules` ảnh hưởng các lệnh diff.
- Pathspec giới hạn các đường dẫn được kiểm tra.
- `--ignored` thay đổi tập record được trả về.

Với automation cần kết quả có thể dự đoán, nên chỉ rõ các tùy chọn quan trọng:

```bash
git status --porcelain=v1 -z \
  --untracked-files=all \
  --ignore-submodules=none
```

Nếu muốn bỏ qua file ignored, không thêm `--ignored`. Nếu muốn kiểm tra riêng một thư mục, thêm dấu `--` rồi đến pathspec:

```bash
git status --porcelain=v1 -z -- src/
```

Dùng `git config --show-origin --get-regexp '^status\.'` để xem các cấu hình status có thể tác động tới kết quả. Dù porcelain ổn định cho script, các tùy chọn khác nhau vẫn có thể làm tập đường dẫn được trả về khác nhau.

## 12. Quy trình thiết kế script đọc trạng thái Git

Một quy trình an toàn có thể áp dụng cho Bash, Python hoặc công cụ tự động hóa khác:

1. **Chọn phiên bản porcelain.** Dùng `--porcelain=v1` nếu cần parser đơn giản; chọn v2 nếu cần metadata chi tiết.
2. **Chọn phạm vi.** Xác định có cần untracked, ignored, submodule và pathspec hay không.
3. **Dùng NUL.** Thêm `-z` nếu pathname được chuyển vào chương trình.
4. **Kiểm tra exit code của Git.** Phân biệt lỗi khi chạy lệnh với repository có thay đổi.
5. **Parse theo record.** Đọc hai cột XY và xử lý rename/copy với pathname thứ hai.
6. **Giữ nguyên pathname.** Không tách theo khoảng trắng/newline và không lưu NUL vào biến shell.
7. **Hành động có giới hạn.** Nếu script stage, xóa hoặc chạy formatter, chỉ tác động tới các đường dẫn đã được phân loại rõ.
8. **Kiểm tra sau thao tác.** Chạy lại porcelain để xác minh trạng thái cuối.

Một script chỉ báo cáo trạng thái nên có quyền hạn tối thiểu: đọc repository và in kết quả. Nếu script tự động stage hoặc commit, hãy tách bước đó thành logic riêng, ghi rõ file được chọn và cung cấp chế độ dry-run khi phù hợp.

## 13. Những lỗi thường gặp khi dùng porcelain

| Hiện tượng | Nguyên nhân | Cách khắc phục |
|---|---|---|
| Tên file có dấu cách bị tách thành nhiều phần | Dùng split theo khoảng trắng hoặc shell word splitting | Dùng `-z` và đọc pathname tới NUL |
| Tên file có newline làm parser lệch record | Đọc theo từng dòng | Dùng NUL-delimited records |
| Rename tạo ra một record “lạ” tiếp theo | Parser chỉ đọc một pathname | Khi XY có R/C, đọc thêm pathname nguồn |
| Tên Unicode hiển thị dạng escape | Đầu ra không dùng `-z` hoặc `core.quotePath` đang bật | Dùng `-z` cho dữ liệu máy; không phụ thuộc cách hiển thị |
| Script nghĩ repository sạch dù có file sửa | Chỉ kiểm tra exit code | Phân tích stdout; exit code chỉ cho biết lệnh có chạy thành công |
| File untracked trong thư mục không được liệt kê | Git đang gộp untracked theo thư mục | Dùng `--untracked-files=all` |
| Không thấy thay đổi bên trong submodule | Ignore setting đang lọc trạng thái | Dùng `--ignore-submodules=none` và kiểm tra trong repository con |
| Parser v1 không đọc được đầu ra v2 | Dùng sai schema | Pin `--porcelain=v1` hoặc viết parser v2 riêng |

## Kết luận

Dùng `git status --porcelain=v1 -z` để script nhận trạng thái repository theo định dạng ổn định và pathname được phân cách bằng NUL. Đọc hai cột XY để phân biệt index với working tree; xử lý riêng record rename/copy vì chúng chứa hai pathname và thứ tự được đảo khi dùng `-z`. Không parse theo dòng, khoảng trắng hoặc command substitution. Luôn kiểm tra exit code riêng với nội dung stdout, chọn rõ phạm vi untracked/ignored/submodule và xác minh lại trạng thái sau khi automation thực hiện hành động.
