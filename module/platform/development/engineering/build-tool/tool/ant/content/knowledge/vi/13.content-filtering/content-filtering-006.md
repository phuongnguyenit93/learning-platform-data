# Chuẩn hóa xuống dòng bằng fixcrlf

Các hệ điều hành và công cụ có thể lưu ký tự kết thúc dòng theo những quy ước khác nhau. Một tệp văn bản tạo trên Windows thường dùng cặp CRLF, trong khi nhiều công cụ trên Linux và Unix dùng LF. Một số định dạng cũ dùng CR. Khi cùng một dự án được chỉnh sửa trên nhiều môi trường, sự khác biệt này có thể làm Git hiển thị thay đổi ở gần như mọi dòng, khiến diff khó đọc hoặc làm công cụ xử lý văn bản hoạt động không nhất quán.

Apache Ant cung cấp task `fixcrlf` để chuẩn hóa ký tự kết thúc dòng trong các tệp văn bản. Task này có thể chuyển đổi giữa CR, LF và CRLF, đồng thời có các tùy chọn xử lý tab và ký tự EOF kiểu DOS. Khi đặt đúng phạm vi tệp và cấu hình encoding, `fixcrlf` giúp build tạo ra nội dung văn bản có định dạng thống nhất.

## 1. CR, LF và CRLF là gì?

Ký tự xuống dòng trong tệp văn bản không phải lúc nào cũng là một byte giống nhau. Có ba dạng thường gặp:

| Dạng | Ký tự | Giá trị byte | Môi trường thường gặp |
|---|---|---|---|
| CR | Carriage Return (`\r`) | `0D` | Một số định dạng cũ, quy ước Mac cổ điển |
| LF | Line Feed (`\n`) | `0A` | Linux, Unix và nhiều công cụ phát triển hiện đại |
| CRLF | Carriage Return + Line Feed (`\r\n`) | `0D 0A` | Windows |

Ví dụ một dòng văn bản `Hello` được kết thúc bằng các dạng khác nhau:

```text
CR:    Hello\r
LF:    Hello\n
CRLF:  Hello\r\n
```

Trong tệp thực tế, các ký tự này được lưu dưới dạng byte điều khiển. Trình soạn thảo thường hiển thị nội dung giống nhau, nhưng công cụ so sánh byte hoặc hệ thống quản lý phiên bản có thể nhận ra khác biệt.

Nếu một tệp có dòng thứ nhất kết thúc bằng CRLF và dòng thứ hai kết thúc bằng LF, nó đang dùng kiểu kết thúc dòng hỗn hợp. Điều này có thể xuất hiện khi nhiều công cụ ghi nối vào cùng một tệp hoặc khi nội dung được ghép từ nhiều nguồn.

## 2. Task fixcrlf làm gì?

`fixcrlf` đọc các tệp văn bản trong thư mục nguồn, phân tích các dòng và ghi chúng theo quy tắc kết thúc dòng được chọn. Task cũng có thể xử lý tab và ký tự EOF đặc biệt kiểu DOS.

Cú pháp cơ bản:

```xml
<fixcrlf srcdir="src" eol="lf" />
```

Ví dụ này xử lý các tệp được chọn trong thư mục `src` và chuyển kết thúc dòng sang LF. Khi không khai báo `destdir`, task cập nhật các tệp ngay trong thư mục nguồn. Đây là thao tác ghi lại tệp, vì vậy cần chắc chắn thư mục đó là đầu vào có thể chỉnh sửa.

Nếu muốn giữ nguyên nguồn và ghi kết quả sang một thư mục khác, hãy khai báo `destdir`:

```xml
<fixcrlf
    srcdir="src"
    destdir="build/normalized"
    eol="lf" />
```

Với `destdir`, Ant ghi phiên bản đã chuẩn hóa vào thư mục đích và giữ cấu trúc thư mục tương đối của các tệp được xử lý. Cách này phù hợp khi muốn tạo một bản đầu vào sạch cho bước đóng gói hoặc kiểm tra mà vẫn giữ nguyên nội dung ban đầu trong `src`.

## 3. Chọn kiểu kết thúc dòng bằng eol

Thuộc tính `eol` xác định kiểu kết thúc dòng đầu ra. Các giá trị thường dùng:

| Giá trị | Kết quả |
|---|---|
| `lf` | Mỗi dòng kết thúc bằng LF (`0A`) |
| `crlf` | Mỗi dòng kết thúc bằng CRLF (`0D 0A`) |
| `cr` | Mỗi dòng kết thúc bằng CR (`0D`) |
| `asis` | Giữ nguyên quy ước kết thúc dòng hiện có |

