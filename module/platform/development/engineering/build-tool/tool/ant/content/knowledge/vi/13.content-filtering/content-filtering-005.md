# Chuyển đổi encoding và xử lý tiếng Việt trong Apache Ant

Khi buildfile sao chép hoặc lọc nội dung văn bản, Apache Ant phải đọc byte từ file nguồn thành ký tự, xử lý nội dung, rồi ghi ký tự ra file đích. Nếu charset đầu vào hoặc đầu ra không đúng với cách file thực sự được mã hóa, các ký tự tiếng Việt có dấu có thể bị biến thành chuỗi khó đọc như `Tiáº¿ng Viá»‡t` hoặc dấu hỏi `????`.

Để xử lý tiếng Việt ổn định, cần phân biệt ba việc: **encoding** xác định cách byte biểu diễn ký tự; **filtering** thay token hoặc biến đổi nội dung; **normalization** chuẩn hóa cách biểu diễn Unicode. Ba việc này liên quan nhưng không thay thế cho nhau. Trong dự án mới, nên thống nhất UTF-8 cho buildfile, tài nguyên văn bản và đầu ra, đồng thời khai báo encoding tường minh ở các bước đọc/ghi có xử lý nội dung.

## 1. Charset, Unicode và UTF-8

Unicode gán mã cho ký tự. Ví dụ, chữ `ế` có mã Unicode U+1EBF. Encoding là quy tắc chuyển mã ký tự thành byte để lưu trữ hoặc truyền đi. UTF-8 là một cách mã hóa Unicode phổ biến, có thể biểu diễn đầy đủ tiếng Việt và các ngôn ngữ khác.

Một file văn bản không tự mang theo thông tin đáng tin cậy về encoding chỉ vì tên file có phần mở rộng `.txt`, `.xml` hay `.properties`. Encoding thực tế phải được thống nhất giữa chương trình ghi và chương trình đọc. XML có thể có khai báo encoding trong phần mở đầu, nhưng khai báo đó cũng phải khớp với byte thật của file.

Ví dụ, cùng một chuỗi tiếng Việt:

```text
Xin chào, tôi đang học Apache Ant.
```

có thể được lưu bằng UTF-8 hoặc một charset cũ như `windows-1258`. Nếu byte UTF-8 bị đọc nhầm như `windows-1252`, ký tự có dấu sẽ biến thành mojibake. Nếu dữ liệu không thể biểu diễn trong charset đầu ra, ký tự có thể bị thay bằng dấu hỏi hoặc ký tự thay thế.

| Khái niệm | Ý nghĩa |
|---|---|
| Unicode | Hệ mã ký tự, ví dụ U+1EBF cho `ế` |
| UTF-8 | Encoding biểu diễn Unicode thành byte |
| `windows-1258` | Một charset Windows cũ có thể gặp trong dữ liệu tiếng Việt legacy |
| Mojibake | Văn bản bị đọc bằng charset sai, ví dụ `Tiáº¿ng Viá»‡t` |
| Unicode normalization | Chuẩn hóa chuỗi ký tự tương đương về một dạng biểu diễn thống nhất |

UTF-8 nên là lựa chọn mặc định cho tài nguyên mới. Với dữ liệu legacy, phải xác định đúng encoding nguồn trước khi chuyển đổi; đổi nhãn encoding mà không chuyển byte không sửa được nội dung.

## 2. Encoding trong task `copy` khi filtering

Task `copy` hỗ trợ hai thuộc tính quan trọng khi có xử lý nội dung văn bản:

- `encoding`: charset dùng để đọc nội dung file nguồn khi filtering.
- `outputencoding`: charset dùng để ghi nội dung file đích sau filtering. Nếu không khai báo, Ant dùng giá trị của `encoding` làm mặc định cho đầu ra.

Ví dụ file nguồn `src/messages.properties` chứa token:

```properties
app.title=@app.title@
app.greeting=@app.greeting@
```

