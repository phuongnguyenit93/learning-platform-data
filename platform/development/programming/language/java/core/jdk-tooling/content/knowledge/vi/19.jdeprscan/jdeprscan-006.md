# Quét nhiều artifact bằng `jdeprscan`

`jdeprscan` là công cụ trong JDK dùng để quét bytecode Java và tìm các tham chiếu đến API Java SE đã bị deprecated. Công cụ nhận đầu vào là thư mục chứa cây package, file JAR, file `.class` hoặc tên class đầy đủ. Có thể truyền **nhiều mục tiêu trong cùng một lệnh**, nhờ đó kiểm tra đồng thời các JAR của ứng dụng, plugin và thư mục class đã biên dịch.

Quét nhiều artifact hữu ích khi một sản phẩm được ghép từ nhiều module hoặc thư viện nội bộ. Một lần chạy có thể giúp phát hiện API cũ nằm trong từng thành phần trước khi nâng JDK, thay đổi baseline Java hoặc phát hành bản mới.

Cần phân biệt ba việc:

- **Target cần quét:** artifact được đặt trực tiếp ở cuối lệnh `jdeprscan`.
- **Class path phụ thuộc:** đường dẫn giúp công cụ tìm các class mà target tham chiếu; khai báo bằng `--class-path`.
- **Release API:** phiên bản Java SE dùng làm tập dữ liệu deprecated; chọn bằng `--release`.

`--class-path` không tự biến mọi JAR trên class path thành target cần quét. Muốn kiểm tra một artifact, phải truyền artifact đó như một đối số mục tiêu.

Toolchain dùng để kiểm tra bài này là `jdeprscan 24.0.2`. Cú pháp và các release được hỗ trợ có thể thay đổi giữa các JDK; hãy kiểm tra `jdeprscan --help` trên môi trường build thực tế.

## 1. `jdeprscan` quét được những loại đầu vào nào?

Theo trợ giúp của JDK 24.0.2, mỗi đối số mục tiêu có thể là:

| Loại đầu vào | Ví dụ | Ý nghĩa |
|---|---|---|
| Thư mục | `build/classes` | Gốc của cây package đã biên dịch |
| JAR | `build/libs/service.jar` | Các class nằm trong archive |
| Class file | `build/classes/com/acme/LegacyAdapter.class` | Một file bytecode cụ thể |
| Tên class đầy đủ | `com.acme.LegacyAdapter` | Class được phân giải qua môi trường tìm kiếm |
| Nested class | `com.acme.Outer$Inner` | Tên nested class dùng ký tự `$` |

Cú pháp tổng quát:

~~~text
jdeprscan [options] {dir|jar|class} ...
~~~

Dấu `...` có nghĩa là có thể truyền nhiều target:

~~~text
jdeprscan --release 17 build/app.jar build/plugin-a.jar build/plugin-b.jar build/classes
~~~

Lệnh trên quét cả ba JAR và cây class `build/classes` trong cùng một lần chạy. Đường dẫn có dấu cách phải được đặt trong dấu nháy theo quy tắc của shell.

`jdeprscan` phân tích bytecode đã biên dịch. Nó không đọc file `.java` để tìm mọi lời gọi trong source. Nếu source vừa thay đổi, hãy compile lại trước khi quét để báo cáo phản ánh bytecode sắp phát hành.

## 2. Vì sao cần quét nhiều artifact?

Một ứng dụng Java thường gồm nhiều thành phần:

~~~text
application/
  app.jar
  plugins/
    billing-plugin.jar
    report-plugin.jar
  libs/
    company-api.jar
    common-utils.jar
  classes/
    com/acme/internal/
~~~

Nếu chỉ quét `app.jar`, các lời gọi deprecated nằm trong plugin hoặc thư viện nội bộ có thể bị bỏ sót. Hãy lập danh sách artifact thuộc phạm vi phát hành và truyền từng mục tiêu vào lệnh.

Các trường hợp nên quét nhiều artifact:

- Ứng dụng gồm nhiều JAR do các team khác nhau phát triển.
- Plugin được nạp ở runtime.
- Nhiều module được build thành các JAR độc lập.
- Có thư mục class chưa được đóng gói thành JAR.
- Cần kiểm tra toàn bộ output trước khi nâng JDK.
- Cần so sánh mức sử dụng API deprecated giữa các release.

Chỉ đưa vào danh sách những artifact thực sự cần kiểm tra. Thường nên loại JAR chứa source, Javadoc, test fixture hoặc artifact trung gian không được phân phối, trừ khi chúng cũng nằm trong phạm vi kiểm tra.

## 3. Quét nhiều JAR trong một lệnh

Ví dụ trên Windows PowerShell:

~~~powershell
jdeprscan --release 17 `
    .\build\app.jar `
    .\build\plugins\billing-plugin.jar `
    .\build\plugins\report-plugin.jar `
    .\build\classes
~~~

Trên macOS/Linux:

~~~sh
jdeprscan --release 17 \
    build/app.jar \
    build/plugins/billing-plugin.jar \
    build/plugins/report-plugin.jar \
    build/classes
~~~

Trong cả hai ví dụ, mỗi đường dẫn sau tùy chọn là một target riêng. Không cần chạy một tiến trình `jdeprscan` cho từng JAR nếu số lượng target vừa phải.

Nếu muốn thêm dependency để phân giải class được tham chiếu, dùng `--class-path`:

Windows:

~~~powershell
jdeprscan --release 17 `
    --class-path ".\libs\company-api.jar;.\libs\common-utils.jar" `
    .\build\app.jar `
    .\build\plugins\billing-plugin.jar `
    .\build\plugins\report-plugin.jar
~~~

macOS/Linux:

~~~sh
jdeprscan --release 17 \
    --class-path "libs/company-api.jar:libs/common-utils.jar" \
    build/app.jar \
    build/plugins/billing-plugin.jar \
    build/plugins/report-plugin.jar
~~~

Dấu phân cách phần tử class path là `;` trên Windows và `:` trên macOS/Linux. Đặt toàn bộ class path trong dấu nháy để shell không diễn giải dấu phân cách thành cú pháp riêng.

## 4. Phân biệt target và dependency class path

Đây là điểm quan trọng nhất khi quét nhiều artifact:

~~~text
jdeprscan --release 17 --class-path "libs/api.jar;libs/util.jar" app.jar plugin.jar
~~~

- `app.jar` và `plugin.jar` là hai target được quét.
- `libs/api.jar` và `libs/util.jar` được cung cấp để phân giải các class phụ thuộc.
- Nếu cũng muốn quét `api.jar` và `util.jar`, hãy thêm chúng vào danh sách target.

Ví dụ:

~~~text
jdeprscan --release 17 --class-path "libs/api.jar;libs/util.jar" app.jar plugin.jar libs/api.jar libs/util.jar
~~~

Nếu thiếu dependency, công cụ có thể không phân giải được một số class hoặc đưa ra chẩn đoán bổ sung. Khi đó, báo cáo có thể chưa đầy đủ. Hãy cung cấp dependency cần thiết trong class path, đồng thời bảo đảm từng artifact cần kiểm tra được liệt kê làm target.

Không dùng class path thay cho danh sách artifact. Việc đặt một JAR ở `--class-path` chỉ nhằm hỗ trợ tra cứu class; không nên suy luận rằng JAR đó đã được quét.

## 5. Quét tự động tất cả JAR trong thư mục bằng PowerShell

Khi build tạo nhiều JAR, có thể lấy danh sách bằng `Get-ChildItem` rồi truyền cả mảng cho `jdeprscan`.

~~~powershell
$targets = @(
    Get-ChildItem .\build\libs -Filter *.jar -File -Recurse |
        Where-Object {
            $_.Name -notlike '*-sources.jar' -and
            $_.Name -notlike '*-javadoc.jar'
        } |
        ForEach-Object { $_.FullName }
)

if ($targets.Count -eq 0) {
    throw "No application JAR files were found."
}

& jdeprscan --release 17 @targets