Ví dụ chuẩn hóa mã nguồn sang LF:

```xml
<fixcrlf
    srcdir="src/main/java"
    destdir="build/normalized-sources"
    includes="**/*.java"
    eol="lf" />
```

Ví dụ chuẩn hóa tệp batch hoặc văn bản dành cho môi trường Windows sang CRLF:

```xml
<fixcrlf
    srcdir="scripts"
    destdir="build/windows-scripts"
    includes="**/*.bat,**/*.cmd,**/*.txt"
    eol="crlf" />
```

`asis` hữu ích khi muốn dùng `fixcrlf` để điều chỉnh một tùy chọn khác nhưng không yêu cầu chuyển đổi kiểu xuống dòng. Nếu mục tiêu là loại bỏ trạng thái hỗn hợp và ép toàn bộ tệp về một quy ước, hãy chọn rõ `lf`, `crlf` hoặc `cr`.

## 4. Giới hạn tệp được xử lý

Không nên áp dụng `fixcrlf` lên toàn bộ thư mục dự án một cách tùy tiện. Task này dành cho nội dung văn bản; các tệp nhị phân như JAR, ZIP, ảnh, PDF hoặc dữ liệu đã mã hóa không phải đối tượng phù hợp để chuyển đổi ký tự kết thúc dòng.

Các thuộc tính `includes` và `excludes` giúp giới hạn phạm vi:

```xml
<fixcrlf
    srcdir="project"
    destdir="build/normalized"
    includes="**/*.java,**/*.xml,**/*.properties,**/*.md"
    excludes="**/generated/**,**/vendor/**"
    eol="lf" />
```

Ở đây Ant chỉ xử lý các phần mở rộng được liệt kê, đồng thời bỏ qua các thư mục sinh tự động và mã nguồn bên thứ ba. Có thể dùng các mẫu `*` và `**` theo quy tắc chọn đường dẫn của Ant: `*` khớp trong một thành phần đường dẫn, còn `**` có thể đi qua nhiều cấp thư mục.

Một target riêng giúp bước chuẩn hóa có thể được gọi rõ ràng:

```xml
<target name="normalize-text">
    <fixcrlf
        srcdir="src"
        destdir="build/normalized"
        includes="**/*.java,**/*.xml,**/*.properties"
        excludes="**/generated/**"
        eol="lf" />
</target>
```

Việc chọn danh sách phần mở rộng rõ ràng giúp tránh làm hỏng dữ liệu nhị phân. Nếu một thư mục chứa cả văn bản và binary, hãy dùng include cụ thể thay vì mặc định quét mọi tệp.

## 5. Xử lý tab bằng thuộc tính tab

Ngoài ký tự xuống dòng, `fixcrlf` còn có thể chuẩn hóa ký tự tab. Thuộc tính `tab` nhận các giá trị:

| Giá trị | Hành vi |
|---|---|
| `asis` | Giữ nguyên tab hiện có |
| `add` | Chuyển các khoảng trắng phù hợp thành ký tự tab |
| `remove` | Mở rộng ký tự tab thành khoảng trắng |

Thuộc tính `tablength` xác định độ rộng tab được dùng khi chuyển đổi. Ví dụ, để mở rộng tab thành khoảng trắng theo độ rộng 4:

```xml
<fixcrlf
    srcdir="src"
    destdir="build/normalized"
    includes="**/*.java"
    eol="lf"
    tab="remove"
    tablength="4" />
```

Khi `tab="remove"`, các tab trong nội dung được thay bằng số khoảng trắng tương ứng với vị trí tab stop tiếp theo, theo độ rộng được cấu hình. Ngược lại, `tab="add"` nén các chuỗi khoảng trắng thích hợp thành tab. Việc chuyển đổi có thể làm thay đổi cách căn lề khi công cụ hiển thị tab với độ rộng khác nhau.

Nếu dự án đã có quy ước định dạng mã nguồn riêng, không nên bật chuyển đổi tab chỉ vì đang chuẩn hóa line ending. Dùng `tab="asis"` hoặc bỏ qua việc thay đổi tab để giữ nội dung căn lề như hiện tại.

## 6. Xử lý ký tự EOF kiểu DOS

Một số tệp văn bản theo quy ước DOS cũ có thể chứa ký tự Ctrl-Z (`0x1A`) ở cuối tệp để đánh dấu EOF. Ký tự này khác với CR, LF và CRLF; nó không phải ký tự xuống dòng.

Thuộc tính `eof` điều khiển việc xử lý dấu EOF kiểu DOS:

| Giá trị | Hành vi |
|---|---|
| `asis` | Giữ nguyên trạng thái ký tự EOF hiện có |
| `add` | Thêm ký tự EOF kiểu DOS |
| `remove` | Loại bỏ ký tự EOF kiểu DOS |

