# Di chuyển, đổi tên bằng move và ánh xạ tên bằng mapper

Trong Apache Ant, task `move` dùng để chuyển tệp hoặc nhóm tệp sang vị trí khác. Khi chuyển một tệp đơn, có thể chỉ định trực tiếp tên nguồn và đích. Khi chuyển nhiều tệp, Ant có thể lấy nguồn từ `FileSet` hoặc một ResourceCollection. Nếu cần đổi tên từng tệp theo quy tắc, có thể kết hợp `move` với `mapper`.

`move` giải quyết thao tác di chuyển; `mapper` giải quyết cách tính tên đích từ tên nguồn. Tách hai trách nhiệm này giúp buildfile mô tả rõ tệp nào được chuyển và mỗi tệp sẽ mang tên gì ở vị trí mới.

## 1. Di chuyển và đổi tên một tệp bằng move

Task `move` có thể nhận một tệp nguồn và một đường dẫn đích cụ thể bằng thuộc tính `file` và `tofile`:

```xml
<move file="build/report.tmp" tofile="build/report.txt" />
```

Ví dụ này chuyển `report.tmp` thành `report.txt` trong cùng thư mục. Vì đích được chỉ định đầy đủ, thao tác vừa di chuyển vừa đổi tên tệp.

Nếu muốn chuyển tệp vào một thư mục, dùng `file` và `todir`:

```xml
<move file="build/report.txt" todir="archive" />
```

Ant đặt tệp vào thư mục `archive`, giữ nguyên tên `report.txt`. Nếu cần đổi tên trong khi chuyển, có thể dùng `tofile` để chỉ định đường dẫn đích đầy đủ.

Hai cách khai báo thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `file` | Đường dẫn của một tệp nguồn cụ thể |
| `tofile` | Đường dẫn đầy đủ của tệp đích; thường dùng khi chuyển một tệp và muốn chỉ định tên đích |
| `todir` | Thư mục đích; tên tệp thường được giữ nguyên nếu không có mapper thay đổi |

Không nên chỉ định đồng thời các thuộc tính nguồn/đích theo những tổ hợp không phù hợp. Với một tệp cụ thể, hãy chọn `file` cùng `tofile` hoặc `todir` theo mục đích. Với nhiều tệp, dùng collection nguồn cùng `todir` và có thể thêm mapper.

## 2. Di chuyển nhiều tệp bằng FileSet

Khi cần chuyển một nhóm tệp, `FileSet` xác định thư mục gốc và mẫu chọn tệp. `move` xử lý những tệp được collection cung cấp:

```xml
<move todir="archive">
    <fileset dir="incoming">
        <include name="**/*.csv" />
        <exclude name="**/temporary/**" />
    </fileset>
</move>
```

Trong ví dụ này, Ant tìm các tệp CSV dưới `incoming`, bỏ qua các tệp nằm trong thư mục `temporary`, rồi chuyển các tệp còn lại sang `archive`. Cấu trúc đường dẫn tương đối của nguồn được dùng để xác định vị trí đích tương ứng.

Có thể dùng `move` để tổ chức bước staging sau khi một target đã tạo ra artifact:

```xml
<target name="archive-reports" depends="generate-reports">
    <move todir="release/reports">
        <fileset dir="build/reports">
            <include name="**/*.html" />
            <include name="**/*.xml" />
        </fileset>
    </move>
</target>
```

`depends` bảo đảm `generate-reports` chạy trước khi target `archive-reports` chuyển các báo cáo đã tạo. Nếu nguồn không tồn tại hoặc không có tệp nào khớp mẫu, không có tệp tương ứng để chuyển.

## 3. move khác copy như thế nào?

`copy` tạo bản sao ở đích và giữ lại tệp nguồn. `move` chuyển tệp sang đích và xóa nguồn sau khi thao tác chuyển thành công. Vì vậy, lựa chọn task ảnh hưởng trực tiếp tới trạng thái thư mục nguồn sau build.

| Nhu cầu | Task phù hợp | Trạng thái nguồn sau thao tác thành công |
|---|---|---|
| Tạo bản sao để dùng ở thư mục khác | `copy` | Tệp nguồn còn nguyên |
| Chuyển tệp sang khu vực lưu trữ | `move` | Tệp nguồn được loại bỏ |
| Đổi tên tệp trong cùng thư mục | `move` với `file` và `tofile` | Tên cũ không còn; tệp mang tên mới |
| Tạo artifact mới nhưng vẫn giữ đầu vào để chạy lại | `copy` | Tệp nguồn còn nguyên |