Buildfile thay token bằng giá trị tiếng Việt và giữ UTF-8 ở cả hai phía:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="encoding-demo" default="filter-messages">

    <property name="app.title" value="Quản lý kho hàng"/>
    <property name="app.greeting" value="Xin chào, chúc bạn học tốt!"/>

    <target name="filter-messages">
        <mkdir dir="build/config"/>
        <copy file="src/messages.properties"
              tofile="build/config/messages.properties"
              encoding="UTF-8"
              outputencoding="UTF-8">
            <filterset>
                <filter token="app.title" value="${app.title}"/>
                <filter token="app.greeting" value="${app.greeting}"/>
            </filterset>
        </copy>
    </target>

</project>
```

Kết quả file đích:

```properties
app.title=Quản lý kho hàng
app.greeting=Xin chào, chúc bạn học tốt!
```

Ant đọc file nguồn bằng UTF-8, thay các token trong nội dung văn bản, rồi ghi file đích bằng UTF-8. Buildfile `build.xml` cũng phải được lưu bằng UTF-8 để các giá trị như `Quản lý kho hàng` và `Xin chào` được parser XML đọc đúng.

`encoding` và `outputencoding` có ý nghĩa trong luồng xử lý văn bản/filtering. Khi chỉ copy file nhị phân hoặc copy nguyên byte mà không có filter, không nên coi hai thuộc tính này là một công cụ chuyển mã tổng quát. JAR, ảnh, PDF và các file nhị phân cần được copy nguyên byte, không đưa qua bộ lọc văn bản.

## 3. Chuyển từ encoding cũ sang UTF-8

Một số dự án lâu năm có thể lưu văn bản tiếng Việt bằng charset Windows như `windows-1258`. Nếu file nguồn thực sự dùng charset đó và bước copy có filtering, có thể chỉ định charset nguồn và đầu ra riêng:

```xml
<copy file="legacy/messages.txt"
      tofile="build/messages.txt"
      encoding="windows-1258"
      outputencoding="UTF-8">
    <filterset>
        <filter token="build.version" value="${build.version}"/>
    </filterset>
</copy>
```

Ở ví dụ này, Ant giải mã byte nguồn theo `windows-1258`, thực hiện thay token, sau đó ghi ký tự sang UTF-8. Chỉ dùng tên charset đúng với dữ liệu thực tế và được JVM đang chạy Ant hỗ trợ. Không được khai báo `encoding="UTF-8"` cho file thực tế đang lưu bằng `windows-1258`, vì parser sẽ giải mã byte sai ngay từ đầu.

Nếu mục tiêu chỉ là chuyển encoding mà không thay token, hãy dùng một bước chuyển đổi văn bản chuyên biệt, chẳng hạn task `concat` ở chế độ văn bản với `encoding` và `outputencoding`, hoặc công cụ chuyển mã phù hợp. Không giả định `copy` sẽ chuyển mã byte chỉ vì đã đặt hai thuộc tính encoding trong trường hợp không có filtering.

Ví dụ `concat` chuyển một file văn bản từ `windows-1258` sang UTF-8:

```xml
<target name="convert-legacy-text">
    <mkdir dir="build/utf8"/>
    <concat destfile="build/utf8/messages.txt"
            encoding="windows-1258"
            outputencoding="UTF-8">
        <filelist dir="legacy" files="messages.txt"/>
    </concat>
</target>
```

`concat` là task ghép nội dung tài nguyên văn bản. Với một file đầu vào, có thể dùng nó để đọc bằng charset nguồn và ghi bằng charset đích. Hãy kiểm tra phiên bản Ant đang dùng và tài liệu task nếu buildfile cần chạy trên nhiều môi trường khác nhau.

### Không đoán encoding từ cách văn bản hiển thị

Khi thấy `Tiáº¿ng Viá»‡t`, không nên thử thay encoding ngẫu nhiên nhiều lần. Hãy tìm nguồn tạo file, cấu hình editor hoặc hệ thống cũ, rồi xác định charset gốc. Một chuỗi đã bị giải mã sai và lưu lại nhiều lần có thể đã mất thông tin; đổi encoding lần nữa không thể tự khôi phục byte ban đầu.

Các charset như TCVN3 hoặc VNI có thể xuất hiện trong dữ liệu cũ, nhưng tên gọi và bộ chuyển đổi không giống nhau giữa các công cụ. Chỉ dùng charset mà JVM thực sự hỗ trợ hoặc cài đặt bộ chuyển đổi có chủ đích. Không tự thay `windows-1258` bằng `TCVN3` chỉ vì file đều chứa tiếng Việt.

## 4. Encoding của buildfile và file XML

Buildfile Ant bản thân nó là XML. Nếu chứa tiếng Việt trực tiếp trong thuộc tính hoặc nội dung, hãy khai báo encoding ở đầu file và lưu byte theo đúng encoding đó:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="vietnamese-build" default="show-message">
    <property name="message" value="Xin chào, các bạn!"/>

    <target name="show-message">
        <echo message="${message}"/>
    </target>
</project>
```

