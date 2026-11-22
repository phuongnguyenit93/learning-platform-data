# Thay thế nội dung bằng `replace` và `replaceregexp`

Trong quá trình build, dự án thường cần cập nhật nội dung của tệp cấu hình, tài nguyên hoặc tài liệu. Ví dụ, có thể đổi một địa chỉ dịch vụ cũ, cập nhật phiên bản, sửa một cờ cấu hình hoặc chuẩn hóa định dạng văn bản. Apache Ant cung cấp hai task hữu ích cho công việc này: `<replace>` và `<replaceregexp>`.

`<replace>` tìm một chuỗi ký tự cụ thể rồi thay bằng chuỗi khác. `<replaceregexp>` tìm nội dung theo biểu thức chính quy (regular expression, hay regex), nhờ đó có thể thay những chuỗi biến đổi theo một mẫu. Hiểu rõ sự khác nhau giúp chọn đúng task, tránh thay nhầm nội dung và giữ cho build có thể lặp lại.

## 1. Chọn task theo kiểu thay thế

| Nhu cầu | Task phù hợp | Cách tìm nội dung |
|---|---|---|
| Thay một token cố định như `@app.name@` | `<replace>` | So khớp chuỗi literal |
| Đổi một URL cố định thành URL mới | `<replace>` | So khớp nguyên văn chuỗi cũ |
| Thay mọi phiên bản có dạng `version=x.y.z` | `<replaceregexp>` | So khớp theo mẫu regex |
| Đổi các mã như `INV-1234` thành `1234-INV` | `<replaceregexp>` | Dùng nhóm bắt (capture groups) |
| Xóa một chuỗi cố định | `<replace>` | Thay chuỗi cần xóa bằng chuỗi rỗng |
| Chuẩn hóa nhiều biến thể văn bản theo một quy tắc | `<replaceregexp>` | Dùng mẫu regex và cờ phù hợp |

Hai task đều có thể xử lý một tệp hoặc nhiều tệp thông qua các thuộc tính và resource collection được hỗ trợ. Phạm vi tệp nên được giới hạn rõ để tránh sửa nhầm dữ liệu không liên quan.

## 2. Thay chuỗi literal bằng `<replace>`

Task `<replace>` tìm chuỗi được chỉ định trong thuộc tính `token` và thay bằng giá trị trong `value`. Nội dung tìm kiếm là chuỗi literal, không được diễn giải như regex.

Ví dụ, tệp `src/config/application.properties` có nội dung:

```properties
application.name=@app.name@
service.url=http://old.example.internal/api
feature.preview=true
```

Có thể thay token và URL bằng:

```xml
<replace file="src/config/application.properties"
         token="@app.name@"
         value="Inventory Service"/>

<replace file="src/config/application.properties"
         token="http://old.example.internal/api"
         value="https://api.example.com"/>
```

Sau khi chạy target chứa hai task này, nội dung tương ứng trở thành:

```properties
application.name=Inventory Service
service.url=https://api.example.com
feature.preview=true
```

Các thuộc tính chính:

- `file`: đường dẫn tới một tệp cần xử lý.
- `token`: chuỗi literal cần tìm.
- `value`: chuỗi thay thế. Đặt giá trị rỗng để xóa token.
- `dir`: thư mục gốc khi cần xử lý một nhóm tệp.
- `includes` và `excludes`: mẫu chọn hoặc loại tệp khi làm việc với thư mục.

Khi dùng `file`, task xử lý tệp được chỉ định. Khi dùng `dir` cùng các mẫu include/exclude, task có thể áp dụng thay thế cho nhóm tệp phù hợp. Không dùng đồng thời các cách chỉ định đầu vào theo cách mâu thuẫn; tham khảo tài liệu task của phiên bản Ant đang chạy nếu cần kết hợp thêm nested resources.

## 3. Dùng `<replace>` trong target của buildfile

Ví dụ đầy đủ tạo bản cấu hình đã cập nhật trong thư mục build:

