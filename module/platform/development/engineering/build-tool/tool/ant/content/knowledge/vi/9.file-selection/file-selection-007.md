# Chọn tệp theo tên, loại, kích thước và thời điểm sửa đổi

Trong Apache Ant, nhiều task cần làm việc với một nhóm tệp thay vì một tệp đơn lẻ. Ví dụ, task `<javac>` cần tìm mã nguồn Java, `<copy>` cần chọn tài nguyên để sao chép, còn `<delete>` có thể cần xóa các tệp log cũ. Nếu liệt kê từng tệp một, buildfile sẽ khó bảo trì khi dự án có thêm hoặc đổi tên tệp.

Ant cung cấp `FileSet` và các **selector** để mô tả nhóm tệp cần xử lý. Bạn có thể lọc theo tên và phần mở rộng, phân biệt tệp với thư mục, so sánh kích thước, kiểm tra thời điểm sửa đổi, rồi kết hợp nhiều điều kiện.

Sau bài học, bạn có thể:

- Dùng `fileset`, `include` và `exclude` để chọn tệp theo đường dẫn hoặc phần mở rộng.
- Dùng selector `filename` để mô tả quy tắc chọn tên chi tiết hơn.
- Chọn tệp hoặc thư mục bằng selector `type`.
- Chọn tệp theo kích thước bằng selector `size`.
- Chọn tệp theo thời điểm sửa đổi bằng selector `date`.
- Kết hợp nhiều điều kiện bằng `and`, `or` và `not`.
- Dùng cùng một FileSet trong các task như `copy`, `delete` và `jar`.

## 1. FileSet là gì?

`FileSet` là một datatype của Ant dùng để mô tả tập hợp tệp được chọn từ một thư mục gốc. Một FileSet thường có:

- `dir`: thư mục gốc để quét.
- `includes`: các mẫu tên hoặc đường dẫn được đưa vào.
- `excludes`: các mẫu tên hoặc đường dẫn bị loại ra.
- Các selector lồng bên trong để lọc sâu hơn theo thuộc tính của từng mục.

Ví dụ, chọn tất cả tệp Java trong thư mục `src`:

```xml
<fileset dir="src">
    <include name="**/*.java" />
</fileset>
```

FileSet này mô tả các tệp có phần mở rộng `.java` trong `src` và các thư mục con. Nó chưa thực hiện sao chép hoặc biên dịch; task sử dụng FileSet mới quyết định sẽ làm gì với các tệp đã chọn.

Ví dụ dùng FileSet với task `<copy>`:

```xml
<copy todir="build/classes">
    <fileset dir="src">
        <include name="**/*.properties" />
    </fileset>
</copy>
```

Task `copy` sao chép các tệp được FileSet chọn sang thư mục `build/classes`.

## 2. Chọn tệp theo tên và phần mở rộng

### 2.1. Dùng `include` và `exclude`

Ant dùng các mẫu đường dẫn để chọn hoặc loại tệp. Có thể khai báo mẫu bằng thuộc tính `includes`, `excludes`, hoặc bằng các phần tử con `<include>` và `<exclude>`.

```xml
<fileset dir="src"
         includes="**/*.java"
         excludes="**/test/**,**/generated/**" />
```

Tương đương với cách khai báo lồng:

```xml
<fileset dir="src">
    <include name="**/*.java" />
    <exclude name="**/test/**" />
    <exclude name="**/generated/**" />
</fileset>
```

Trong ví dụ, Ant chọn các tệp `.java`, sau đó loại các tệp nằm trong thư mục `test` hoặc `generated` ở bất kỳ cấp nào bên dưới thư mục gốc.

### 2.2. Ký tự đại diện trong mẫu Ant

Ant sử dụng ba dạng ký tự đại diện thường gặp:

| Mẫu | Ý nghĩa | Ví dụ |
|---|---|---|
| `*` | Khớp không hoặc nhiều ký tự trong một thành phần đường dẫn, không đi qua dấu phân cách thư mục. | `*.java` khớp `Hello.java`. |
| `?` | Khớp đúng một ký tự trong một thành phần đường dẫn. | `Test?.java` khớp `Test1.java`, `TestA.java`. |
| `**` | Khớp không hoặc nhiều cấp thư mục. | `**/*.java` khớp tệp Java ở thư mục gốc hoặc thư mục con. |