if ($LASTEXITCODE -ne 0) {
    throw "jdeprscan failed with exit code $LASTEXITCODE"
}
~~~

Giải thích:

- `Get-ChildItem -Recurse` tìm JAR trong toàn bộ thư mục build.
- `-File` chỉ lấy file, không lấy thư mục.
- Bộ lọc bỏ qua `-sources.jar` và `-javadoc.jar`.
- `@targets` truyền từng đường dẫn trong mảng thành một đối số riêng.
- `$LASTEXITCODE` kiểm tra trạng thái tiến trình native sau khi chạy.

Nếu target có dependency ngoài JDK, thêm `--class-path` trước `@targets`. Hãy kiểm tra class path có đủ dependency và dùng dấu `;` giữa các đường dẫn trên Windows.

## 6. Chia batch khi có rất nhiều artifact

Một lệnh có quá nhiều đường dẫn có thể chạm giới hạn độ dài command line của hệ điều hành. Khi đó, chia danh sách thành các batch nhỏ. Mỗi batch vẫn quét nhiều artifact trong cùng một tiến trình.

Ví dụ PowerShell, mỗi batch tối đa 25 JAR:

~~~powershell
$targets = @(
    Get-ChildItem .\build\libs -Filter *.jar -File -Recurse |
        Where-Object {
            $_.Name -notlike '*-sources.jar' -and
            $_.Name -notlike '*-javadoc.jar'
        } |
        ForEach-Object { $_.FullName }
)

if ($targets.Count -eq 0) {
    throw "No application JAR files were found."
}

$batchSize = 25

for ($i = 0; $i -lt $targets.Count; $i += $batchSize) {
    $end = [Math]::Min($i + $batchSize - 1, $targets.Count - 1)
    $batch = @($targets[$i..$end])

    Write-Host "Scanning artifacts $($i + 1) to $($end + 1)..."

    & jdeprscan --release 17 @batch

    if ($LASTEXITCODE -ne 0) {
        throw "jdeprscan failed for batch starting at index $i"
    }
}
~~~

Nếu có class path phụ thuộc, thêm `--class-path $dependencyPath` vào mỗi lần gọi. Chọn kích thước batch theo độ dài đường dẫn và giới hạn command line của môi trường CI.

Với batch, lưu báo cáo kèm danh sách target tương ứng. Nếu cần xác định một phát hiện thuộc artifact nào, quét riêng artifact đó sau bước quét tổng hợp hoặc dùng `--verbose` để hỗ trợ điều tra. Chế độ verbose có thể in lượng thông tin rất lớn.

## 7. Quét nhiều JAR bằng Bash

Ví dụ Bash trên macOS/Linux, tìm JAR và truyền theo mảng để giữ nguyên đường dẫn có dấu cách:

~~~bash
targets=()

while IFS= read -r -d '' target; do
    targets+=("$target")
done < <(
    find build/libs -type f -name '*.jar' \
        ! -name '*-sources.jar' \
        ! -name '*-javadoc.jar' \
        -print0
)

if [ "${#targets[@]}" -eq 0 ]; then
    echo "No application JAR files were found." >&2
    exit 2
fi

jdeprscan --release 17 "${targets[@]}"
scan_status=$?

if [ "$scan_status" -ne 0 ]; then
    echo "jdeprscan failed with exit code $scan_status" >&2
    exit "$scan_status"
fi
~~~

Bash array giữ mỗi đường dẫn thành một đối số riêng. Cách này tránh lỗi khi tên file có dấu cách hoặc ký tự đặc biệt.

Nếu số lượng target lớn, có thể chia mảng thành batch:

~~~bash
batch_size=25

