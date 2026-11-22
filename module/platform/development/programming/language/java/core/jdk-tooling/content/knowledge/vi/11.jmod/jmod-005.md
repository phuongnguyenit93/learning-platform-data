# Extract JMOD trong Java

## 1. JMOD là gì và khi nào cần extract?

JMOD là định dạng archive dành cho các module của nền tảng Java và các module do nhà phát triển đóng gói. Một tệp JMOD có phần class đã biên dịch cùng những thành phần bổ sung mà module có thể cần, chẳng hạn thư viện native, lệnh native, tệp cấu hình, header hoặc thông tin pháp lý.

JMOD thường xuất hiện trong thư mục `jmods` của một bộ JDK, ví dụ `java.base.jmod` hoặc `java.sql.jmod`. Nhà phát triển cũng có thể tạo JMOD riêng bằng công cụ `jmod`.

**Extract JMOD** là thao tác giải xuất toàn bộ entry của một tệp `.jmod` ra thư mục trên hệ thống tệp. Công cụ `jmod` đọc archive và giữ lại cấu trúc các section bên trong để bạn kiểm tra hoặc sử dụng cho công việc phát triển.

Các tình huống thường cần extract:

- Kiểm tra class file và `module-info.class` của một module.
- Xem cấu hình, native library, header hoặc legal notice được đóng gói cùng module.
- Điều tra nội dung của JMOD trước khi tạo runtime image bằng `jlink`.
- Kiểm tra một JMOD do nhóm phát triển hoặc nhà cung cấp tạo ra.
- Lấy một thành phần cụ thể để phân tích bằng công cụ khác sau khi đã extract.

JMOD không phải định dạng chạy ứng dụng trực tiếp. Theo tài liệu JDK, JMOD được dùng trong quá trình biên dịch hoặc liên kết module; để triển khai module thông thường, modular JAR thường là lựa chọn phù hợp. JMOD đặc biệt hữu ích khi module có native library hoặc cấu hình bổ sung, hay khi cần liên kết module vào runtime image bằng `jlink`. [Tài liệu Oracle về lệnh jmod](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmod.html)

## 2. Phân biệt JMOD, JAR và runtime image

Ba dạng này có mục đích khác nhau:

| Thành phần | Nội dung chính | Mục đích |
|---|---|---|
| JAR | Class file, resource và manifest | Phân phối thư viện hoặc ứng dụng Java; modular JAR có thể nằm trên module path |
| JMOD | Class file, module descriptor và các section bổ sung như native library, cấu hình, header, legal notice | Đóng gói module phục vụ compile-time hoặc link-time, đặc biệt với `jlink` |
| Runtime image | Các module đã được liên kết cùng runtime cần thiết | Chạy ứng dụng trên một runtime được tạo riêng |

JMOD có cấu trúc archive riêng, có thể chứa các section mà JAR thông thường không biểu diễn theo cùng cách. Vì vậy, hãy dùng `jmod extract` để giải xuất JMOD thay vì mặc định xem nó như một JAR thông thường.

Các lệnh liên quan có nhiệm vụ khác nhau:

- `jmod list`: in tên các entry đang có trong JMOD.
- `jmod describe`: hiển thị thông tin module như tên, yêu cầu và exports.
- `jmod extract`: giải xuất toàn bộ entry ra thư mục.
- `jmod create`: tạo một JMOD mới.
- `jlink`: liên kết các module thành runtime image.

## 3. Tìm tệp JMOD cần extract

Các JMOD của JDK thường nằm trong thư mục `jmods` ở thư mục gốc JDK:

```text
<JDK_HOME>/
├── bin/
│   └── jmod
├── jmods/
│   ├── java.base.jmod
│   ├── java.sql.jmod
│   ├── java.xml.jmod
│   └── ...
└── lib/
```

Một số ví dụ:

- `java.base.jmod`: module nền tảng cốt lõi, thường chứa nhiều class và thành phần native.
- `java.sql.jmod`: module liên quan đến JDBC và API SQL.
- `java.xml.jmod`: module cung cấp các API XML.