```xml
<project name="replace-demo" default="prepare-config" basedir=".">

    <property name="source.file" location="src/config/application.properties"/>
    <property name="output.dir" location="build/config"/>
    <property name="output.file" location="${output.dir}/application.properties"/>

    <target name="prepare-config">
        <mkdir dir="${output.dir}"/>
        <copy file="${source.file}" tofile="${output.file}"/>
        <replace file="${output.file}"
                 token="@app.name@"
                 value="Inventory Service"/>
        <replace file="${output.file}"
                 token="@app.version@"
                 value="2.1.0"/>
    </target>

</project>
```

Quy trình này sao chép tệp mẫu trước, sau đó thay nội dung trên bản sao trong `build/config`. Nhờ vậy, mỗi lần build có thể tạo lại đầu ra từ mẫu nguồn mà không tích lũy các thay đổi đã áp dụng vào tệp gốc.

Chạy target:

```sh
ant prepare-config
```

Nếu cần thay trực tiếp một tệp nguồn, có thể dùng `file` trỏ thẳng tới tệp đó. Tuy nhiên, với quy trình build có thể chạy lặp lại, thường nên tạo bản đầu ra rồi thay trên bản đó để giữ nguyên dữ liệu nguồn.

## 4. Thay nhiều token bằng nested `<replacefilter>`

Khi một tệp cần thay nhiều token, có thể gom các cặp token/giá trị trong một task `<replace>` bằng nested element `<replacefilter>`:

```xml
<replace file="build/config/application.properties">
    <replacefilter token="@app.name@" value="Inventory Service"/>
    <replacefilter token="@app.version@" value="2.1.0"/>
    <replacefilter token="@service.url@" value="https://api.example.com"/>
</replace>
```

Cách khai báo này giúp các giá trị thay thế của cùng một tệp nằm cạnh nhau, dễ đọc và dễ cập nhật. Có thể kết hợp với một tệp properties hoặc property Ant nếu muốn tách dữ liệu cấu hình khỏi buildfile; khi đó hãy dùng đúng thuộc tính của `replacefilter` được phiên bản Ant hỗ trợ.

Nếu cần thay token trong nhiều tệp, có thể dùng dạng thư mục:

```xml
<replace dir="build/config"
         includes="**/*.properties"
         token="@service.url@"
         value="https://api.example.com"/>
```

Task chỉ áp dụng cho các tệp `.properties` phù hợp với mẫu trong thư mục `build/config`. Mẫu `**/*.properties` chọn tệp có phần mở rộng `.properties` ở thư mục gốc và các thư mục con.

## 5. Xóa chuỗi bằng `<replace>`

Để xóa một chuỗi literal, đặt `value` thành chuỗi rỗng:

```xml
<replace file="build/config/application.properties"
         token="@temporary.comment@"
         value=""/>
```

Ví dụ, nếu tệp có dòng:

```properties
# @temporary.comment@
application.name=Inventory Service
```

thì token `@temporary.comment@` được xóa. Phần còn lại của dòng, bao gồm ký tự `#` và khoảng trắng, vẫn được giữ. Nếu muốn xóa cả dòng hoặc nhiều định dạng biến đổi, regex có thể phù hợp hơn.

## 6. Thay theo mẫu bằng `<replaceregexp>`

Task `<replaceregexp>` dùng biểu thức chính quy để tìm nội dung theo mẫu. Điều này hữu ích khi giá trị cũ có thể khác nhau nhưng tuân theo cùng một định dạng.

Ví dụ, một tệp có thể chứa các dòng:

```properties
application.name=Inventory Service
application.version=1.4.0
build.version=1.4.0
```

Muốn cập nhật mọi dòng có khóa `application.version` hoặc `build.version` thành `2.1.0`, có thể dùng:

```xml
<replaceregexp file="build/config/application.properties"
               match="^(application\.version|build\.version)=.*$"
               replace="\1=2.1.0"
               flags="gm"/>
```

Ở đây:

- `match` là biểu thức regex cần tìm.
- `replace` là nội dung thay thế.
- `flags` điều khiển cách tìm kiếm; `g` thay mọi kết quả phù hợp, `m` bật chế độ multiline cho các neo đầu/cuối dòng.
- `\.` trong XML attribute được truyền tới regex để dấu chấm được hiểu là dấu chấm literal. Dấu chấm không escape trong regex có nghĩa là khớp với một ký tự bất kỳ.
- `\1` tham chiếu nhóm bắt thứ nhất trong biểu thức.