Ví dụ với thư mục:

```text
src/
├── Main.java
├── util/
│   └── StringHelper.java
└── test/
    └── MainTest.java
```

Các mẫu có kết quả như sau:

| Mẫu | Tệp khớp |
|---|---|
| `*.java` | `Main.java` ở ngay trong thư mục gốc `src`. |
| `**/*.java` | `Main.java`, `util/StringHelper.java`, `test/MainTest.java`. |
| `util/*.java` | `util/StringHelper.java`. |
| `**/test/**/*.java` | Các tệp Java trong cây thư mục `test` ở bất kỳ cấp nào. |
| `**/*Test.java` | Các tệp Java có tên kết thúc bằng `Test.java` ở mọi cấp. |

Mẫu được tính tương đối với thư mục `dir` của FileSet. Dùng dấu `/` trong mẫu đường dẫn kể cả khi build chạy trên Windows; Ant xử lý mẫu theo quy tắc đường dẫn của nó.

### 2.3. Chọn nhiều loại tệp

Có thể chọn nhiều phần mở rộng trong cùng một FileSet:

```xml
<fileset dir="resources">
    <include name="**/*.properties" />
    <include name="**/*.xml" />
    <include name="**/*.yml" />
</fileset>
```

Hoặc dùng thuộc tính `includes` với danh sách mẫu phân cách bằng dấu phẩy hoặc khoảng trắng:

```xml
<fileset dir="resources" includes="**/*.properties,**/*.xml,**/*.yml" />
```

Khi dự án có nhiều tệp, hãy giới hạn phạm vi quét bằng `dir` và các mẫu phù hợp. Điều này giúp buildfile dễ đọc và tránh đưa nhầm tài nguyên vào sản phẩm.

### 2.4. Không phân biệt chữ hoa và chữ thường

Mặc định, việc khớp mẫu của FileSet phân biệt chữ hoa và chữ thường. Có thể thay đổi bằng `casesensitive="false"`:

```xml
<fileset dir="resources" casesensitive="false">
    <include name="**/*.JPG" />
</fileset>
```

Khai báo này có thể khớp các phần mở rộng `.jpg`, `.JPG`, `.Jpg` và các cách viết hoa/thường khác. Hãy chọn quy tắc phù hợp với hệ điều hành và quy ước đặt tên của dự án; không nên phụ thuộc vào khác biệt chữ hoa/thường giữa các hệ thống tệp.

### 2.5. Mẫu loại trừ mặc định

Ant có một tập mẫu loại trừ mặc định dành cho các tệp phụ trợ thường không nên đưa vào build, chẳng hạn thư mục quản lý phiên bản hoặc tệp tạm của trình soạn thảo. FileSet bật các default excludes theo mặc định.

Có thể bật hoặc tắt rõ ràng bằng thuộc tính `defaultexcludes`:

```xml
<fileset dir="src" defaultexcludes="yes">
    <include name="**/*.java" />
</fileset>
```

Thông thường nên giữ mặc định. Chỉ dùng `defaultexcludes="no"` khi thật sự cần xử lý những tệp mà Ant thường loại trừ; hãy kiểm tra kỹ danh sách tệp được chọn trước khi dùng FileSet đó để đóng gói hoặc xóa dữ liệu.

## 3. Dùng selector `filename`

Ngoài `include` và `exclude`, Ant có selector `<filename>` để chọn theo tên hoặc đường dẫn tương đối. Selector này hữu ích khi muốn đưa quy tắc tên vào nhóm selector kết hợp với kích thước, ngày sửa đổi hoặc loại mục.

```xml
<fileset dir="src">
    <filename name="**/*Service.java" />
</fileset>
```

Selector `filename` thường có các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `name` | Mẫu tên hoặc đường dẫn cần khớp. |
| `casesensitive` | Có phân biệt chữ hoa và chữ thường hay không. |
| `negate` | Đảo kết quả khớp; `true` chọn những mục không khớp mẫu. |