Ví dụ loại bỏ dấu Ctrl-Z trong các tệp văn bản được xử lý:

```xml
<fixcrlf
    srcdir="legacy"
    destdir="build/legacy-normalized"
    includes="**/*.txt"
    eol="crlf"
    eof="remove" />
```

Không nhầm `eof` với việc thêm hoặc xóa ký tự xuống dòng ở cuối dòng cuối cùng. `eof` nói về dấu EOF kiểu DOS, còn `eol` điều khiển ký tự kết thúc dòng. Với dự án hiện đại không sử dụng dấu Ctrl-Z, thường có thể giữ `eof="asis"` hoặc không cấu hình thuộc tính này.

## 7. Encoding đầu vào và đầu ra

Chuẩn hóa line ending không chỉ liên quan đến byte CR và LF. Task còn phải đọc và ghi văn bản theo encoding phù hợp. Nếu nguồn dùng UTF-8 nhưng task đọc theo encoding mặc định khác, ký tự tiếng Việt hoặc ký tự ngoài ASCII có thể bị biến dạng khi ghi lại.

Hai thuộc tính cần quan tâm:

- `encoding`: encoding dùng để đọc tệp nguồn.
- `outputencoding`: encoding dùng để ghi tệp kết quả. Nếu không khai báo, output encoding thường theo encoding đầu vào được chọn.

Ví dụ đọc và ghi UTF-8:

```xml
<fixcrlf
    srcdir="src"
    destdir="build/normalized"
    includes="**/*.properties,**/*.xml,**/*.md"
    eol="lf"
    encoding="UTF-8"
    outputencoding="UTF-8" />
```

Nếu các tệp nguồn có encoding khác nhau, không nên ép tất cả vào cùng một cấu hình mà không xác định nguồn. Có thể chia thành nhiều nhóm xử lý với encoding riêng. Khi chỉ muốn đổi CRLF sang LF và giữ nguyên nội dung ký tự, hãy khai báo encoding khớp với dữ liệu thực tế.

## 8. Giữ thời gian sửa đổi của tệp

Khi task ghi lại tệp, thời gian sửa đổi có thể thay đổi. Nếu quy trình build cần giữ timestamp gốc, có thể dùng thuộc tính `preservelastmodified`:

```xml
<fixcrlf
    srcdir="src"
    destdir="build/normalized"
    includes="**/*.txt"
    eol="lf"
    preservelastmodified="true" />
```

Việc giữ timestamp hữu ích khi các bước incremental hoặc công cụ bên ngoài dựa vào thời gian sửa đổi để xác định tệp cần xử lý. Tuy nhiên, timestamp không chứng minh nội dung giống nhau; nếu cần kiểm tra tính toàn vẹn, hãy so sánh nội dung hoặc checksum theo quy trình riêng.

## 9. Ví dụ buildfile hoàn chỉnh

Ví dụ sau tạo một thư mục chứa bản văn bản đã chuẩn hóa. Nguồn nằm trong `src`; kết quả được ghi vào `build/normalized`. Các tệp Java, XML, properties và Markdown được chuyển về LF, giữ tab hiện tại và dùng UTF-8.

```xml
<project name="normalize-text-files" default="normalize">

    <property name="source.dir" value="src" />
    <property name="normalized.dir" value="build/normalized" />

    <target name="clean-normalized">
        <delete dir="${normalized.dir}" />
    </target>

    <target name="normalize" depends="clean-normalized">
        <mkdir dir="${normalized.dir}" />

        <fixcrlf
            srcdir="${source.dir}"
            destdir="${normalized.dir}"
            includes="**/*.java,**/*.xml,**/*.properties,**/*.md"
            excludes="**/generated/**,**/vendor/**"
            eol="lf"
            tab="asis"
            eof="asis"
            encoding="UTF-8"
            outputencoding="UTF-8"
            preservelastmodified="true" />
    </target>

</project>
```

Khi chạy:

```shell
ant normalize
```

Ant xóa thư mục kết quả cũ, tạo lại thư mục đích và ghi các tệp văn bản đã chọn với line ending LF. Các thư mục `generated` và `vendor` không được xử lý. Nguồn ban đầu vẫn nằm trong `src` vì `destdir` trỏ sang một vị trí khác.

Nếu muốn chuẩn hóa trực tiếp các tệp trong thư mục nguồn, có thể bỏ `destdir`, nhưng khi đó task sẽ ghi lại tệp tại chỗ. Chỉ nên làm như vậy khi đó là hành vi mong muốn và các thay đổi nội dung đã được quản lý trong quy trình làm việc.