Trong Java regex, các nhóm bắt được đánh số từ 1 theo thứ tự dấu ngoặc mở. Trong ví dụ, nhóm thứ nhất là `application.version` hoặc `build.version`, vì vậy `\1=2.1.0` giữ lại tên khóa và thay phần giá trị.

Lưu ý: trong thuộc tính XML, dấu gạch chéo ngược không phải ký tự escape của XML. Cú pháp `\1` trong ví dụ được đưa nguyên vẹn tới bộ xử lý regex của Ant/Java. Nếu biểu thức có ký tự XML đặc biệt như `&` hoặc `<`, cần escape theo quy tắc XML, ví dụ `&amp;` hoặc `&lt;`.

## 7. Ý nghĩa của các cờ regex

Thuộc tính `flags` điều chỉnh hành vi của phép thay thế. Các cờ thường dùng gồm:

| Cờ | Ý nghĩa |
|---|---|
| `g` | Thay tất cả kết quả phù hợp trong phạm vi xử lý |
| `i` | Không phân biệt chữ hoa/chữ thường |
| `m` | Bật chế độ multiline để `^` và `$` làm việc theo từng dòng |
| `s` | Bật chế độ dotall để dấu chấm có thể khớp cả ký tự xuống dòng |

Các cờ được ghép thành một chuỗi, ví dụ `flags="gi"` để thay toàn bộ kết quả không phân biệt hoa thường. Regex của Ant dựa trên cú pháp biểu thức chính quy Java; hãy dùng cú pháp và cờ mà Java hỗ trợ.

Nếu không có cờ `g`, phép thay thế thường chỉ xử lý kết quả đầu tiên trong từng đơn vị xử lý. Khi cần thay tất cả lần xuất hiện, hãy khai báo `g` rõ ràng.

## 8. Thay thế bằng capture group

Capture group giúp giữ lại một phần nội dung đã tìm thấy trong khi thay đổi phần còn lại.

Ví dụ, đổi mã `INV-1234` thành `1234-INV`:

```xml
<replaceregexp file="build/orders.txt"
               match="([A-Z]+)-([0-9]+)"
               replace="\2-\1"
               flags="g"/>
```

Nếu tệp có:

```text
INV-1234
ORD-5678
```

đầu ra là:

```text
1234-INV
5678-ORD
```

Nhóm `([A-Z]+)` bắt phần chữ cái; nhóm `([0-9]+)` bắt phần số. Chuỗi thay thế `\2-\1` đảo vị trí hai nhóm. Đây là cách xử lý các mẫu dữ liệu có cấu trúc mà `<replace>` literal không thể diễn đạt trực tiếp.

## 9. Xử lý nhiều tệp bằng nested `<fileset>`

`<replaceregexp>` có thể xử lý một tệp cụ thể hoặc một tập hợp tệp thông qua `fileset`:

```xml
<replaceregexp match="http://old\.example\.com"
               replace="https://example.com"
               flags="g">
    <fileset dir="build/resources">
        <include name="**/*.properties"/>
        <include name="**/*.xml"/>
        <exclude name="**/third-party/**"/>
    </fileset>
</replaceregexp>
```

Ví dụ này thay URL trong các tệp `.properties` và `.xml` dưới `build/resources`, đồng thời bỏ qua thư mục `third-party`. Dùng `fileset` giúp kiểm soát phạm vi và tránh áp dụng thay thế trên toàn bộ repository.

Với `<replace>`, có thể dùng `dir`, `includes` và `excludes` để chọn nhiều tệp. Với `<replaceregexp>`, nested `fileset` thường là cách rõ ràng để chỉ định nhiều nguồn.

## 10. Xử lý theo dòng với `byline`

`<replaceregexp>` có thuộc tính `byline`. Khi bật `byline="true"`, task xử lý tệp từng dòng một thay vì đọc toàn bộ nội dung như một khối. Điều này có ích khi regex chỉ cần khớp trong từng dòng và tệp có kích thước lớn.