Ví dụ chọn các tệp không kết thúc bằng `Test.java`:

```xml
<fileset dir="src">
    <filename name="**/*Test.java" negate="true" />
</fileset>
```

Với các quy tắc tên đơn giản, `include` và `exclude` thường ngắn gọn hơn. Selector `filename` phát huy tác dụng khi cần kết hợp quy tắc tên với các selector khác bên trong `<and>` hoặc `<or>`.

## 4. Chọn theo loại mục: file hoặc directory

Phần mở rộng thường giúp nhận diện loại nội dung, ví dụ `.java`, `.xml`, `.properties`, nhưng phần mở rộng chỉ là một phần của tên. Selector `<type>` cho phép kiểm tra mục được chọn là tệp hay thư mục.

Ví dụ chỉ chọn tệp:

```xml
<fileset dir="project">
    <type type="file" />
</fileset>
```

Ví dụ chọn thư mục:

```xml
<fileset dir="project">
    <type type="dir" />
</fileset>
```

`type` nhận các giá trị `file` hoặc `dir`. Khi mục tiêu của bạn là làm việc với các thư mục như những đơn vị riêng biệt, datatype `<dirset>` thường diễn đạt ý định rõ hơn:

```xml
<dirset dir="project">
    <include name="**/test" />
</dirset>
```

Trong thực tế, nếu đang chọn tài nguyên để sao chép hoặc đóng gói, bạn thường quan tâm đến tệp. Nếu cần chọn cây thư mục để tạo cấu trúc đầu ra hoặc xử lý thư mục, hãy xem xét `dirset` và các task hỗ trợ nó.

## 5. Chọn theo kích thước bằng selector `size`

Selector `<size>` so sánh kích thước tệp với một giá trị. Cú pháp:

```xml
<size value="giá-trị" units="đơn-vị" when="điều-kiện" />
```

Các thuộc tính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `value` | Kích thước dùng để so sánh. |
| `units` | Đơn vị kích thước; có thể dùng byte hoặc các đơn vị như `K`, `M`, `G`, `T`, `P`. |
| `when` | Phép so sánh: `less`, `more` hoặc `equal`. |

Ví dụ chọn tệp lớn hơn 1 MB:

```xml
<fileset dir="logs">
    <include name="**/*.log" />
    <size value="1" units="M" when="more" />
</fileset>
```

Ví dụ chọn tệp nhỏ hơn 100 KB:

```xml
<fileset dir="resources">
    <size value="100" units="K" when="less" />
</fileset>
```

Ví dụ chọn tệp có kích thước đúng bằng 4096 byte:

```xml
<fileset dir="data">
    <size value="4096" units="B" when="equal" />
</fileset>
```

`when="more"` và `when="less"` là so sánh lớn hơn và nhỏ hơn; chúng không có nghĩa lớn hơn hoặc bằng, nhỏ hơn hoặc bằng. Nếu cần một khoảng kích thước, hãy kết hợp hai selector bằng `<and>`:

```xml
<fileset dir="uploads">
    <and>
        <size value="100" units="K" when="more" />
        <size value="5" units="M" when="less" />
    </and>
</fileset>
```

FileSet này chọn các tệp lớn hơn 100 KB và nhỏ hơn 5 MB. Đơn vị kích thước cần được ghi rõ trong buildfile để người đọc không nhầm lẫn giữa byte, kilobyte và megabyte.

## 6. Chọn theo thời điểm sửa đổi bằng selector `date`

Mỗi tệp có thời điểm sửa đổi gần nhất (last modified time). Selector `<date>` so sánh thời điểm đó với một mốc ngày giờ được chỉ định.

Cú pháp tổng quát:

```xml
<date datetime="MM/dd/yyyy HH:mm a" when="before|after|equal" granularity="milliseconds" />
```

Các thuộc tính chính:

| Thuộc tính | Ý nghĩa |
|---|---|
| `datetime` | Mốc ngày giờ dùng để so sánh. |
| `when` | Chọn tệp có thời điểm sửa đổi trước (`before`), sau (`after`) hoặc bằng (`equal`) mốc. |
| `granularity` | Dung sai độ chính xác timestamp, tính bằng mili giây. |