Ví dụ:

```xml
<!-- Sao chép: cả hai tệp đều tồn tại sau thao tác -->
<copy file="build/app.jar" tofile="release/app.jar" />

<!-- Di chuyển: tệp nguồn được chuyển khỏi build/ -->
<move file="build/app.jar" tofile="release/app.jar" />
```

Không dùng `move` chỉ vì muốn đổi tên đầu ra nếu các target sau vẫn cần tệp nguồn ở vị trí cũ. Trong trường hợp đó, `copy` với mapper hoặc một bước tạo artifact mới có thể phù hợp hơn.

## 4. Kiểm soát việc ghi đè và lỗi khi di chuyển

Khi tệp đích đã tồn tại, thuộc tính `overwrite` điều khiển việc ghi đè. Mặc định `overwrite` là `false`; Ant không ghi đè một tệp đích mới hơn nguồn. Nếu cần thay thế đích ngay cả khi đích mới hơn, đặt `overwrite="true"`:

```xml
<move todir="release" overwrite="true">
    <fileset dir="build">
        <include name="*.jar" />
    </fileset>
</move>
```

Hãy cân nhắc tác động của việc ghi đè khi thư mục đích chứa artifact do một bước khác tạo ra. Đặc biệt khi mapper có thể tạo cùng một tên đích cho nhiều nguồn, cần tránh cấu hình khiến các tệp lần lượt ghi đè lẫn nhau.

Task `move` còn có các thuộc tính hỗ trợ xử lý lỗi và theo dõi thao tác. Ví dụ, `failonerror` điều khiển việc build có thất bại khi không thể thực hiện thao tác di chuyển hay không; `verbose` có thể bật thông tin chi tiết về những tệp được xử lý. Khi cần giữ thời gian sửa đổi của tệp, xem xét `preserveLastModified` theo yêu cầu của quy trình.

```xml
<move todir="release"
      overwrite="true"
      failonerror="true"
      verbose="true"
      preservelastmodified="true">
    <fileset dir="build/package">
        <include name="*.zip" />
    </fileset>
</move>
```

Với một build phát hành, để lỗi di chuyển làm build thất bại thường giúp tránh tạo ra trạng thái phát hành thiếu tệp. Nếu quy trình có yêu cầu xử lý lỗi riêng, hãy đặt chính sách rõ ràng thay vì vô tình bỏ qua lỗi.

## 5. Mapper là gì?

Mapper là cơ chế ánh xạ tên nguồn thành một hoặc nhiều tên đích. Một task hỗ trợ mapper có thể dùng quy tắc này để tính đường dẫn đích cho từng tệp trong collection.

Ví dụ, nếu cần chuyển các tệp log và thêm hậu tố `.old`, có thể viết:

```xml
<move todir="archive">
    <fileset dir="logs">
        <include name="**/*.log" />
    </fileset>
    <mapper type="glob" from="*.log" to="*.log.old" />
</move>
```

Với một nguồn `server.log`, mapper tạo tên đích `server.log.old` dưới thư mục `archive`. Các tệp nguồn khác được ánh xạ theo cùng quy tắc. `todir` xác định gốc đích, còn mapper quyết định tên tương đối của từng tệp.

Mapper không chọn tập nguồn. `FileSet` và các mẫu include/exclude quyết định tệp nào được xử lý; mapper chỉ chuyển tên của mỗi tệp đã chọn thành tên đích. Sự phân chia này giúp kiểm soát độc lập phạm vi nguồn và cách đặt tên kết quả.

## 6. Các loại mapper thường dùng

Ant cung cấp nhiều loại mapper để biểu diễn những quy tắc đặt tên khác nhau:

| Loại mapper | Cách hoạt động | Trường hợp sử dụng |
|---|---|---|
| `identity` | Giữ nguyên tên nguồn | Muốn dùng cơ chế mapper nhưng không thay đổi tên |
| `flatten` | Bỏ các thành phần thư mục, chỉ giữ tên tệp | Gom tệp từ nhiều thư mục về một thư mục đích phẳng |
| `glob` | Thay phần khớp wildcard trong mẫu `from` bằng phần tương ứng của mẫu `to` | Thêm hậu tố, đổi phần mở rộng hoặc thêm thư mục đích |
| `regexp` | Dùng biểu thức chính quy để biến đổi tên | Quy tắc đổi tên có cấu trúc phức tạp |
| `merge` | Ánh xạ các nguồn về một tên đích cố định | Những task phù hợp với việc gộp nhiều nguồn vào một đích |
| `package` | Ánh xạ tên theo quy tắc package Java và tên lớp | Một số quy trình xử lý cấu trúc package/class |

Với thao tác move nhiều tệp, `glob` và `flatten` là hai lựa chọn dễ gặp. `regexp` hữu ích khi quy tắc đổi tên cần nhóm bắt hoặc biến đổi phức tạp hơn wildcard. Cần kiểm tra khả năng và cú pháp cụ thể của mapper được chọn trong phiên bản Ant đang dùng.

## 7. Dùng glob mapper để đổi tên theo mẫu

`glob` mapper nhận hai mẫu `from` và `to`. Phần wildcard được khớp ở `from` sẽ được thay vào vị trí wildcard tương ứng trong `to`.

Ví dụ đổi phần mở rộng `.txt` thành `.processed.txt`:

```xml
<move todir="processed">
    <fileset dir="incoming">
        <include name="**/*.txt" />
    </fileset>
    <mapper type="glob"
            from="*.txt"
            to="*.processed.txt" />
</move>
```

Một số ánh xạ minh họa:

| Tên nguồn | Tên đích tương đối do mapper tạo |
|---|---|
| `orders.txt` | `orders.processed.txt` |
| `customers.txt` | `customers.processed.txt` |
| `logs/system.txt` | `logs/system.processed.txt` |

Mẫu `from` phải phù hợp với tên mà task đưa vào mapper. Nếu tên nguồn không khớp mẫu, mapper không tạo tên đích cho nguồn đó; vì vậy, nên giữ `include` nhất quán với mẫu mapper để phạm vi được xử lý dễ hiểu.

Có thể thêm thư mục vào mẫu đích để tổ chức lại cây thư mục:

```xml
<move todir="archive">
    <fileset dir="incoming">
        <include name="**/*.log" />
    </fileset>
    <mapper type="glob"
            from="*.log"
            to="logs/*.log" />
</move>
```

Mỗi tên nguồn được ánh xạ vào nhánh `logs` bên dưới thư mục đích. Trước khi dùng quy tắc này cho dữ liệu thật, hãy kiểm tra cấu trúc đích dự kiến để tránh tạo đường dẫn lồng nhau ngoài ý muốn.

## 8. Dùng flatten mapper để gom tệp về một thư mục

`flatten` mapper bỏ các thành phần thư mục khỏi tên nguồn. Nó hữu ích khi muốn lấy tệp từ nhiều nhánh rồi gom về một nơi:

```xml
<move todir="archive/all-logs">
    <fileset dir="application">
        <include name="**/*.log" />
    </fileset>
    <mapper type="flatten" />
</move>
```

Ví dụ, các nguồn sau:

```text
application/
├── api/server.log
├── worker/server.log
└── scheduler/job.log
```

được ánh xạ thành tên đích:

```text
archive/all-logs/
├── server.log
├── server.log
└── job.log
```

Ví dụ cho thấy rủi ro quan trọng của `flatten`: hai tệp ở hai thư mục khác nhau có thể cùng tên sau khi bỏ đường dẫn. Khi nhiều nguồn ánh xạ tới một đích, kết quả có thể phụ thuộc thứ tự xử lý và chính sách ghi đè. Vì vậy, chỉ dùng `flatten` khi tên tệp là duy nhất trong toàn bộ tập nguồn hoặc khi đã có quy tắc giải quyết xung đột.

Nếu cần giữ thông tin nguồn, có thể dùng `glob` mapper để thêm hoặc đổi một phần tên nhưng vẫn bảo toàn cấu trúc thư mục tương đối.

## 9. Dùng regexp mapper khi quy tắc đổi tên phức tạp