Ví dụ chỉ thay giá trị của khóa `debug`:

```xml
<replaceregexp file="build/config/application.properties"
               match="^debug=.*$"
               replace="debug=false"
               byline="true"/>
```

Với `byline="true"`, biểu thức không thể khớp một mẫu trải qua nhiều dòng vì mỗi dòng được xử lý riêng. Nếu cần regex có thể nhìn thấy nội dung nhiều dòng, hãy dùng chế độ xử lý toàn bộ nội dung và chọn cờ regex thích hợp.

## 11. Một buildfile hoàn chỉnh kết hợp hai task

Ví dụ dưới đây sao chép tệp mẫu vào thư mục build, thay token literal bằng `<replace>`, sau đó chuẩn hóa phiên bản bằng regex:

```xml
<project name="content-replacement" default="prepare-resources" basedir=".">

    <property name="source.file" location="src/main/resources/application.properties"/>
    <property name="output.dir" location="build/resources"/>
    <property name="output.file" location="${output.dir}/application.properties"/>

    <target name="prepare-resources">
        <mkdir dir="${output.dir}"/>
        <copy file="${source.file}" tofile="${output.file}"/>

        <replace file="${output.file}">
            <replacefilter token="@app.name@" value="Inventory Service"/>
            <replacefilter token="@service.url@" value="https://api.example.com"/>
        </replace>

        <replaceregexp file="${output.file}"
                       match="^(application\.version=)[0-9.]+$"
                       replace="\1 2.1.0"
                       flags="m"/>
    </target>

</project>
```

Trong ví dụ này, phần thay thế token được xử lý bằng literal; bước regex áp dụng cho dòng phiên bản có cấu trúc. Nếu dùng capture group để giữ nguyên phần `application.version=`, chuỗi thay thế cần khớp chính xác định dạng mong muốn. Chẳng hạn, để không thêm khoảng trắng giữa dấu `=` và giá trị, có thể dùng:

```xml
<replaceregexp file="${output.file}"
               match="^(application\.version=)[0-9.]+$"
               replace="\12.1.0"
               flags="m"/>
```

Trong trường hợp chuỗi thay thế đặt chữ số ngay sau `$1`, cú pháp nhóm có thể khó đọc vì bộ phân tích replacement có thể diễn giải tiếp chữ số như một phần số thứ tự nhóm. Có thể viết biểu thức để tránh nhập nhằng, ví dụ bắt cả phần dấu bằng và dùng một ký tự phân cách trong replacement phù hợp, hoặc thay cả dòng thành chuỗi cố định. Khi mục tiêu chỉ là một phiên bản cố định, cách rõ nhất là:

```xml
<replaceregexp file="${output.file}"
               match="^application\.version=.*$"
               replace="application.version=2.1.0"
               flags="m"/>
```

## 12. XML escaping và ký tự đặc biệt trong regex

Regex được đặt trong thuộc tính XML, vì vậy cần tuân theo cả hai bộ quy tắc: cú pháp XML và cú pháp regex Java.

| Ký tự cần biểu diễn | Trong XML attribute |
|---|---|
| `&` | `&amp;` |
| `<` | `&lt;` |
| `>` | Có thể viết trực tiếp, hoặc `&gt;` để rõ ràng |
| `"` | Dùng dấu nháy đơn bao quanh attribute hoặc `&quot;` |
| Dấu chấm literal trong regex | `\.` |
| Dấu gạch chéo ngược trong regex | Viết theo cú pháp regex Java, ví dụ `\d` |

Ví dụ tìm URL chứa dấu `&`:

```xml
<replaceregexp file="build/config/url.txt"
               match="mode=old&amp;active=true"
               replace="mode=new&amp;active=true"/>
```

XML parser chuyển `&amp;` thành ký tự `&` trước khi Ant đưa chuỗi cho regex. Không escape dấu `&` trong XML có thể khiến buildfile không được phân tích đúng.

## 13. Encoding và việc giữ nguyên tệp nguồn