Ví dụ chọn các tệp log được sửa đổi trước nửa đêm ngày 1 tháng 1 năm 2025:

```xml
<fileset dir="logs">
    <include name="**/*.log" />
    <date datetime="01/01/2025 12:00 AM" when="before" />
</fileset>
```

Ví dụ chọn các tệp được sửa đổi sau mốc thời gian đó:

```xml
<fileset dir="logs">
    <date datetime="01/01/2025 12:00 AM" when="after" />
</fileset>
```

Selector `date` xét thời điểm sửa đổi của từng mục, không đọc nội dung tệp để xác định dữ liệu bên trong có thay đổi hay không. Nó cũng không tự diễn giải yêu cầu tương đối như “trong 7 ngày gần nhất”; bạn cần cung cấp một mốc ngày giờ cụ thể. Nếu muốn mốc thay đổi theo thời điểm chạy build, hãy tạo giá trị thời gian phù hợp từ một bước hoặc công cụ cấu hình trước rồi truyền vào selector.

### 6.1. Độ chính xác của thời gian

Timestamp trên hệ thống tệp có thể có độ chính xác khác nhau tùy hệ điều hành, hệ thống tệp và cách sao chép tệp. Thuộc tính `granularity` cho phép selector xét một khoảng dung sai tính bằng mili giây khi so sánh thời điểm.

Nếu bạn đang chọn tệp quanh một mốc thời gian rất gần nhau, hãy cân nhắc độ chính xác timestamp của môi trường build. Không nên đặt `granularity` quá lớn nếu mục tiêu là phân biệt những tệp được sửa đổi cách nhau trong khoảng thời gian ngắn.

### 6.2. Ngày giờ và múi giờ

Chuỗi `datetime` được phân tích theo định dạng ngày giờ mà Ant DateSelector hỗ trợ; ví dụ trong bài dùng dạng `MM/dd/yyyy HH:mm a`. Cách diễn giải thời điểm còn phụ thuộc múi giờ và thiết lập môi trường chạy. Khi build trên nhiều máy, hãy thống nhất mốc thời gian và môi trường để tránh kết quả chọn tệp khác nhau ngoài dự kiến.

## 7. Kết hợp nhiều điều kiện chọn tệp

Khi FileSet có nhiều selector lồng trực tiếp, Ant kết hợp các selector đó theo logic AND: một mục phải thỏa mãn tất cả điều kiện để được chọn. Khi muốn biểu đạt logic khác, dùng các selector container.

### 7.1. `<and>`: tất cả điều kiện đều đúng

Ví dụ chọn tệp `.log`, có kích thước trên 1 MB và được sửa đổi trước một mốc thời gian:

```xml
<fileset dir="logs">
    <and>
        <filename name="**/*.log" />
        <type type="file" />
        <size value="1" units="M" when="more" />
        <date datetime="01/01/2025 12:00 AM" when="before" />
    </and>
</fileset>
```

Một tệp chỉ được chọn nếu đồng thời:

1. Đường dẫn kết thúc bằng `.log`.
2. Mục đó là tệp.
3. Kích thước lớn hơn 1 MB.
4. Thời điểm sửa đổi trước mốc ngày giờ đã khai báo.

### 7.2. `<or>`: ít nhất một điều kiện đúng

Ví dụ chọn tệp Java hoặc XML:

```xml
<fileset dir="src">
    <or>
        <filename name="**/*.java" />
        <filename name="**/*.xml" />
    </or>
</fileset>
```

Một tệp được chọn nếu khớp ít nhất một trong hai mẫu.

### 7.3. `<not>`: phủ định một điều kiện

Ví dụ chọn mọi tệp trong thư mục `resources`, ngoại trừ các tệp có phần mở rộng `.tmp`:

```xml
<fileset dir="resources">
    <not>
        <filename name="**/*.tmp" />
    </not>
</fileset>
```

`<not>` nhận một selector con và đảo kết quả của selector đó. Nếu cần loại trừ theo tên đơn giản, thuộc tính `excludes` thường ngắn gọn hơn; `<not>` hữu ích khi muốn ghép điều kiện phức tạp.