Không phải mọi bộ cài runtime đều có thư mục `jmods`. Thư mục này thường đi cùng bộ JDK đầy đủ. Nếu không tìm thấy, hãy kiểm tra `JAVA_HOME` và vị trí cài JDK đang dùng.

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command jmod -All
Test-Path (Join-Path $env:JAVA_HOME 'jmods\java.sql.jmod')
```

Trên Linux hoặc macOS:

```bash
echo "$JAVA_HOME"
command -v jmod
ls "$JAVA_HOME/jmods/java.sql.jmod"
```

`JAVA_HOME` nên trỏ đến thư mục gốc của JDK, không phải thư mục `bin`.

## 4. Cú pháp jmod extract

Cú pháp tổng quát:

```bash
jmod extract [options] <jmod-file>
```

Tùy chọn quan trọng nhất khi extract là `--dir`:

```bash
jmod extract --dir <output-directory> <module-file.jmod>
```

Ý nghĩa:

- `jmod`: gọi công cụ JMOD đi kèm JDK.
- `extract`: chọn chế độ giải xuất archive.
- `--dir`: chỉ định thư mục đích để ghi các entry được giải xuất.
- `<module-file.jmod>`: đường dẫn tới tệp JMOD nguồn.

Ví dụ:

```bash
jmod extract --dir extracted/java.sql "$JAVA_HOME/jmods/java.sql.jmod"
```

Lệnh trên giải xuất các entry của `java.sql.jmod` vào thư mục `extracted/java.sql`.

`jmod extract` giải xuất toàn bộ nội dung archive. Lệnh không có tham số chọn riêng một class hoặc một entry. Nếu chỉ cần một tệp, hãy extract vào thư mục làm việc riêng, sau đó lấy tệp cần thiết từ kết quả.

## 5. Kiểm tra JMOD trước khi extract

Trước khi giải xuất, nên xác nhận đúng tệp và xem trước danh sách entry.

### 5.1. Liệt kê nội dung bằng jmod list

```bash
jmod list "$JAVA_HOME/jmods/java.sql.jmod"
```

`jmod list` in tên các entry bên trong archive. Kết quả có thể gồm các đường dẫn như:

```text
classes/module-info.class
classes/java/sql/...
legal/...
```

Đây là ví dụ minh họa; danh sách cụ thể phụ thuộc module, phiên bản JDK và nhà cung cấp.

Lệnh `list` chỉ đọc danh sách entry, không ghi nội dung ra thư mục.

### 5.2. Xem thông tin module bằng jmod describe

```bash
jmod describe "$JAVA_HOME/jmods/java.sql.jmod"
```

`jmod describe` hiển thị metadata của module, chẳng hạn:

- Tên module.
- Những module mà nó `requires`.
- Các package được `exports`.
- Những dịch vụ mà module `uses` hoặc `provides`, nếu có.
- Thông tin phiên bản hoặc hash module trong trường hợp tương ứng.

`describe` giúp hiểu module ở mức module descriptor; nó không thay thế việc liệt kê hoặc extract các tệp bên trong.

### 5.3. Khi nào nên xem list và describe?

| Câu hỏi cần trả lời | Lệnh |
|---|---|
| JMOD chứa entry nào? | `jmod list` |
| Module có tên gì và phụ thuộc module nào? | `jmod describe` |
| Cần đọc hoặc phân tích các tệp thực tế? | `jmod extract` |

## 6. Ví dụ thực hành trên Linux và macOS

Ví dụ sử dụng JDK hiện tại để extract module `java.sql`.

Trước tiên, kiểm tra `JAVA_HOME` và tạo một thư mục đích mới, riêng biệt. Chọn thư mục chưa tồn tại để tránh trộn kết quả với các tệp cũ.

```bash
set -e

if [ -z "$JAVA_HOME" ]; then
    echo "Set JAVA_HOME to the JDK directory." >&2
    exit 1
fi

jmodFile="$JAVA_HOME/jmods/java.sql.jmod"
outDir="extracted/java.sql"