`regexp` mapper dùng biểu thức chính quy để nhận diện tên nguồn và tạo tên đích từ các nhóm bắt. Cú pháp cụ thể phụ thuộc loại mapper và engine regex được Ant sử dụng; ví dụ dưới đây minh họa cách bắt phần tên trước phần mở rộng rồi đổi đuôi:

```xml
<move todir="converted">
    <fileset dir="incoming">
        <include name="**/*.data" />
    </fileset>
    <mapper type="regexp"
            from="^(.*)\.data$"
            to="\1.txt" />
</move>
```

Biểu thức `^(.*)\.data$` nhận toàn bộ tên kết thúc bằng `.data`; nhóm `(.*)` giữ phần tên đứng trước phần mở rộng. Phần thay thế `\1.txt` tạo tên mới với phần tên đã bắt và đuôi `.txt`.

Khi dùng regex trong XML, cần chú ý dấu gạch chéo ngược và cú pháp thay thế của Ant. Hãy thử mapper với một tập tệp nhỏ, gồm cả tên có thư mục con và tên không khớp mẫu, trước khi chạy trên tập dữ liệu lớn. Nếu quy tắc chỉ cần wildcard đơn giản, `glob` thường dễ đọc và ít nhầm lẫn hơn.

## 10. Kết hợp nhiều mapper

Khi cần thực hiện nhiều bước biến đổi tên, Ant hỗ trợ `chainedmapper` để đưa kết quả của mapper trước làm đầu vào cho mapper tiếp theo.

Ví dụ, có thể trước tiên loại bỏ phần thư mục, sau đó thêm hậu tố:

```xml
<move todir="archive">
    <fileset dir="logs">
        <include name="**/*.log" />
    </fileset>
    <chainedmapper>
        <flattenmapper />
        <globmapper from="*.log" to="*.log.old" />
    </chainedmapper>
</move>
```

Với một tên nguồn `service/api.log`, bước `flattenmapper` tạo `api.log`; bước `globmapper` tiếp tục tạo `api.log.old`. Tên cuối cùng được đặt dưới thư mục `archive`.

`chainedmapper` hữu ích khi mỗi bước biến đổi có một trách nhiệm nhỏ, nhưng cần kiểm tra các bước có thể làm mất thông tin. Trong ví dụ trên, bước flatten bỏ đường dẫn thư mục; nếu nhiều thư mục có cùng tên tệp, xung đột có thể xảy ra trước khi bước đổi phần mở rộng được áp dụng.

## 11. Mapper và đường dẫn đích

Khi dùng `todir`, đường dẫn mà mapper tạo thường được hiểu tương đối với thư mục đích. Vì vậy, mapper có thể thay đổi tên, giữ cấu trúc tương đối hoặc tạo nhánh con mới.

Ví dụ:

```xml
<move todir="release">
    <fileset dir="build/output">
        <include name="**/*.jar" />
    </fileset>
    <mapper type="glob"
            from="*.jar"
            to="libraries/*.jar" />
</move>
```

Với thư mục nguồn `build/output`, mapper đặt các JAR vào nhánh `libraries` dưới `release`, giữ phần tên phù hợp mẫu. Hãy xem `todir` là gốc của cây đích và `to` là quy tắc tạo đường dẫn tương đối bên trong gốc đó.

Nếu chỉ có một tệp và biết chính xác đường dẫn đích, `file` cùng `tofile` thường rõ ràng hơn. Mapper phù hợp hơn khi quy tắc phải áp dụng lặp lại cho nhiều nguồn.

## 12. Các lưu ý khi thiết kế thao tác move

Di chuyển là thao tác làm thay đổi vị trí nguồn. Một số điểm cần xác định trước:

- **Nguồn có được dùng lại không?** Nếu target khác cần tệp ở vị trí cũ, cân nhắc `copy` thay vì `move`.
- **Đích đã tồn tại chưa?** Xác định rõ có cho phép ghi đè hay cần giữ bản cũ.
- **Mapper có ánh xạ duy nhất không?** Hai nguồn không nên vô tình cùng tạo một đường dẫn đích.
- **Cấu trúc thư mục có cần giữ không?** `flatten` bỏ cấu trúc; `glob` có thể giữ hoặc thay đổi cấu trúc theo mẫu.
- **Tệp nguồn có được chọn đúng không?** `FileSet` kiểm soát phạm vi; mapper không thay thế include/exclude.
- **Build có thể chạy lặp lại không?** Sau lần move đầu tiên, tệp không còn ở nguồn. Lần build tiếp theo cần có bước tạo lại nguồn hoặc dùng dữ liệu đầu vào khác.