### 7.4. Kết hợp container lồng nhau

Có thể kết hợp AND, OR và NOT để diễn đạt điều kiện rõ ràng. Ví dụ chọn tệp Java hoặc XML, nhưng chỉ nhận tệp có kích thước dưới 2 MB:

```xml
<fileset dir="src">
    <and>
        <or>
            <filename name="**/*.java" />
            <filename name="**/*.xml" />
        </or>
        <type type="file" />
        <size value="2" units="M" when="less" />
    </and>
</fileset>
```

Có thể đọc cấu trúc này như một biểu thức:

```text
(tên là *.java HOẶC tên là *.xml)
VÀ là tệp
VÀ kích thước nhỏ hơn 2 MB
```

Khi selector lồng nhiều cấp, hãy thụt lề theo cấu trúc logic để người đọc dễ thấy nhóm điều kiện nào được kết hợp với nhau.

## 8. Kết hợp include/exclude với selector

`include` và `exclude` là cách lọc theo mẫu đường dẫn. Selector bổ sung điều kiện dựa trên thuộc tính của mục được quét. Khi dùng chung, mục được chọn cần vượt qua cả quy tắc include/exclude lẫn các selector.

Ví dụ chọn các tệp `.log` trong `logs/archive`, bỏ qua thư mục `temporary`, chỉ lấy tệp lớn hơn 500 KB và đã cũ hơn mốc ngày giờ:

```xml
<fileset dir="logs">
    <include name="archive/**/*.log" />
    <exclude name="archive/temporary/**" />
    <and>
        <type type="file" />
        <size value="500" units="K" when="more" />
        <date datetime="01/01/2025 12:00 AM" when="before" />
    </and>
</fileset>
```

Quy trình chọn có thể hiểu như sau:

1. Quét nội dung bên dưới thư mục `logs`.
2. Giữ các đường dẫn khớp `archive/**/*.log`.
3. Loại đường dẫn nằm dưới `archive/temporary/`.
4. Kiểm tra loại mục, kích thước và thời điểm sửa đổi.
5. Chỉ các mục vượt qua mọi điều kiện mới thuộc FileSet.

## 9. Dùng FileSet trong các task thực tế

FileSet chỉ mô tả tập hợp tệp. Task sử dụng nó mới quyết định thao tác. Một FileSet có thể được lồng trong nhiều task khác nhau nếu task đó hỗ trợ kiểu dữ liệu này.

### 9.1. Sao chép các tệp được chọn

```xml
<target name="copy-config">
    <copy todir="build/config">
        <fileset dir="config">
            <include name="**/*.properties" />
            <include name="**/*.xml" />
            <exclude name="**/*.local.*" />
        </fileset>
    </copy>
</target>
```

Task `<copy>` chỉ sao chép các tệp được FileSet chọn. Các đường dẫn tương đối bên dưới thư mục gốc thường được giữ lại trong thư mục đích; nếu muốn làm phẳng cấu trúc, task copy có thuộc tính `flatten` để thay đổi hành vi này.

### 9.2. Đóng gói các tệp được chọn

```xml
<target name="package-resources">
    <jar destfile="build/resources.jar">
        <fileset dir="resources">
            <include name="**/*.properties" />
            <include name="**/*.xml" />
            <exclude name="**/private/**" />
        </fileset>
    </jar>
</target>
```

Task `<jar>` tạo tệp JAR từ các tệp đã chọn. FileSet giúp chỉ đóng gói những tài nguyên cần phân phối.

### 9.3. Xóa tệp được chọn

```xml
<target name="clean-old-logs">
    <delete>
        <fileset dir="logs">
            <include name="**/*.log" />
            <date datetime="01/01/2025 12:00 AM" when="before" />
        </fileset>
    </delete>
</target>
```

Task `<delete>` xóa những tệp mà FileSet chọn. Trước khi dùng cách lọc này trong build thực tế, hãy chạy thử với một task chỉ liệt kê hoặc sao chép tệp sang thư mục kiểm tra để xác nhận tập hợp kết quả đúng với ý định. Sau khi xác nhận mới gắn FileSet vào thao tác xóa.