mkdir -p extracted
mkdir "$outDir"

jmod list "$jmodFile"
jmod describe "$jmodFile"
jmod extract --dir "$outDir" "$jmodFile"

find "$outDir" -type f
```

Giải thích:

1. `set -e` yêu cầu shell dừng khi một lệnh thất bại.
2. Dòng kiểm tra `JAVA_HOME` báo lỗi nếu biến chưa được đặt.
3. `jmodFile` trỏ tới JMOD nguồn trong thư mục `jmods`.
4. `outDir` là thư mục chứa kết quả.
5. `mkdir` tạo thư mục đích mới.
6. `jmod list` và `jmod describe` cho phép kiểm tra archive trước khi giải xuất.
7. `jmod extract --dir` thực hiện thao tác extract.
8. `find` liệt kê các tệp thực tế sau khi giải xuất.

Nếu JDK được cài ở vị trí khác hoặc tên module cần extract khác, thay giá trị `jmodFile` tương ứng. Không đổi đường dẫn sang một tệp JAR thông thường.

## 7. Ví dụ thực hành trên Windows PowerShell

Ví dụ sau cũng extract `java.sql.jmod` từ JDK được chỉ định bởi `JAVA_HOME`.

```powershell
$ErrorActionPreference = 'Stop'

if (-not $env:JAVA_HOME) {
    throw 'Set JAVA_HOME to the JDK directory.'
}

$jmodFile = Join-Path $env:JAVA_HOME 'jmods\java.sql.jmod'
$outDir = '.\extracted\java.sql'

if (-not (Test-Path $jmodFile)) {
    throw "JMOD file not found: $jmodFile"
}

New-Item -ItemType Directory -Path '.\extracted' -Force | Out-Null
New-Item -ItemType Directory -Path $outDir | Out-Null

jmod list $jmodFile
jmod describe $jmodFile
jmod extract --dir $outDir $jmodFile

Get-ChildItem -Path $outDir -Recurse -File
```

Ý nghĩa:

- `$env:JAVA_HOME` lấy biến môi trường JDK trong PowerShell.
- `Join-Path` tạo đường dẫn tới JMOD nguồn.
- `Test-Path` xác nhận tệp nguồn tồn tại.
- `New-Item` tạo thư mục đích.
- `jmod extract` giải xuất archive vào thư mục đã chọn.
- `Get-ChildItem -Recurse -File` liệt kê các tệp sau khi giải xuất.

Ví dụ này tạo thư mục đích mới. Nếu thư mục `.\extracted\java.sql` đã tồn tại, hãy chọn một tên thư mục mới hoặc kiểm tra nội dung hiện có trước khi chạy để tránh ghi trộn với kết quả cũ.

## 8. Cấu trúc thư mục sau khi extract

JMOD chia nội dung thành các section. Tùy module, chỉ một số section xuất hiện; không phải JMOD nào cũng có đủ mọi thư mục.

Các section thường gặp:

| Thư mục sau extract | Nội dung |
|---|---|
| `classes/` | Class file Java, bao gồm `module-info.class` nếu module có descriptor |
| `conf/` | Tệp cấu hình có thể chỉnh sửa |
| `include/` | Header file, thường liên quan đến native interface |
| `legal/` | License và legal notice của module |
| `lib/` | Native library |
| `bin/` | Native command hoặc executable đi kèm module |
| `man/` | Manual page |

Ví dụ cấu trúc có thể gặp:

```text
extracted/
└── java.base/
    ├── classes/
    │   ├── module-info.class
    │   └── java/
    │       └── lang/
    │           └── Object.class
    ├── conf/
    ├── include/
    ├── legal/
    ├── lib/
    ├── bin/
    └── man/