Không khai báo `encoding="UTF-8"` trong XML nếu file thực tế được lưu bằng charset khác. XML parser dựa vào BOM, quy tắc XML và khai báo để xác định cách đọc byte; thông tin không khớp có thể làm parser báo lỗi hoặc đọc sai ký tự.

### XML được copy và filtering

Giả sử file XML nguồn có khai báo:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<message>Xin chào</message>
```

Nếu output cũng là UTF-8, giữ khai báo như trên. Nếu chuyển file sang một encoding khác, khai báo XML ở đầu file phải phản ánh encoding đầu ra. Nếu chỉ đổi `outputencoding` mà để nguyên khai báo XML cũ, parser XML ở bước sau có thể giải mã sai.

Với HTML, thẻ meta charset cũng phải khớp với byte file đích, ví dụ:

```html
<meta charset="UTF-8">
```

Đối với JSON, cần tuân theo encoding mà hệ thống tiêu thụ yêu cầu; UTF-8 là lựa chọn phổ biến và nên được thống nhất trong dự án.

## 5. Đọc file văn bản và properties với encoding rõ ràng

Khi Ant nạp nội dung file vào property, hãy chỉ định encoding nếu task hỗ trợ. Ví dụ dùng `loadfile` để đọc một file văn bản UTF-8:

```xml
<target name="show-notice">
    <loadfile property="release.notice"
              srcFile="src/notice.txt"
              encoding="UTF-8"/>
    <echo message="${release.notice}"/>
</target>
```

`loadfile` đọc nội dung file thành một property. Nếu file chứa tiếng Việt mà không chỉ định encoding, kết quả có thể phụ thuộc charset mặc định của JVM/máy chạy Ant. Không nên dùng property để giữ file nhị phân hoặc nội dung quá lớn.

Với file cấu hình `.properties`, cần xét cả encoding mà Ant dùng để đọc lẫn cách ứng dụng Java đọc file đó. Ví dụ:

```xml
<target name="load-build-properties">
    <loadproperties srcFile="config/build.properties"
                    encoding="UTF-8"/>
</target>
```

`loadproperties` đưa các cặp key/value vào property của Ant. Ở phía ứng dụng, `java.util.Properties.load(InputStream)` theo hợp đồng truyền thống đọc dữ liệu theo ISO-8859-1 và dùng escape `\\uXXXX` cho ký tự ngoài phạm vi đó; `Properties.load(Reader)` thì đọc theo charset mà Reader đã chọn. Một số framework hoặc API cấu hình có quy ước UTF-8 riêng. Vì vậy, file được Ant tạo ra phải khớp với cách runtime thực sự đọc file, không chỉ khớp với cách editor hiển thị.

Ví dụ một giá trị Unicode được biểu diễn bằng escape trong file properties truyền thống:

```properties
app.greeting=Ch\u00E0o m\u1EEBng b\u1EA1n
```

Khi đọc bằng `Properties.load(InputStream)`, các escape được chuyển thành chuỗi Unicode. Nếu ứng dụng đọc file qua UTF-8 Reader, có thể lưu ký tự tiếng Việt trực tiếp theo UTF-8, miễn là quy ước giữa bên tạo và bên đọc được thống nhất.

## 6. Encoding khi biên dịch Java source

Encoding của Java source là một cấu hình khác với encoding của file được copy. Task `javac` có thuộc tính `encoding` để chỉ định charset của file `.java`:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           encoding="UTF-8"
           includeantruntime="false"/>
</target>
```