Đặc biệt với pipeline nhiều target, hãy phân biệt thư mục nguồn trung gian và thư mục artifact cuối. Chỉ chuyển tệp sau khi mọi bước cần đọc nguồn đã hoàn thành. Nếu cần lưu artifact đồng thời vẫn giữ dữ liệu để tái tạo, hãy sao chép sang vùng lưu trữ.

## 13. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Tệp được chuyển nhưng không đổi tên | Chưa khai báo mapper hoặc mẫu mapper không khớp tên nguồn | Kiểm tra `type`, `from`, `to` và tên tương đối được đưa vào mapper |
| Không có tệp nào được chuyển | FileSet không chọn được tệp hoặc mẫu mapper không tạo ánh xạ | Kiểm tra `dir`, include/exclude và thử với một tên nguồn cụ thể |
| Tệp đích cũ vẫn còn nguyên | Đích đã tồn tại và `overwrite` không cho phép thay thế | Xác định có nên bật `overwrite="true"` hay giữ bản đích hiện tại |
| Nhiều tệp ghi đè lên nhau | Mapper tạo cùng một tên đích cho các nguồn khác nhau | Giữ cấu trúc thư mục hoặc đưa thông tin phân biệt vào tên đích |
| Tệp không còn ở thư mục nguồn sau target | `move` đã chuyển và loại bỏ nguồn sau thao tác thành công | Dùng `copy` nếu bước sau vẫn cần nguồn |
| Đường dẫn đích lồng thêm thư mục ngoài dự kiến | Mẫu `to` đã chứa đường dẫn con trong khi tên nguồn cũng giữ đường dẫn tương đối | Kiểm tra kết quả ánh xạ của một vài đường dẫn mẫu và điều chỉnh `to` |
| Regex mapper không tạo tên mong muốn | Biểu thức `from` hoặc cú pháp nhóm thay thế `to` không khớp | Kiểm tra biểu thức, ký tự escape và nhóm bắt trên các tên mẫu |
| Build chạy lần thứ hai không còn tệp đầu vào | Lần chạy trước đã di chuyển nguồn đi | Tạo lại nguồn ở bước trước hoặc chọn copy nếu build cần lặp lại trên cùng đầu vào |

Khi debug, nên kiểm tra theo thứ tự: tập nguồn, tên tương đối đầu vào mapper, kết quả mapper, đường dẫn đích cuối cùng và chính sách overwrite. Điều này tách được lỗi chọn tệp khỏi lỗi ánh xạ tên và lỗi ghi đích.

## 14. Trình tự thiết kế move và mapper

Khi xây dựng một bước di chuyển tệp trong Ant, có thể thực hiện theo trình tự sau:

1. Xác định một tệp đơn hay một nhóm tệp cần chuyển.
2. Với tệp đơn, chọn `file` cùng `tofile` hoặc `todir`; với nhiều tệp, chọn ResourceCollection như `FileSet` và chỉ định `todir`.
3. Viết include/exclude để xác định chính xác các nguồn được chuyển.
4. Nếu cần đổi tên hàng loạt, chọn mapper phù hợp: `glob` cho wildcard, `flatten` để bỏ thư mục, `regexp` cho quy tắc phức tạp hoặc `chainedmapper` cho nhiều bước biến đổi.
5. Kiểm tra các nguồn khác nhau có thể tạo cùng tên đích hay không.
6. Xác định chính sách ghi đè, xử lý lỗi và thời gian sửa đổi của tệp.
7. Chạy target trên tập mẫu nhỏ, kiểm tra cả thư mục đích lẫn việc nguồn đã được di chuyển đúng như dự kiến.

`move` chịu trách nhiệm chuyển tệp và làm thay đổi vị trí nguồn; `mapper` biến tên tương đối của từng nguồn thành tên đích. Khi tách rõ hai phần này, buildfile có thể di chuyển một tệp đơn, chuyển hàng loạt hoặc tổ chức lại cây thư mục theo quy tắc đặt tên có thể đọc và tái sử dụng.