```

Đây là cấu trúc minh họa cho một module có nhiều loại thành phần. Một module nhỏ như `java.sql` có thể chỉ có `classes/` và `legal/`, hoặc một tập section khác tùy bản phân phối.

Các section giữ vai trò khác nhau:

- `classes/` chứa bytecode và module descriptor. Đây thường là phần cần xem khi nghiên cứu API hoặc module.
- `conf/` có thể chứa cấu hình mà runtime hoặc thành phần module sử dụng.
- `include/` chứa header dành cho công việc native/JNI.
- `legal/` lưu thông tin giấy phép và thông báo pháp lý.
- `lib/` và `bin/` có thể chứa mã native phụ thuộc nền tảng.
- `man/` chứa tài liệu dạng manual.

## 9. Xác minh kết quả sau khi extract

Sau khi lệnh hoàn tất, hãy kiểm tra rằng các tệp dự kiến đã xuất hiện và đường dẫn giữ đúng section.

### 9.1. Kiểm tra trên Linux/macOS

```bash
find extracted/java.sql -type f
test -f extracted/java.sql/classes/module-info.class
```

Nếu module có `module-info.class`, lệnh `test` kết thúc thành công khi tệp tồn tại.

### 9.2. Kiểm tra trên Windows PowerShell

```powershell
Get-ChildItem -Path '.\extracted\java.sql' -Recurse -File
Test-Path '.\extracted\java.sql\classes\module-info.class'
```

`Test-Path` trả về `True` nếu đường dẫn được kiểm tra tồn tại.

### 9.3. Đối chiếu với danh sách gốc

Có thể chạy lại:

```bash
jmod list "$JAVA_HOME/jmods/java.sql.jmod"
```

Đối chiếu entry trong danh sách với đường dẫn đã extract. Ví dụ, entry `classes/module-info.class` phải tương ứng với tệp `classes/module-info.class` bên trong thư mục đích.

Việc đối chiếu này xác nhận cấu trúc và sự hiện diện của tệp. Nếu cần xác minh nội dung byte-for-byte, có thể dùng checksum của từng tệp hoặc công cụ so sánh phù hợp; chỉ kiểm tra tên tệp không chứng minh nội dung không bị thay đổi.

## 10. Làm việc với module JMOD khác

Có thể extract bất kỳ JMOD nào mà công cụ JDK hiện tại đọc được, không chỉ `java.sql.jmod`.

Ví dụ với `java.xml.jmod`:

```bash
jmod list "$JAVA_HOME/jmods/java.xml.jmod"
jmod describe "$JAVA_HOME/jmods/java.xml.jmod"
jmod extract --dir extracted/java.xml "$JAVA_HOME/jmods/java.xml.jmod"
```

Ví dụ với `java.base.jmod`:

```bash
jmod list "$JAVA_HOME/jmods/java.base.jmod"
jmod extract --dir extracted/java.base "$JAVA_HOME/jmods/java.base.jmod"
```

`java.base.jmod` thường lớn và chứa nhiều class cùng thành phần nền tảng. Nếu chỉ cần tìm hiểu thao tác extract, bắt đầu với một module nhỏ hơn để kết quả dễ kiểm tra.

Với JMOD do dự án tự tạo, dùng đường dẫn file cụ thể:

```bash
jmod list build/jmods/com.example.module.jmod
jmod describe build/jmods/com.example.module.jmod
jmod extract --dir extracted/com.example.module build/jmods/com.example.module.jmod
```

Tên module và đường dẫn output ở ví dụ cần được thay bằng artifact thực tế.

## 11. Có thể extract một entry riêng lẻ không?

Chế độ `jmod extract` giải xuất toàn bộ các entry của JMOD. Tùy chọn `--dir` chỉ chọn thư mục đích; nó không phải bộ lọc entry.

Nếu chỉ cần một class hoặc một resource:

1. Dùng `jmod list` để tìm chính xác đường dẫn entry.
2. Extract JMOD vào một thư mục làm việc riêng.
3. Lấy tệp cần thiết từ section tương ứng, thường là `classes/` hoặc `conf/`.
4. Giữ nguyên cấu trúc package hoặc đường dẫn nếu công cụ tiếp theo cần cấu trúc đó.

Không nên extract vào thư mục dự án hoặc thư mục JDK hiện tại chỉ để lấy một tệp. Một module có thể chứa hàng nghìn class và các thành phần native.

## 12. Phân tích nội dung sau khi extract

Sau khi giải xuất, có thể dùng các công cụ JDK khác để xem từng loại tệp.

### 12.1. Kiểm tra module descriptor

`module-info.class` mô tả tên module, dependencies, exports, opens, uses và provides. Có thể xem thông tin module trước khi extract bằng:

```bash
jmod describe "$JAVA_HOME/jmods/java.sql.jmod"
```

Đây là cách thuận tiện để đọc metadata module mà không cần tự phân tích class file.

### 12.2. Phân tích class file

Các class file trong `classes/` có thể được kiểm tra bằng `javap`. Ví dụ, sau khi extract module `java.sql`, class file của API JDBC có thể nằm dưới `classes/java/sql/`.

```bash
javap -classpath extracted/java.sql/classes java.sql.Connection
```

Lệnh này yêu cầu `javap` tìm class từ thư mục chứa package root. Nó hiển thị chữ ký class và method; thêm `-c` nếu cần xem bytecode của method phù hợp.

### 12.3. Kiểm tra native library

Các tệp trong `lib/` hoặc `bin/` có thể là thành phần native phụ thuộc hệ điều hành và kiến trúc. Việc extract chỉ ghi chúng ra đĩa; nó không chuyển đổi binary cho nền tảng khác và không tự cài đặt hoặc đăng ký chúng vào hệ thống.

Hãy xác định target platform và nguồn gốc module trước khi sử dụng native binary được extract.

## 13. JMOD extract và jlink liên quan thế nào?

`jlink` tạo runtime image từ một tập module cùng dependency cần thiết. JMOD là một trong những định dạng đầu vào phục vụ quá trình liên kết này.

Quy trình ở mức khái niệm:

```text
JMOD archive
    |
    | jmod list / describe
    v