Nếu source chứa literal tiếng Việt:

```java
public class Greeting {
    public static void main(String[] args) {
        System.out.println("Xin chào các bạn!");
    }
}
```

thì compiler phải đọc file `.java` bằng đúng encoding đã dùng khi lưu file. Khai báo `encoding="UTF-8"` giúp build nhất quán giữa máy lập trình viên và CI, kể cả khi charset mặc định của hai máy khác nhau.

Thuộc tính `encoding` của `javac` điều khiển cách compiler đọc source; nó không quyết định encoding mà ứng dụng dùng khi đọc file cấu hình ở runtime hoặc khi ghi nội dung ra console.

## 7. Filtering với `filterset` và `filterchain`

Ant cung cấp hai cách phổ biến để biến đổi nội dung khi copy:

- `filterset`: thay token theo cặp token/giá trị. Mặc định token được bao bởi ký tự `@`, ví dụ `@app.name@`.
- `filterchain`: áp dụng một chuỗi bộ lọc văn bản, chẳng hạn thay chuỗi, lọc dòng hoặc xử lý token theo quy tắc phức tạp hơn.

Ví dụ `filterset` phù hợp khi chỉ cần thay một số placeholder đã biết:

```xml
<copy file="src/config/app.yml"
      tofile="build/config/app.yml"
      encoding="UTF-8"
      outputencoding="UTF-8">
    <filterset begintoken="@{" endtoken="}">
        <filter token="application.name" value="dịch vụ quản lý kho"/>
        <filter token="application.owner" value="Nhóm Nền tảng"/>
    </filterset>
</copy>
```

Nguồn tương ứng dùng token `@{application.name}` và `@{application.owner}`. Có thể thay delimiter để tránh xung đột với cú pháp placeholder của framework hoặc template engine khác.

Ví dụ `filterchain` dùng `replacetokens`:

```xml
<copy file="src/messages.txt"
      tofile="build/messages.txt"
      encoding="UTF-8"
      outputencoding="UTF-8">
    <filterchain>
        <replacetokens begintoken="@{" endtoken="}">
            <token key="user.name" value="Nguyễn An"/>
            <token key="message" value="Chào mừng bạn đến với hệ thống"/>
        </replacetokens>
    </filterchain>
</copy>
```

Nguồn tương ứng dùng token `@{user.name}` và `@{message}`. Chọn delimiter ít có khả năng xuất hiện trong nội dung tự nhiên để tránh thay nhầm. Không dùng đồng thời nhiều filter thay cùng một token nếu không xác định rõ thứ tự xử lý.

## 8. Unicode normalization và dấu tiếng Việt

Một ký tự tiếng Việt có thể có nhiều cách biểu diễn Unicode tương đương. Ví dụ, một chữ có dấu có thể được lưu dưới dạng một code point dựng sẵn hoặc chữ cái cơ sở kết hợp với một dấu riêng. Hai chuỗi có thể hiển thị giống nhau nhưng có dãy code point khác nhau.

Điều này không phải lỗi encoding. UTF-8 có thể mã hóa cả hai dạng. Tuy nhiên, so sánh chuỗi, tìm kiếm token hoặc xử lý tên file có thể cho kết quả khác nếu hai bên dùng dạng normalization khác nhau.

- NFC thường được dùng để đưa chuỗi về dạng hợp thành khi có thể.
- NFD biểu diễn ký tự bằng chữ cơ sở và dấu kết hợp.
- Ant `copy` và `filterset` không tự động chuẩn hóa Unicode cho toàn bộ nội dung.

Nếu token tiếng Việt không được thay dù nhìn bằng mắt giống hệt, hãy kiểm tra cả byte/charset lẫn chuỗi Unicode thực tế. Có thể chuẩn hóa dữ liệu đầu vào ở bước tạo nội dung hoặc bằng một công cụ xử lý Unicode chuyên biệt trước khi đưa vào build. Đừng cố sửa normalization bằng cách đổi `encoding`.