for ((i = 0; i < ${#targets[@]}; i += batch_size)); do
    batch=("${targets[@]:i:batch_size}")

    echo "Scanning artifacts $((i + 1)) to $((i + ${#batch[@]}))..."

    jdeprscan --release 17 "${batch[@]}" || exit $?
done
~~~

Nếu cần class path, thêm `--class-path 'libs/api.jar:libs/util.jar'` vào lệnh trong vòng lặp. Trên macOS/Linux, dấu `:` phân cách các phần tử class path.

## 8. Chọn đúng `--release`

Tùy chọn `--release` xác định phiên bản Java SE cung cấp tập API deprecated dùng để đối chiếu. Nó không phải tùy chọn compile và cũng không tự thay đổi bytecode của artifact.

Ví dụ:

~~~text
jdeprscan --release 17 app.jar plugin.jar
~~~

Lệnh trên kiểm tra việc sử dụng API deprecated theo bộ API của Java SE 17.

Khi sản phẩm hỗ trợ nhiều Java release, chạy lại cho từng baseline cần hỗ trợ:

~~~text
jdeprscan --release 17 app.jar plugin.jar
jdeprscan --release 21 app.jar plugin.jar
jdeprscan --release 24 app.jar plugin.jar
~~~

Mỗi lần chạy chỉ có một giá trị `--release`. Không ghép nhiều release vào cùng một lần gọi. Giữ nguyên danh sách artifact giữa các lần chạy để có thể so sánh báo cáo.

Trong JDK 24.0.2 được kiểm tra, help liệt kê các release từ 8 đến 24. JDK khác có thể hỗ trợ tập release khác. Hãy xem help của chính JDK được dùng trong CI.

Nếu ứng dụng cần chạy trên Java 17 nhưng bạn đang đánh giá kế hoạch nâng lên Java 21, hãy tạo báo cáo riêng cho từng release mục tiêu. Như vậy team có thể phân biệt API đã deprecated trong baseline hiện tại với API bị deprecated ở release mới hơn.

## 9. Chỉ tìm API deprecated for removal

`--for-removal` giới hạn kết quả vào các API đã được đánh dấu deprecated for removal trong release được chọn:

~~~text
jdeprscan --release 17 --for-removal app.jar plugin.jar
~~~

Chế độ này hữu ích để ưu tiên rủi ro nâng cấp. API deprecated thông thường có thể còn tồn tại lâu; API for removal báo hiệu khả năng bị loại bỏ ở release tương lai và cần được xử lý sớm.

Phân biệt:

- Không có `--for-removal`: quét các API deprecated thuộc tập release đã chọn.
- Có `--for-removal`: chỉ quét nhóm API được đánh dấu for removal.
- `--for-removal` không có nghĩa artifact đang bị xóa hoặc package bị gỡ.

Theo help của JDK 24.0.2, `--for-removal` không thể kết hợp với `--release 6`, `7` hoặc `8`. Với release 8, bỏ `--for-removal` hoặc dùng một release phù hợp được toolchain hỗ trợ.

Có thể tạo hai báo cáo riêng cho cùng một tập artifact: một báo cáo đầy đủ và một báo cáo ưu tiên API for removal.

## 10. Dùng `--list` để xem danh sách API deprecated

`--list` in tập API deprecated mà tool biết cho release được chọn:

~~~text
jdeprscan --list --release 17
~~~

Đây là thao tác liệt kê API, không phải quét artifact. Không truyền directory, JAR, class file hoặc class name khi dùng `--list`.

Có thể dùng danh sách này để tra cứu tên API và xác nhận API có thuộc tập release đang kiểm tra hay không. Danh sách có thể dài; trong CI, lưu ra file nếu cần tra cứu hoặc so sánh.

Ví dụ PowerShell:

~~~powershell
jdeprscan --list --release 17 |
    Set-Content -Encoding UTF8 .\build\deprecated-java-se-17.txt
~~~

Ví dụ macOS/Linux:

~~~sh
jdeprscan --list --release 17 > build/deprecated-java-se-17.txt
~~~

Không nhầm `--list` với lệnh quét. Muốn tìm nơi ứng dụng đang dùng API, hãy chạy lệnh với các target artifact và không thêm `--list`.

## 11. Hiểu báo cáo scan

Một lần chạy thử trên JDK 24.0.2:

~~~text
jdeprscan --release 17 java.lang.Thread java.util.Date
~~~

Kết quả:

~~~text
class java/util/Date uses deprecated method java/util/Date::<init>(IIIIII)V
class java/util/Date uses deprecated method java/util/Date::parse(Ljava/lang/String;)J
~~~

Trong lần chạy này, hai target class được truyền cùng lệnh; các phát hiện xuất hiện trong `java.util.Date`. Dòng báo cáo cho biết class sử dụng API deprecated và member được tham chiếu.

Một số kiểu thông tin có thể xuất hiện:

- Class sử dụng deprecated class hoặc interface.
- Method gọi một method deprecated.
- Field được đọc hoặc ghi có trạng thái deprecated.
- Constructor deprecated được gọi.

Phần signature có thể dùng JVM descriptor. Ví dụ:

- `I` đại diện kiểu `int`.
- `J` đại diện kiểu `long`.
- `V` đại diện kiểu trả về `void`.
- `Ljava/lang/String;` đại diện kiểu `java.lang.String`.
- `IIIIII` là sáu tham số kiểu `int`.

Không phải mọi báo cáo đều có source line number. `jdeprscan` phân tích bytecode nên hãy dùng tên class/member để quay lại source, tìm call site và xác định module sở hữu code.

## 12. Exit code không có nghĩa là không còn deprecated usage

Một điểm quan trọng khi tích hợp CI: `jdeprscan` có thể trả exit code `0` dù đã in ra các dòng sử dụng API deprecated.

Trong thử nghiệm ở mục trước, lệnh:

~~~text
jdeprscan --release 17 java.lang.Thread java.util.Date
~~~

đã in hai phát hiện nhưng tiến trình vẫn kết thúc với exit code `0`. Vì vậy, chỉ kiểm tra `$LASTEXITCODE` hoặc `$?` là chưa đủ để đặt quality gate “không còn deprecated usage”.

Cần kiểm tra riêng hai điều:

1. **Tool execution:** tiến trình có chạy thành công và đọc được target hay không.
2. **Scan findings:** báo cáo có chứa các dòng sử dụng deprecated API hay không.

Ví dụ PowerShell cho một batch:

~~~powershell
$report = & jdeprscan --release 17 @targets 2>&1
$scanExitCode = $LASTEXITCODE

$report | Set-Content -Encoding UTF8 .\build\jdeprscan-report.txt

if ($scanExitCode -ne 0) {
    throw "jdeprscan could not complete successfully."
}

$findings = @(
    $report | Where-Object { "$_" -match ' uses deprecated ' }
)

if ($findings.Count -gt 0) {
    throw "Deprecated Java SE API usages were found. Review jdeprscan-report.txt."
}
~~~

Mẫu này dùng chuỗi `uses deprecated` trong định dạng output đã quan sát của tool. Nếu nâng JDK, hãy kiểm tra output mới và cập nhật parser nếu format thay đổi. Giữ nguyên báo cáo thô để người review có thể kiểm tra.

Trong dự án đã có nhiều finding, có thể dùng baseline được duyệt: lưu báo cáo hiện tại, so sánh với báo cáo mới và chỉ chặn finding mới hoặc finding for removal theo chính sách. Không xóa finding cũ khỏi baseline nếu chưa có kế hoạch xử lý.

## 13. Tổ chức báo cáo cho từng artifact

Khi quét nhiều JAR cùng lúc, output giúp phát hiện class và API deprecated, nhưng việc truy ngược class về đúng artifact có thể cần thêm thông tin build.

Có ba cách tổ chức:

**Quét tổng hợp:** truyền tất cả target trong một lệnh. Phù hợp để phát hiện nhanh toàn bộ vấn đề trong sản phẩm.

**Quét theo nhóm:** chia target theo module, plugin hoặc team sở hữu. Phù hợp khi cần giao việc xử lý theo component.

**Quét riêng artifact:** chạy từng JAR độc lập sau khi quét tổng hợp để xác định chính xác nguồn phát hiện. Cách này tạo nhiều báo cáo nhưng dễ gắn owner.

Đặt tên report theo release và component, ví dụ:

~~~text
reports/
  jdeprscan-java17-all.txt
  jdeprscan-java17-billing.txt
  jdeprscan-java17-report-plugin.txt
  jdeprscan-java21-all.txt
  jdeprscan-java17-for-removal.txt
~~~

Ghi nhận cùng báo cáo:

- JDK và `jdeprscan` version.
- Release API được chọn.
- Danh sách artifact và checksum nếu cần tái hiện.
- Class path dependency dùng khi quét.
- Ngày build/commit.
- Exit code của tool.
- Số finding và baseline được so sánh.

Nếu nhiều artifact chứa cùng một class do shading hoặc đóng gói trùng, báo cáo tổng hợp có thể gây khó khăn khi xác định artifact gốc. Hãy giữ inventory của target và quét riêng những component cần truy nguyên.

## 14. Phạm vi và giới hạn cần hiểu

`jdeprscan` tập trung vào các API Java SE deprecated. Nó hữu ích khi nâng JDK hoặc kiểm tra tương thích với các release Java, nhưng không thay thế mọi hình thức kiểm tra deprecated trong hệ sinh thái.

Một số giới hạn:

- Công cụ đọc bytecode; source chưa compile sẽ không được phân tích.
- Mục tiêu là API Java SE deprecated, không phải bộ kiểm tra tổng quát mọi annotation `@Deprecated` của thư viện bên thứ ba.
- Lời gọi được tạo động qua reflection, tên class/method lấy từ cấu hình hoặc đường đi runtime không có tham chiếu bytecode trực tiếp có thể không được phát hiện như một call site thông thường.
- Thiếu dependency có thể làm việc phân giải class không đầy đủ.
- `jdeprscan` không thay thế test runtime, kiểm tra binary compatibility hoặc kiểm tra API của vendor/library riêng.
- CLI JDK 24.0.2 cung cấp `--class-path`; không giả định có tùy chọn `--module-path` tương tự một số công cụ JDK khác.
- Trợ giúp liệt kê target là directory, JAR, class file hoặc class name; không mặc định mọi loại archive như `.jmod` đều được hỗ trợ.

Với thư viện bên thứ ba, dùng thêm compiler warning, tài liệu migration của nhà cung cấp, dependency analysis và công cụ kiểm tra phù hợp với hệ sinh thái đó.

## 15. Lỗi thường gặp khi quét nhiều artifact

### Chỉ thấy finding trong ứng dụng chính

**Nguyên nhân:** chỉ truyền `app.jar`, bỏ sót plugin hoặc thư viện nội bộ.

**Cách xử lý:** lấy danh sách artifact từ toàn bộ output của build và truyền tất cả target cần kiểm tra.

### Dependency không phân giải được

**Nguyên nhân:** `--class-path` thiếu JAR hoặc thư mục chứa class phụ thuộc.

**Cách xử lý:** bổ sung dependency vào class path; vẫn truyền dependency cần kiểm tra như target riêng.

### Dùng sai dấu phân cách class path

**Nguyên nhân:** dùng `:` trên Windows hoặc `;` trên Linux/macOS.

**Cách xử lý:** Windows dùng `;`; macOS/Linux dùng `:`. Đặt path list trong dấu nháy.

### Đường dẫn có dấu cách bị tách thành nhiều đối số

**Nguyên nhân:** không quote đường dẫn hoặc script tự ghép command thành một chuỗi.

**Cách xử lý:** dùng array và argument splatting trong PowerShell; dùng Bash array với `"${targets[@]}"` trên Unix.

### Quét nhầm source/Javadoc JAR

**Nguyên nhân:** lấy mọi file `*.jar` trong thư mục output mà không lọc artifact phụ.

**Cách xử lý:** loại `-sources.jar`, `-javadoc.jar` và artifact không được phân phối khỏi target list nếu chúng nằm ngoài phạm vi.

### Báo cáo có finding nhưng CI vẫn xanh

**Nguyên nhân:** chỉ kiểm tra exit code của `jdeprscan`.

**Cách xử lý:** phân tích report hoặc so sánh với baseline; không coi exit code `0` là bằng chứng không có deprecated usage.

### Không biết finding thuộc JAR nào

**Nguyên nhân:** chạy tổng hợp cho nhiều artifact và class trùng giữa các JAR.

**Cách xử lý:** chia theo module/team hoặc quét riêng artifact cần truy nguyên; lưu inventory của target cùng report.

### `--list` không chạy cùng danh sách JAR

**Nguyên nhân:** `--list` là chế độ liệt kê API deprecated, không phải chế độ scan target.

**Cách xử lý:** bỏ `--list` khi quét artifact; dùng `--list` riêng khi cần xem danh sách API.

### Không tìm thấy API mới deprecated ở release cao hơn

**Nguyên nhân:** đang dùng `--release` thấp hơn phiên bản cần đánh giá.

**Cách xử lý:** chạy một lượt riêng cho từng Java release mà sản phẩm cần hỗ trợ hoặc dự định nâng cấp.

## 16. Quy trình đề xuất cho CI và release

Một pipeline quét nhiều artifact có thể thực hiện theo trình tự:

1. Build tất cả module và plugin cần phát hành.
2. Tạo inventory các JAR và class directory thực tế.
3. Loại artifact phụ không thuộc phạm vi.
4. Chọn Java release cần đánh giá.
5. Cung cấp dependency qua `--class-path`.
6. Chạy `jdeprscan` trên toàn bộ target hoặc chia batch.
7. Lưu raw report và thông tin toolchain.
8. Kiểm tra exit code để phát hiện lỗi thực thi.
9. Phân tích finding hoặc so sánh với baseline được duyệt.
10. Ưu tiên xử lý API `for removal`.
11. Quét lại sau khi sửa và đính kèm report mới vào release.

Ví dụ một lệnh quét tổng hợp:

~~~text
jdeprscan --release 17 --class-path "libs/api.jar;libs/common.jar" app.jar billing-plugin.jar report-plugin.jar build/classes
~~~

Ví dụ một lệnh chỉ kiểm tra API for removal:

~~~text
jdeprscan --release 17 --for-removal --class-path "libs/api.jar;libs/common.jar" app.jar billing-plugin.jar report-plugin.jar build/classes
~~~

Chính sách release nên phân biệt finding mới với finding đã được chấp nhận có thời hạn. Mỗi finding nên có owner, API thay thế, mức ưu tiên, release dự kiến xử lý và trạng thái xác nhận.

## 17. Checklist trước khi hoàn tất quét nhiều artifact

- [ ] Đã xác nhận `jdeprscan --version` và `jdeprscan --help`.
- [ ] Đã lập danh sách tất cả JAR/class directory thuộc phạm vi.
- [ ] Đã truyền từng artifact cần quét làm target argument.
- [ ] Đã phân biệt target với dependency trong `--class-path`.
- [ ] Class path dùng đúng dấu phân cách theo hệ điều hành.
- [ ] Đã quote đường dẫn có dấu cách hoặc dùng array của shell.
- [ ] Đã chọn đúng `--release` cho baseline cần kiểm tra.
- [ ] Đã chạy riêng `--for-removal` nếu cần ưu tiên API có nguy cơ bị loại bỏ.
- [ ] Không kết hợp `--list` với target scan.
- [ ] Đã kiểm tra cả exit code lẫn nội dung report.
- [ ] Đã lưu report, tool version, release và target inventory.
- [ ] Đã phân loại finding theo artifact/team sở hữu.
- [ ] Đã so sánh baseline và xử lý finding mới theo chính sách.
- [ ] Đã quét lại sau khi thay thế API deprecated.
- [ ] Đã giữ báo cáo cuối cùng cùng artifact phát hành.

Quét nhiều artifact bằng `jdeprscan` giúp kiểm tra bytecode của toàn bộ sản phẩm trong một quy trình nhất quán. Truyền đúng target, cung cấp dependency để phân giải, chọn release phù hợp và phân tích report độc lập với exit code sẽ giúp nhóm phát hiện sớm việc dùng API Java SE deprecated trước khi nâng cấp hoặc phát hành.