## 10. Khai báo FileSet dùng lại bằng `id` và `refid`

Nếu nhiều target cần cùng một nhóm tệp, có thể khai báo FileSet một lần với `id`, rồi tham chiếu bằng `refid` tại nơi sử dụng:

```xml
<project name="resource-demo" default="copy-resources">
    <fileset id="web.resources" dir="web">
        <include name="**/*.html" />
        <include name="**/*.css" />
        <include name="**/*.js" />
        <exclude name="**/*.min.js" />
    </fileset>

    <target name="copy-resources">
        <copy todir="build/web">
            <fileset refid="web.resources" />
        </copy>
    </target>
</project>
```

`id` đặt tên cho datatype FileSet. `refid` cho biết task sử dụng lại cấu hình đã khai báo. Khi quy tắc chọn tài nguyên thay đổi, bạn chỉ cần cập nhật một nơi.

## 11. Lựa chọn selector phù hợp

| Nhu cầu | Cách dùng nên xem xét | Ví dụ |
|---|---|---|
| Chọn theo phần mở rộng hoặc đường dẫn | `include` / `exclude` | `**/*.java`, `**/generated/**` |
| Chọn theo mẫu tên trong một nhóm điều kiện | `<filename>` | `<filename name="**/*Test.java" />` |
| Chỉ nhận tệp hoặc thư mục | `<type>` | `<type type="file" />` |
| Chọn lớn hơn, nhỏ hơn hoặc bằng một kích thước | `<size>` | `<size value="1" units="M" when="more" />` |
| Chọn trước hoặc sau một mốc sửa đổi | `<date>` | `<date datetime="01/01/2025 12:00 AM" when="before" />` |
| Tất cả điều kiện phải đúng | `<and>` | Tên `.log` VÀ lớn hơn 1 MB |
| Một trong các điều kiện đúng | `<or>` | Tên `.java` HOẶC `.xml` |
| Đảo một điều kiện | `<not>` | Không phải tệp `.tmp` |

Không cần dùng selector phức tạp nếu `include` và `exclude` đã diễn đạt đủ yêu cầu. Hãy bắt đầu bằng mẫu tên và chỉ bổ sung selector khi cần lọc theo thuộc tính khác hoặc kết hợp logic.

## 12. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| FileSet không chọn được tệp nào | `dir` sai, mẫu đường dẫn không khớp hoặc nhầm `*` với `**`. | Kiểm tra thư mục gốc, đường dẫn tương đối và mẫu khớp. |
| Bỏ sót tệp có chữ hoa trong phần mở rộng | Mẫu mặc định phân biệt chữ hoa và chữ thường. | Dùng quy tắc tên thống nhất hoặc `casesensitive="false"`. |
| Tệp nằm trong thư mục con không được chọn | Mẫu chỉ khớp cấp hiện tại. | Dùng `**/` khi cần tìm ở nhiều cấp thư mục. |
| Tệp cũ không được chọn như mong đợi | Mốc `datetime`, múi giờ hoặc độ chính xác timestamp chưa phù hợp. | Kiểm tra định dạng ngày giờ, `when` và `granularity`. |
| Tệp có kích thước sát ngưỡng bị chọn sai | Dùng nhầm đơn vị hoặc nhầm `more`/`less` với phép so sánh bao gồm bằng. | Ghi rõ `units`, kiểm tra toán tử so sánh và thử với vài tệp có kích thước đã biết. |
| Tệp tạm vẫn xuất hiện trong kết quả | Chưa có quy tắc `exclude`, hoặc default excludes đã bị tắt. | Bổ sung `exclude` và kiểm tra `defaultexcludes`. |
| Kết quả khác nhau giữa các máy | Hệ thống tệp, chữ hoa/thường, timestamp hoặc múi giờ khác nhau. | Chuẩn hóa quy tắc tên, mốc thời gian và cấu hình môi trường build. |
| Task không xử lý thư mục như mong đợi | Đang dùng `fileset` cho mục tiêu cần thao tác với thư mục. | Xem xét `dirset` và khả năng hỗ trợ của task. |