## 9. Phân biệt lỗi encoding với lỗi hiển thị terminal

Không phải mọi trường hợp tiếng Việt hiển thị sai trong log đều có nghĩa file đầu ra bị hỏng. Có thể byte file đúng UTF-8 nhưng terminal đang giải mã output theo code page khác hoặc font terminal không hiển thị glyph tương ứng.

| Dấu hiệu | Khả năng nguyên nhân | Cách kiểm tra |
|---|---|---|
| File mở trong editor cũng thành `Tiáº¿ng Viá»‡t` | Byte UTF-8 bị đọc bằng charset khác | Mở lại file bằng cách chọn UTF-8 và kiểm tra encoding thật |
| File đúng trong editor nhưng log Ant sai | Encoding đầu ra của JVM hoặc terminal không khớp | Kiểm tra cấu hình terminal/JVM; đừng sửa file nguồn chỉ để làm log đẹp |
| Một số ký tự thành `?` sau filtering | Charset đầu ra không biểu diễn được ký tự hoặc bước giải mã đã sai | Chọn outputencoding có thể biểu diễn Unicode, ưu tiên UTF-8 |
| Token chứa tiếng Việt không được thay | Token nguồn và token trong filter khác chuỗi hoặc khác Unicode normalization | So sánh chính xác token, dấu, khoảng trắng và code point |
| XML parser báo encoding không hợp lệ | XML declaration/BOM không khớp với byte file | Kiểm tra byte đầu file và khai báo encoding |

Khi chẩn đoán, hãy xem file đầu ra bằng editor có khả năng chọn encoding, kiểm tra khai báo XML/HTML và thử đọc file bằng chính API mà ứng dụng sử dụng. Không dùng ảnh chụp terminal làm bằng chứng duy nhất về encoding của file.

## 10. Những lỗi thường gặp và cách phòng tránh

| Lỗi | Nguyên nhân | Cách xử lý |
|---|---|---|
| Tiếng Việt thành mojibake sau copy | `encoding` không khớp charset của file nguồn | Xác định charset nguồn và khai báo chính xác |
| Ký tự thành dấu hỏi | Charset đầu ra không thể biểu diễn ký tự hoặc đã mất dữ liệu ở bước trước | Ghi bằng UTF-8 và kiểm tra lại dữ liệu trước filtering |
| Local chạy đúng nhưng CI lỗi | Charset mặc định JVM/OS khác nhau | Khai báo `encoding`, `outputencoding` và `javac encoding` tường minh |
| XML đích không đọc được | XML declaration không khớp byte đầu ra | Cập nhật khai báo XML đồng bộ với outputencoding |
| `.properties` hiển thị sai trong ứng dụng | Ant và runtime dùng quy ước charset khác nhau | Kiểm tra API đọc properties và chọn UTF-8 hoặc Unicode escape theo hợp đồng runtime |
| Token không thay | Delimiter hoặc nội dung token không khớp | Kiểm tra `begintoken`, `endtoken`, dấu tiếng Việt và khoảng trắng |
| File ảnh/JAR bị hỏng | Filtering áp dụng cho dữ liệu nhị phân | Copy nguyên byte, không đặt filterset/filterchain cho file nhị phân |
| Nội dung giống nhau nhưng so sánh thất bại | Hai chuỗi dùng Unicode normalization khác nhau | Chuẩn hóa chuỗi trước bước so sánh bằng công cụ phù hợp |

Các nguyên tắc thực tế:

- Lưu `build.xml`, file nguồn văn bản và file cấu hình mới bằng UTF-8.
- Khai báo encoding ở từng task có đọc/ghi văn bản thay vì phụ thuộc charset mặc định của máy.
- Với dữ liệu legacy, xác định encoding nguồn trước khi chuyển sang UTF-8.
- Giữ XML declaration và HTML meta charset đồng bộ với encoding đầu ra.
- Kiểm tra cách runtime đọc `.properties`; không giả định mọi API Java đều đọc UTF-8 theo cùng quy tắc.
- Tách xử lý văn bản khỏi copy file nhị phân.
- Nếu nội dung đúng nhưng log sai, kiểm tra terminal/JVM trước khi thay đổi file.