Các task thay thế làm thay đổi nội dung tệp. Khi làm việc với tiếng Việt hoặc ký tự ngoài ASCII, cần đảm bảo encoding đọc và ghi phù hợp với dữ liệu. Kiểm tra thuộc tính encoding được task hỗ trợ trong phiên bản Ant đang dùng và khai báo charset khi cần.

Một quy trình build thường an toàn hơn khi:

1. Giữ tệp mẫu trong thư mục nguồn.
2. Sao chép tệp vào thư mục build.
3. Thực hiện `<replace>` hoặc `<replaceregexp>` trên bản sao.
4. Kiểm tra nội dung đầu ra trước khi đóng gói.

Không áp dụng thay thế văn bản lên tệp nhị phân như ảnh, font, JAR hoặc ZIP. Những tệp này không phải văn bản và có thể bị hỏng nếu task đọc/ghi chúng như nội dung ký tự.

## 14. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `<replace>` không thay được nội dung | Token không khớp chính xác hoặc trỏ nhầm tệp | Kiểm tra token, khoảng trắng, chữ hoa/thường và đường dẫn `file`/`dir` |
| Regex thay quá nhiều nội dung | Mẫu quá rộng hoặc bật `g` ngoài ý muốn | Thu hẹp `match`, dùng neo `^`/`$` và kiểm tra từng trường hợp |
| Regex chỉ thay kết quả đầu tiên | Chưa bật cờ `g` | Thêm `flags="g"` nếu cần thay tất cả kết quả |
| Không khớp được dấu chấm hoặc dấu ngoặc | Ký tự regex đang có ý nghĩa đặc biệt | Escape ký tự theo regex Java, ví dụ `\.` để khớp dấu chấm literal |
| Buildfile lỗi XML khi regex có `&` hoặc `<` | Chưa escape ký tự theo XML | Dùng `&amp;`, `&lt;` hoặc dấu nháy phù hợp |
| Capture group thay sai phần nội dung | Đánh số nhóm hoặc tham chiếu `\1`, `\2` sai | Đếm dấu ngoặc mở của nhóm bắt và kiểm tra chuỗi replacement |
| Regex không khớp qua nhiều dòng | Đang bật `byline` hoặc thiếu cờ/mẫu multiline phù hợp | Tắt `byline` nếu cần xử lý toàn bộ tệp và dùng cờ regex thích hợp |
| Tệp tiếng Việt bị lỗi dấu | Encoding đọc/ghi không phù hợp | Kiểm tra charset của tệp và thuộc tính encoding của task |
| Tệp ngoài dự kiến bị thay đổi | Phạm vi `dir`, `includes` hoặc `fileset` quá rộng | Giới hạn danh sách tệp và loại trừ thư mục không cần xử lý |

## 15. Checklist chọn và dùng task thay thế

- [ ] Nếu cần thay chuỗi cố định, dùng `<replace>` với `token` và `value`.
- [ ] Nếu cần mẫu linh hoạt, dùng `<replaceregexp>` với `match` và `replace`.
- [ ] Chỉ bật cờ `g` khi muốn thay mọi kết quả phù hợp.
- [ ] Dùng capture group khi cần giữ lại một phần nội dung cũ.
- [ ] Chọn `byline` theo việc regex cần xử lý từng dòng hay toàn bộ nội dung.
- [ ] Giới hạn phạm vi tệp bằng `file`, `dir`, include/exclude hoặc `fileset`.
- [ ] Escape ký tự theo cả quy tắc XML và regex Java.
- [ ] Xác định encoding phù hợp cho tệp văn bản.
- [ ] Giữ tệp mẫu nguồn nguyên vẹn nếu quy trình cần build lặp lại.
- [ ] Kiểm tra nội dung đầu ra để bảo đảm chỉ những vị trí dự kiến được thay đổi.

`<replace>` phù hợp với thay thế literal rõ ràng và dễ đọc. `<replaceregexp>` phù hợp khi nội dung cần tìm được mô tả bằng mẫu, nhóm bắt hoặc quy tắc regex. Dùng đúng task, giới hạn đúng tệp và kiểm tra đầu ra sẽ giúp bước xử lý nội dung trong Ant có thể dự đoán và bảo trì được.