## 10. Khi nào nên dùng fixcrlf?

`fixcrlf` phù hợp với các bước build cần tạo ra tệp văn bản có quy ước xuống dòng cụ thể, ví dụ:

- Chuẩn hóa mã nguồn trước khi tạo archive.
- Chuẩn hóa script trước khi phát hành cho một môi trường đích.
- Làm sạch tệp văn bản được tạo từ nhiều nguồn khác nhau.
- Tạo bản sao có line ending thống nhất để chạy kiểm tra hoặc so sánh.
- Chuyển đổi tệp legacy có CR hoặc CRLF sang LF.

Nếu mục tiêu chỉ là quy định cách Git xử lý line ending khi checkout và commit, có thể cấu hình `.gitattributes`. Git và `fixcrlf` hoạt động ở các giai đoạn khác nhau: Git quản lý cách nội dung được lưu/checkout trong repository, còn `fixcrlf` là một bước build chủ động đọc và ghi các tệp theo cấu hình Ant. Một dự án có thể dùng cả hai, nhưng nên xác định một quy ước thống nhất để tránh việc hai công cụ liên tục biến đổi qua lại.

## 11. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Git hiển thị gần như mọi dòng là thay đổi | Tệp có line ending khác với quy ước repository hoặc bị trộn CRLF/LF | Chọn một kiểu `eol` thống nhất và áp dụng có kiểm soát |
| Ký tự tiếng Việt bị lỗi sau khi chạy task | `encoding` đọc nguồn không khớp encoding thực tế hoặc output encoding không phù hợp | Xác định encoding nguồn và khai báo `encoding`/`outputencoding` tương ứng |
| Tệp binary bị thay đổi hoặc hỏng | Mẫu include đã chọn cả dữ liệu nhị phân | Giới hạn `includes` vào phần mở rộng văn bản và loại trừ thư mục binary |
| Tệp vẫn giữ kiểu xuống dòng cũ | `eol="asis"` được dùng hoặc tệp không nằm trong tập được chọn | Chọn `lf`, `crlf` hoặc `cr`, kiểm tra include/exclude |
| Tab trong mã nguồn thay đổi cách căn lề | `tab="add"` hoặc `tab="remove"` đã chuyển đổi tab và khoảng trắng | Dùng `tab="asis"` nếu chỉ cần đổi line ending |
| Có ký tự Ctrl-Z ở cuối tệp | Tệp dùng dấu EOF kiểu DOS | Chọn `eof="remove"` nếu yêu cầu loại bỏ dấu này |
| Tệp nguồn thay đổi ngoài dự kiến | Không đặt `destdir`, task ghi kết quả tại chỗ | Khai báo `destdir` để giữ bản nguồn |
| Build không xử lý một số tệp | Mẫu include không khớp hoặc tệp bị exclude | Kiểm tra đường dẫn tương đối và danh sách mẫu |

Khi gặp lỗi, nên kiểm tra lần lượt danh sách tệp được chọn, kiểu line ending đầu ra, encoding đọc/ghi, tùy chọn tab và EOF. Nếu nội dung bị biến dạng, hãy so sánh một tệp nguồn với bản kết quả ở mức byte để xác định chính xác thay đổi.

## 12. Quy trình chuẩn hóa xuống dòng trong buildfile

Khi thêm `fixcrlf` vào một dự án, có thể thực hiện theo trình tự sau:

1. Xác định quy ước line ending mà đầu ra cần sử dụng: LF, CRLF hay CR.
2. Xác định chính xác nhóm tệp văn bản cần xử lý; loại trừ binary và thư mục không thuộc phạm vi.
3. Chọn cách ghi kết quả: dùng `destdir` để tạo bản đã chuẩn hóa riêng, hoặc bỏ `destdir` nếu cần sửa trực tiếp nguồn.
4. Đặt `eol` rõ ràng; không dùng `asis` nếu mục tiêu là chuyển toàn bộ tệp về một kiểu thống nhất.
5. Xác định encoding đầu vào và đầu ra để bảo toàn nội dung ký tự.
6. Chỉ điều chỉnh `tab` và `eof` khi dự án có yêu cầu cụ thể đối với các định dạng đó.
7. Chạy target trên một tập tệp đại diện và so sánh kết quả để xác nhận line ending cùng nội dung ký tự đúng như mong muốn.

`fixcrlf` giúp Ant kiểm soát cách các tệp văn bản được ghi ra trong quá trình build. Chọn đúng phạm vi, kiểu `eol` và encoding sẽ giúp chuẩn hóa xuống dòng mà vẫn giữ nguyên nội dung cần thiết của tệp.