## 13. Bài thực hành

Tạo cấu trúc thư mục sau:

```text
ant-files/
├── build.xml
├── resources/
│   ├── app.properties
│   ├── readme.txt
│   ├── old.log
│   ├── image.PNG
│   └── config/
│       ├── app.xml
│       └── local.properties
└── logs/
    ├── app.log
    └── archive/
        └── previous.log
```

Giả sử bạn cần tạo một bản sao tài nguyên vào `build/resources` theo các yêu cầu:

1. Chỉ chọn các tệp `.properties` và `.xml`.
2. Không chọn tệp nằm trong thư mục `config`.
3. Chỉ chọn tệp có kích thước nhỏ hơn 1 MB.
4. Chỉ chọn tệp có thời điểm sửa đổi sau một mốc ngày giờ đã cho.

Hãy viết target `copy-selected` dùng `<copy>` và `<fileset>`. Gợi ý cấu trúc:

```xml
<target name="copy-selected">
    <copy todir="build/resources">
        <fileset dir="resources">
            <include name="**/*.properties" />
            <include name="**/*.xml" />
            <exclude name="config/**" />
            <and>
                <type type="file" />
                <size value="1" units="M" when="less" />
                <date datetime="01/01/2025 12:00 AM" when="after" />
            </and>
        </fileset>
    </copy>
</target>
```

Tiếp tục thực hành:

- Đổi điều kiện ngày sửa đổi từ `after` thành `before` và quan sát nhóm tệp được chọn.
- Đổi `casesensitive` thành `false` để thử khớp phần mở rộng không đồng nhất chữ hoa/thường.
- Dùng `<or>` để chọn `.xml` hoặc `.txt`.
- Thêm `<not>` để loại các tệp có tên chứa hậu tố `local` bằng một selector tên phù hợp.
- Thay `<copy>` bằng một task chỉ hiển thị hoặc kiểm tra danh sách trong môi trường thử nghiệm trước khi áp dụng thao tác có tác động lên tệp.

### Câu hỏi tự kiểm tra

1. `fileset` và task `<copy>` có vai trò khác nhau như thế nào?
2. Khác biệt giữa `*` và `**` trong mẫu đường dẫn Ant là gì?
3. Khi nào nên dùng `<type type="file" />`?
4. `when="more"` của selector `size` có bao gồm trường hợp kích thước bằng giá trị `value` không?
5. Selector `date` so sánh thuộc tính nào của tệp?
6. Nếu có nhiều selector lồng trực tiếp trong FileSet, các điều kiện được kết hợp như thế nào?
7. Khi nào cần dùng `<or>` hoặc `<not>` thay vì chỉ dùng `include` và `exclude`?

### Đáp án gợi ý

- `fileset` mô tả tập hợp tệp; task `<copy>` thực hiện sao chép tập hợp đó.
- `*` khớp trong một thành phần đường dẫn; `**` có thể đi qua nhiều cấp thư mục.
- `<type type="file" />` giới hạn kết quả ở các tệp, hữu ích khi cấu trúc quét có thể chứa cả mục thư mục.
- `more` là lớn hơn nghiêm ngặt, không bao gồm bằng.
- `date` so sánh thời điểm sửa đổi gần nhất của mục với mốc `datetime`.
- Các selector lồng trực tiếp được kết hợp theo AND; dùng container khi cần logic khác.
- `<or>` biểu diễn một trong nhiều điều kiện đúng; `<not>` đảo kết quả của một selector.

## Kết luận

FileSet giúp mô tả nhóm tệp để task Ant xử lý. `include`, `exclude` và selector `filename` chọn theo tên hoặc đường dẫn; `type` phân biệt tệp và thư mục; `size` lọc theo kích thước; `date` so sánh thời điểm sửa đổi. Khi cần nhiều điều kiện, hãy kết hợp selector bằng `and`, `or` và `not`. Việc giới hạn đúng thư mục gốc và kiểm tra tập hợp tệp trước khi sao chép, đóng gói hoặc xóa sẽ giúp buildfile an toàn và dễ bảo trì.