## 11. Ví dụ buildfile hoàn chỉnh

Ví dụ sau đọc file template UTF-8, thay placeholder bằng giá trị tiếng Việt và ghi kết quả UTF-8. File `src/main/resources/banner.txt` có nội dung:

```text
Ứng dụng: @{app.name}
Thông điệp: @{welcome.message}
```

Buildfile `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="vietnamese-filtering" default="prepare-text" basedir=".">

    <property name="source.encoding" value="UTF-8"/>
    <property name="target.encoding" value="UTF-8"/>
    <property name="app.name" value="Java Learning"/>
    <property name="welcome.message"
              value="Xin chào, chúc bạn học Apache Ant thật tốt!"/>

    <target name="clean">
        <delete dir="build"/>
    </target>

    <target name="prepare-text">
        <mkdir dir="build/resources"/>
        <copy file="src/main/resources/banner.txt"
              tofile="build/resources/banner.txt"
              encoding="${source.encoding}"
              outputencoding="${target.encoding}">
            <filterset begintoken="@{" endtoken="}">
                <filter token="app.name" value="${app.name}"/>
                <filter token="welcome.message"
                        value="${welcome.message}"/>
            </filterset>
        </copy>
    </target>

</project>
```

Chạy `ant prepare-text` sẽ tạo `build/resources/banner.txt` với các giá trị đã thay thế. Vì cả source template và buildfile đều là UTF-8, Ant đọc được tiếng Việt; `outputencoding` đảm bảo file đích được ghi bằng UTF-8.

## 12. Bài tập tự kiểm tra

**Bài 1.** Trong task `copy` có filtering, `encoding` và `outputencoding` khác nhau ở điểm nào?

**Đáp án:** `encoding` chỉ charset dùng để đọc file nguồn; `outputencoding` chỉ charset dùng để ghi file đích sau khi xử lý. Nếu bỏ `outputencoding`, Ant mặc định dùng giá trị `encoding`.

**Bài 2.** File nguồn thực sự là UTF-8 nhưng buildfile đặt `encoding="windows-1258"`. Điều gì có thể xảy ra?

**Đáp án:** Ant giải mã byte theo charset sai, khiến ký tự tiếng Việt bị biến dạng trước khi filtering. Phải khai báo charset đúng với byte nguồn.

**Bài 3.** Có thể dùng `copy encoding="UTF-8" outputencoding="UTF-8"` để chuyển mọi file trong thư mục, kể cả JAR và ảnh, không?

**Đáp án:** Không. Hai thuộc tính này dành cho luồng xử lý văn bản/filtering. File nhị phân phải được copy nguyên byte và không đưa qua filter.

**Bài 4.** File XML đích được ghi bằng UTF-8 nhưng khai báo `encoding="windows-1258"`. Vấn đề là gì?

**Đáp án:** Parser XML có thể giải mã byte theo khai báo sai. XML declaration phải phản ánh encoding thật của file đích.

**Bài 5.** File hiển thị đúng trong editor nhưng log Ant hiển thị sai tiếng Việt. Có nên chuyển encoding file nguồn không?

**Đáp án:** Chưa nên. Hãy kiểm tra encoding của JVM và terminal trước; có thể file đúng nhưng log bị giải mã sai khi hiển thị.

## Kết luận

Xử lý tiếng Việt trong Apache Ant cần thống nhất encoding từ lúc lưu buildfile, đọc nguồn, filtering đến ghi đầu ra. Với `copy`, `encoding` mô tả charset đầu vào và `outputencoding` mô tả charset đầu ra trong quá trình xử lý văn bản. Các task đọc properties và `javac` cũng cần encoding phù hợp với dữ liệu của chúng. Khi phân biệt rõ charset, filtering và Unicode normalization, đồng thời kiểm tra quy ước của ứng dụng tiêu thụ file, build sẽ tạo được tài nguyên tiếng Việt nhất quán trên máy phát triển và CI.