Kiểm tra nội dung và module metadata
    |
    | jmod extract
    v
Các section được giải xuất để kiểm tra
    |
    | jlink dùng module từ module path
    v
Runtime image
```

Extract là thao tác kiểm tra và lấy các tệp ra thư mục. Nó không phải bước bắt buộc trước khi chạy `jlink`; `jlink` có thể làm việc trực tiếp với module path chứa JMOD.

Ví dụ liên kết runtime image từ các module có sẵn trong JDK:

```bash
jlink --module-path "$JAVA_HOME/jmods" --add-modules java.sql --output sql-runtime
```

Trên Windows PowerShell:

```powershell
jlink --module-path "$env:JAVA_HOME\jmods" --add-modules java.sql --output sql-runtime
```

Lệnh này tạo runtime image có module `java.sql` cùng các dependency cần thiết. Nó minh họa mục đích link-time của JMOD; không cần extract module trước khi gọi `jlink`.

## 14. Lưu ý về an toàn và tính tương thích

Khi extract JMOD, cần chú ý:

- **Nguồn archive:** ưu tiên JMOD từ JDK hoặc repository đáng tin cậy.
- **Thư mục đích:** chọn thư mục mới, riêng biệt để tránh ghi trộn hoặc ghi đè tệp đang có.
- **Dung lượng:** module lớn như `java.base` có thể giải xuất nhiều class và native binary.
- **Nền tảng:** native library và native command có thể chỉ phù hợp một hệ điều hành hoặc kiến trúc.
- **Phiên bản JDK:** dùng `jmod` từ JDK phù hợp với định dạng và module đang xử lý; khi gặp lỗi, kiểm tra phiên bản công cụ và nguồn archive.
- **Không chạy binary chỉ vì đã extract:** thao tác extract không chứng minh binary an toàn hoặc phù hợp với máy hiện tại.

Extract không thực thi class Java hoặc native command trong archive. Tuy nhiên, nó ghi dữ liệu ra hệ thống tệp, vì vậy vẫn nên chọn thư mục làm việc an toàn và kiểm tra nguồn file.

## 15. Lỗi thường gặp khi extract JMOD

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `jmod` không được nhận diện | PATH chưa chứa `bin` của JDK hoặc chỉ cài runtime | Kiểm tra `JAVA_HOME`, PATH và cài đặt JDK |
| Không tìm thấy `.jmod` | Sai đường dẫn hoặc JDK không có thư mục `jmods` | Kiểm tra đường dẫn và đúng bản JDK |
| Archive không hợp lệ | Tệp không phải JMOD hợp lệ, bị hỏng hoặc tải thiếu | Lấy lại artifact từ nguồn tin cậy và kiểm tra checksum |
| Không ghi được vào output directory | Thiếu quyền ghi hoặc thư mục đích không phù hợp | Chọn thư mục do người dùng quản lý và có quyền ghi |
| Kết quả trộn với tệp cũ | Dùng lại thư mục extract đã có nội dung | Chọn một thư mục đích mới, rỗng |
| Không thấy class trong kết quả | Đang xem sai section hoặc module không chứa class mong đợi | Đối chiếu `jmod list` và tìm dưới `classes/` |
| Không thấy `conf/`, `lib/` hoặc `include/` | Module không có section tương ứng | Kiểm tra danh sách entry; không phải module nào cũng chứa mọi section |
| Native binary không chạy | Binary không tương thích hệ điều hành hoặc kiến trúc | Kiểm tra target platform và dùng đúng bản phân phối |
| Muốn extract một file nhưng nhận được nhiều file | `jmod extract` giải xuất toàn bộ archive | Extract vào thư mục riêng rồi lấy entry cần thiết |

Khi gặp lỗi, hãy giữ nguyên file JMOD nguồn và kiểm tra lại bằng `jmod list`, `jmod describe` cùng phiên bản `jmod --version`. Tránh chỉnh sửa archive gốc để thử khắc phục một lỗi extract chưa rõ nguyên nhân.

## 16. Quy trình thực hành chuẩn

Khi cần extract một JMOD trong công việc:

1. Xác định JDK và đường dẫn tới tệp `.jmod`.
2. Kiểm tra `jmod --version` để biết công cụ đang sử dụng.
3. Dùng `jmod list` để xác nhận archive có entry mong đợi.
4. Dùng `jmod describe` để xem module metadata khi cần.
5. Chọn một thư mục output mới, rỗng và có quyền ghi.
6. Chạy `jmod extract --dir <output-dir> <module.jmod>`.
7. Liệt kê các tệp đã giải xuất và đối chiếu với `jmod list`.
8. Phân tích `module-info.class`, class file, config hoặc native file bằng công cụ phù hợp.
9. Nếu mục tiêu cuối cùng là tạo runtime image, đánh giá dùng `jlink` trực tiếp từ module path thay vì extract trước.
10. Ghi lại JDK, module, đường dẫn nguồn và thư mục output để người khác có thể tái lập thao tác.

## 17. Tổng kết

`jmod extract` là lệnh dùng để giải xuất toàn bộ nội dung của một JMOD archive vào thư mục được chỉ định.

Những lệnh cần nhớ:

- `jmod list <file.jmod>`: xem danh sách entry.
- `jmod describe <file.jmod>`: xem metadata module.
- `jmod extract --dir <output-dir> <file.jmod>`: extract toàn bộ entry.
- `jmod --version`: kiểm tra phiên bản công cụ.
- `jmod --help`: xem cú pháp và tùy chọn của JDK hiện tại.

JMOD có thể chứa class, cấu hình, legal notice, header và native binary. Sau khi extract, hãy kiểm tra section tương ứng, xác minh kết quả và dùng công cụ phù hợp để phân tích từng loại tệp. Nhớ rằng JMOD phục vụ compile-time hoặc link-time; modular JAR thường phù hợp hơn cho việc phân phối module thông thường, còn `jlink` dùng để tạo runtime image tùy chỉnh.

**Tài liệu tham khảo chính thức:** [The jmod Command — Java SE 24](https://docs.oracle.com/en/java/javase/24/docs/specs/man/jmod.html).
