# Tài nguyên tệp, chuỗi, URL và phần tử trong kho nén

Trong Apache Ant, nhiều task có thể làm việc với dữ liệu đầu vào theo một cách thống nhất, dù dữ liệu đó đến từ tệp trên đĩa, một chuỗi trong buildfile, một địa chỉ URL hay một mục nằm bên trong tệp ZIP. Ant gọi những đầu vào như vậy là **resource** (tài nguyên).

Resource giúp buildfile mô tả dữ liệu cần xử lý mà không phải gắn mọi thao tác với một đường dẫn tệp thông thường. Ví dụ, task có thể đọc nội dung từ một `FileResource`, ghép thêm một `StringResource`, lấy dữ liệu từ `URLResource` hoặc đọc một mục cụ thể trong kho ZIP. Khi có nhiều resource, ta có thể nhóm chúng trong một resource collection rồi truyền collection đó cho task hỗ trợ.

Sau bài học, bạn có thể:

- Hiểu resource và resource collection trong Ant.
- Khai báo tài nguyên tệp bằng `file`.
- Tạo tài nguyên từ chuỗi bằng `string`.
- Trỏ đến tài nguyên qua URL bằng `url`.
- Tham chiếu một mục bên trong kho ZIP bằng `zipentry` hoặc chọn nhiều mục bằng `zipfileset`.
- Kết hợp nhiều loại tài nguyên trong một collection.
- Dùng resource trong các task như `copy`, `concat` và `loadresource`.

## 1. Resource là gì?

Resource là một đối tượng đại diện cho một nguồn dữ liệu. Tùy loại resource, dữ liệu có thể nằm trong tệp cục bộ, được tạo từ một chuỗi, được truy cập qua URL hoặc được lưu trong một kho nén.

Một resource thường cung cấp một số thông tin và khả năng chung:

- **Tên:** tên hoặc định danh giúp nhận biết tài nguyên.
- **Tồn tại:** resource có thể cho biết nguồn dữ liệu có sẵn hay không.
- **Kích thước:** nếu xác định được, resource có thể cung cấp độ dài dữ liệu.
- **Thời điểm sửa đổi:** một số loại resource có metadata thời gian.
- **Nội dung:** task có thể mở luồng dữ liệu để đọc nội dung resource.

Không phải loại resource nào cũng cung cấp đầy đủ metadata. Ví dụ, một chuỗi được tạo trong bộ nhớ không có thời điểm sửa đổi của tệp; URL từ máy chủ có thể không cung cấp kích thước trước khi tải nội dung.

### Resource và ResourceCollection

Hai khái niệm có liên quan nhưng khác nhau:

| Khái niệm | Vai trò | Ví dụ |
|---|---|---|
| Resource | Đại diện cho một nguồn dữ liệu đơn lẻ. | Một tệp `config.properties`, một URL hoặc một mục trong ZIP. |
| ResourceCollection | Đại diện cho một nhóm resource để task xử lý. | `fileset`, `path`, `resources`, `union`, `zipfileset`. |

Một resource có thể được xem như một collection chỉ chứa một phần tử. Ngược lại, một collection có thể chứa nhiều resource thuộc các loại khác nhau nếu kiểu collection và task sử dụng hỗ trợ chúng.

Sơ đồ khái quát:

```text
Resource
  +-- FileResource
  +-- StringResource
  +-- URLResource
  +-- ZipEntryResource

ResourceCollection
  +-- FileSet
  +-- Path
  +-- Resources
  +-- Union
  +-- ZipFileSet
```

Resource mô tả dữ liệu; task như `copy`, `concat` hoặc `loadresource` quyết định đọc, sao chép hay ghép dữ liệu đó như thế nào.

## 2. Tài nguyên tệp: `file`

File resource đại diện cho một tệp trên hệ thống tệp. Đây là loại resource quen thuộc nhất khi làm việc với Ant.

Ví dụ khai báo một tệp:

```xml
<file file="src/config/app.properties" />
```

Có thể dùng resource này làm đầu vào cho task `copy`:

```xml
<target name="copy-config">
    <copy tofile="build/app.properties">
        <file file="src/config/app.properties" />
    </copy>
</target>
```

Task `copy` đọc nội dung từ resource tệp và ghi ra tệp đích `build/app.properties`.

### 2.1. Đường dẫn tương đối và tuyệt đối

Đường dẫn tương đối được phân giải dựa trên thư mục cơ sở của project hoặc ngữ cảnh mà resource sử dụng. Có thể khai báo `basedir` trong `<project>`:

```xml
<project name="file-resource-demo" default="show" basedir=".">
    <target name="show">
        <echo message="Project base: ${basedir}" />
        <copy tofile="build/readme.txt">
            <file file="docs/readme.txt" />
        </copy>
    </target>
</project>
```

Khi build được gọi từ thư mục dự án, `docs/readme.txt` được hiểu tương đối với thư mục cơ sở của project. Đường dẫn tuyệt đối cũng có thể được dùng khi cần tham chiếu một vị trí ngoài dự án, nhưng buildfile thường dễ di chuyển hơn nếu ưu tiên đường dẫn tương đối.

Một số resource type hỗ trợ chỉ định tên tệp kết hợp với `basedir`. Ví dụ dạng khai báo:

```xml
<file name="app.properties" basedir="src/config" />
```

Điều này giúp tách thư mục gốc và tên tệp, thuận tiện khi các giá trị đến từ property.

### 2.2. Dùng FileSet khi cần nhiều tệp

`file` phù hợp khi bạn muốn chỉ rõ một tệp. Nếu cần chọn nhiều tệp theo mẫu, hãy dùng `fileset`:

```xml
<fileset dir="src">
    <include name="**/*.properties" />
    <exclude name="**/local/**" />
</fileset>
```

Ví dụ sao chép cả nhóm tài nguyên:

```xml
<copy todir="build/config">
    <fileset dir="src">
        <include name="**/*.properties" />
        <exclude name="**/local/**" />
    </fileset>
</copy>
```

FileSet là một resource collection, không phải một resource đơn lẻ. Chọn `file` khi nguồn là một tệp cụ thể; chọn `fileset` khi nguồn là một tập hợp tệp được lọc theo tên hoặc selector.

## 3. Tài nguyên chuỗi: `string`

String resource đại diện cho nội dung văn bản được khai báo trực tiếp trong buildfile. Nó hữu ích khi dữ liệu ngắn, được tạo bởi build hoặc cần ghép với nội dung từ nguồn khác.

Ví dụ:

```xml
<string value="Hello from Apache Ant" />
```

Có thể ghi nội dung chuỗi ra tệp bằng task `copy`:

```xml
<target name="write-message">
    <copy tofile="build/message.txt">
        <string value="Hello from Apache Ant" />
    </copy>
</target>
```

Resource chuỗi không cần tệp nguồn tồn tại trên đĩa. Nội dung của nó được tạo từ giá trị thuộc tính `value`.

### 3.1. Chú ý mã hóa ký tự

Khi resource chuỗi được chuyển thành byte để task ghi ra tệp hoặc truyền cho một API, mã hóa ký tự có thể ảnh hưởng đến kết quả. Nếu cần nội dung Unicode nhất quán, hãy chỉ định encoding mà resource hoặc task hỗ trợ và cấu hình encoding của task ghi.

Ví dụ dùng `concat` để tạo một tệp văn bản UTF-8:

```xml
<concat destfile="build/info.txt" encoding="UTF-8">
    <string value="Thông tin được tạo bởi Ant." />
</concat>
```

Encoding là cách chuyển ký tự thành byte. Nếu tệp được đọc bởi ứng dụng kỳ vọng UTF-8, hãy bảo đảm bước ghi tạo ra đúng mã hóa đó.

### 3.2. Chuỗi có ký tự đặc biệt trong XML

String resource thường được khai báo bên trong thuộc tính XML `value`. Vì vậy, nội dung phải tuân theo quy tắc XML. Ví dụ, dấu `&` trong giá trị thuộc tính cần viết thành `&amp;`:

```xml
<string value="Tom &amp; Jerry" />
```

Nếu chuỗi chứa dấu nháy kép, có thể dùng dấu nháy đơn bao quanh thuộc tính hoặc escape dấu nháy theo cú pháp XML phù hợp. Đây là quy tắc của XML, không phải quy tắc riêng của resource string.

## 4. Tài nguyên URL: `url`

URL resource đại diện cho dữ liệu có thể truy cập qua một địa chỉ URL. Nguồn có thể là một tài nguyên web hoặc một giao thức mà Java hỗ trợ.

Ví dụ:

```xml
<url url="https://example.com/config/app.properties" />
```

Có thể dùng URL resource làm nguồn cho task `copy`:

```xml
<target name="download-config">
    <copy tofile="build/app.properties">
        <url url="https://example.com/config/app.properties" />
    </copy>
</target>
```

Khi target chạy, task truy cập URL và đọc dữ liệu từ nguồn để ghi vào tệp đích.

### 4.1. URL và đường dẫn tệp không giống nhau

URL mô tả cách truy cập tài nguyên thông qua một giao thức. Đường dẫn tệp mô tả vị trí trong hệ thống tệp cục bộ.

| Nguồn | Cách biểu diễn | Resource phù hợp |
|---|---|---|
| Tệp trong dự án | `src/config/app.properties` | `file` |
| Nội dung văn bản được tạo trong buildfile | `Build completed` | `string` |
| Tài nguyên trên máy chủ web | `https://example.com/config/app.properties` | `url` |
| Tệp bên trong kho ZIP | `config/app.properties` trong `app.zip` | `zipentry` hoặc `zipfileset` |

Không nên đưa một URL HTTP vào thuộc tính `file` với kỳ vọng Ant sẽ tự tải dữ liệu. Hãy dùng resource type phù hợp với nguồn.

### 4.2. Mạng và khả năng truy cập

URL resource phụ thuộc vào kết nối mạng, DNS, máy chủ, quyền truy cập và giao thức được hỗ trợ. Nếu URL không truy cập được, task sử dụng resource có thể thất bại.

Khi dùng URL trong build:

- Ưu tiên URL ổn định và phiên bản tài nguyên có thể xác định.
- Không giả định máy build luôn có Internet.
- Xử lý trường hợp máy chủ trả lỗi hoặc tài nguyên không tồn tại.
- Tránh ghi thông tin bí mật trực tiếp vào URL hoặc buildfile.
- Với build cần tái lập, cân nhắc tải và lưu dependency vào kho nội bộ hoặc cache đã kiểm soát.

URL resource mô tả nguồn dữ liệu; nó không tự bảo đảm dữ liệu tải về là bất biến. Nội dung tại cùng một URL có thể thay đổi theo thời gian.

## 5. Tài nguyên phần tử trong kho ZIP: `zipentry`

Một kho ZIP có thể chứa nhiều mục (entry). Mỗi mục có tên đường dẫn bên trong kho và nội dung riêng. Zip entry resource đại diện cho một mục cụ thể trong kho ZIP.

Ví dụ, giả sử có tệp `dist/app.zip` với cấu trúc:

```text
app.zip
├── config/
│   └── app.properties
├── docs/
│   └── readme.txt
└── lib/
    └── helper.jar
```

Muốn tham chiếu riêng mục `config/app.properties`, có thể khai báo:

```xml
<zipentry zipfile="dist/app.zip" name="config/app.properties" />
```

Đưa mục đó ra tệp bên ngoài kho ZIP:

```xml
<target name="extract-config">
    <copy tofile="build/app.properties">
        <zipentry zipfile="dist/app.zip" name="config/app.properties" />
    </copy>
</target>
```

Task `copy` đọc nội dung entry đã chọn và ghi ra `build/app.properties`. Thuộc tính `name` là đường dẫn của mục bên trong kho nén, không phải đường dẫn tệp trên hệ thống tệp.

### 5.1. Chọn nhiều mục bằng `zipfileset`

Nếu cần chọn nhiều entry trong kho ZIP, dùng `zipfileset`. Đây là resource collection chuyên dùng cho các mục trong kho ZIP:

```xml
<zipfileset src="dist/app.zip">
    <include name="config/**" />
    <include name="docs/**" />
    <exclude name="docs/draft/**" />
</zipfileset>
```

Ví dụ giải nén hoặc sao chép các mục được chọn:

```xml
<target name="extract-resources">
    <copy todir="build/extracted">
        <zipfileset src="dist/app.zip">
            <include name="config/**" />
            <include name="docs/**" />
            <exclude name="docs/draft/**" />
        </zipfileset>
    </copy>
</target>
```

`zipfileset` chọn một tập hợp entry từ kho ZIP, tương tự cách `fileset` chọn tệp từ thư mục trên đĩa. `src` chỉ định kho nén nguồn; `include` và `exclude` lọc theo tên entry bên trong kho.

### 5.2. Đường dẫn bên trong kho nén

Tên entry thường dùng dấu `/` để phân tách thư mục, ví dụ `config/app.properties`. Đây là đường dẫn logic bên trong kho ZIP, không phải đường dẫn tuyệt đối của hệ điều hành.

Một số thuộc tính của `zipfileset` có thể thay đổi cách entry được đặt ở đích, ví dụ:

- `prefix`: thêm một tiền tố thư mục vào đường dẫn entry khi ghi vào kho hoặc xử lý collection theo cách task hỗ trợ.
- `fullpath`: chỉ định một đường dẫn đích duy nhất cho nội dung của FileSet/ZipFileSet trong những ngữ cảnh được hỗ trợ.
- `includes` và `excludes`: chọn hoặc loại entry theo mẫu.

Ví dụ trong task tạo ZIP:

```xml
<zip destfile="build/distribution.zip">
    <zipfileset src="dist/app.zip" includes="config/**" prefix="application" />
</zip>
```

Các entry được chọn từ kho nguồn sẽ được đặt dưới tiền tố `application` trong kho đích. Cần phân biệt việc chọn entry nguồn với cách đặt tên entry trong kho đích; thuộc tính `prefix` ảnh hưởng đến đường dẫn đầu ra.

### 5.3. Archive resource tổng quát

Ant còn có các resource type cho những định dạng kho lưu trữ khác, tùy phiên bản và task được dùng, chẳng hạn TAR hoặc các dạng nén. Với ZIP, hai trường hợp thường gặp là:

- `zipentry`: tham chiếu một entry cụ thể.
- `zipfileset`: chọn nhiều entry theo mẫu.

Hãy dùng `zipentry` khi biết chính xác tên một mục cần đọc; dùng `zipfileset` khi muốn chọn nhiều mục theo thư mục, phần mở rộng hoặc mẫu đường dẫn.

## 6. Nhóm nhiều resource trong `<resources>`

Phần tử `<resources>` là một container cho phép khai báo nhiều resource hoặc resource collection con. Nó hữu ích khi task cần xử lý một chuỗi đầu vào gồm nhiều loại nguồn.

Ví dụ kết hợp tệp, chuỗi và một entry trong ZIP:

```xml
<resources id="report.inputs">
    <file file="docs/header.txt" />
    <string value="Build report" />
    <zipentry zipfile="dist/app.zip" name="docs/readme.txt" />
</resources>
```

Collection này mô tả ba nguồn dữ liệu. Có thể truyền collection vào task hỗ trợ ResourceCollection, ví dụ `concat`:

```xml
<concat destfile="build/report.txt" encoding="UTF-8">
    <resources refid="report.inputs" />
</concat>
```

Task `concat` ghép nội dung các resource theo thứ tự collection cung cấp và ghi vào `build/report.txt`. Với task ghép nội dung, thứ tự resource có ý nghĩa vì nó ảnh hưởng thứ tự các đoạn văn bản trong tệp đầu ra.

### 6.1. Tham chiếu collection bằng `id` và `refid`

Nếu nhiều target cần cùng một nhóm resource, có thể đặt `id` cho collection rồi tham chiếu bằng `refid`:

```xml
<resources id="common.inputs">
    <file file="docs/intro.txt" />
    <file file="docs/usage.txt" />
</resources>

<target name="build-guide">
    <concat destfile="build/guide.txt">
        <resources refid="common.inputs" />
    </concat>
</target>
```

`id` định danh collection; `refid` sử dụng lại collection đó. Cách này giúp các target dùng chung một cấu hình đầu vào mà không phải khai báo lặp lại các resource.

### 6.2. Resource collection lồng nhau

Một collection có thể chứa collection khác nếu cấu trúc datatype hỗ trợ. Ví dụ:

```xml
<resources id="all.inputs">
    <file file="README.txt" />
    <fileset dir="docs">
        <include name="**/*.txt" />
    </fileset>
</resources>
```

Collection này chứa một resource tệp cụ thể và một FileSet nhiều tệp. Task nhận collection sẽ xử lý các phần tử theo khả năng hỗ trợ của nó.

## 7. Dùng resource trong các task thường gặp

Không phải task nào cũng nhận mọi loại resource. Cần xem kiểu dữ liệu mà task hỗ trợ và cách task diễn giải resource. Một số task thường dùng resource collection làm đầu vào.

### 7.1. `copy`: sao chép resource ra tệp hoặc thư mục

Ví dụ sao chép một file resource:

```xml
<copy tofile="build/readme.txt">
    <file file="README.txt" />
</copy>
```

Ví dụ sao chép dữ liệu từ URL:

```xml
<copy tofile="build/remote-config.properties">
    <url url="https://example.com/config/app.properties" />
</copy>
```

Ví dụ sao chép một entry từ ZIP:

```xml
<copy tofile="build/app.properties">
    <zipentry zipfile="dist/app.zip" name="config/app.properties" />
</copy>
```

Task `copy` cần xác định đích thông qua `tofile` cho một tệp đích hoặc `todir` cho thư mục đích. Với collection nhiều resource, dùng `todir` và bảo đảm task có thể xác định đường dẫn đích cho từng resource.

### 7.2. `concat`: ghép nội dung nhiều resource

`concat` phù hợp khi cần ghép nội dung văn bản từ nhiều nguồn:

```xml
<concat destfile="build/all-notes.txt" encoding="UTF-8">
    <resources>
        <file file="docs/part-1.txt" />
        <string value="--- End of part 1 ---" />
        <file file="docs/part-2.txt" />
    </resources>
</concat>
```

Kết quả là nội dung các resource được nối theo thứ tự khai báo. Có thể cấu hình separator hoặc cách xử lý dòng mới tùy yêu cầu của task `concat`.

### 7.3. `loadresource`: đọc resource vào property

Nếu cần nạp nội dung một resource thành property, dùng task `<loadresource>`:

```xml
<loadresource property="app.banner" encoding="UTF-8">
    <file file="config/banner.txt" />
</loadresource>

<echo message="${app.banner}" />
```

Task đọc nội dung resource và đặt vào property `app.banner`. Đây là cách tiện lợi với nội dung văn bản nhỏ cần sử dụng trong các task tiếp theo.

Không nên nạp tệp nhị phân lớn vào property. Property được thiết kế để giữ giá trị dạng chuỗi; với tệp nhị phân hoặc dữ liệu lớn, hãy dùng task xử lý resource trực tiếp như `copy` hoặc task phù hợp khác.

## 8. So sánh các loại resource

| Loại | Đại diện cho | Cách khai báo minh họa | Khi nên dùng |
|---|---|---|---|
| `file` | Một tệp trên hệ thống tệp. | `<file file="src/app.txt" />` | Đọc hoặc sao chép một tệp đã biết. |
| `string` | Nội dung văn bản được khai báo trong buildfile. | `<string value="Hello" />` | Tạo đoạn văn bản nhỏ hoặc ghép nội dung. |
| `url` | Dữ liệu truy cập qua URL. | `<url url="https://example.com/data.txt" />` | Lấy tài nguyên từ máy chủ hoặc nguồn URL. |
| `zipentry` | Một mục cụ thể trong kho ZIP. | `<zipentry zipfile="app.zip" name="config/app.properties" />` | Đọc một entry đã biết tên. |
| `fileset` | Tập hợp tệp trên hệ thống tệp. | `<fileset dir="src"><include name="**/*.java" /></fileset>` | Chọn nhiều tệp theo mẫu. |
| `zipfileset` | Tập hợp entry trong kho ZIP. | `<zipfileset src="app.zip" includes="config/**" />` | Chọn nhiều entry trong archive. |
| `resources` | Collection chứa nhiều resource hoặc collection con. | `<resources><file .../><string .../></resources>` | Gom nhiều nguồn đầu vào. |

Chọn loại resource theo vị trí và số lượng nguồn dữ liệu, sau đó chọn task theo thao tác cần thực hiện.

## 9. Xử lý lỗi và các giới hạn cần biết

Resource có thể không truy cập được hoặc không cung cấp metadata như mong đợi. Một số lỗi phổ biến:

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy file resource | Đường dẫn sai hoặc thư mục cơ sở không như dự kiến. | Kiểm tra `basedir`, đường dẫn tương đối và sự tồn tại của tệp. |
| Không đọc được URL | Mất kết nối, DNS lỗi, máy chủ không phản hồi hoặc quyền truy cập bị từ chối. | Kiểm tra URL và khả năng truy cập từ máy chạy Ant. |
| Không tìm thấy ZIP entry | Tên entry sai hoặc khác chữ hoa/thường so với tên trong archive. | Liệt kê nội dung ZIP và kiểm tra chính xác đường dẫn entry. |
| Nội dung văn bản bị lỗi dấu | Encoding khi đọc hoặc ghi không khớp. | Chỉ định UTF-8 hoặc encoding đúng ở task/resource hỗ trợ. |
| Task không chấp nhận resource | Task chỉ hỗ trợ một số ResourceCollection hoặc cách lồng nhất định. | Kiểm tra tài liệu task và dùng đúng phần tử con được hỗ trợ. |
| Kết quả collection thiếu mục | Mẫu include/exclude hoặc đường dẫn trong archive không khớp. | Kiểm tra mẫu và thư mục gốc của collection. |
| Nội dung URL thay đổi giữa các lần build | Máy chủ thay đổi nội dung tại cùng địa chỉ. | Dùng phiên bản cố định hoặc lưu bản phụ thuộc có kiểm soát. |

Khi build cần tái lập, hãy hạn chế phụ thuộc vào nguồn bên ngoài thay đổi liên tục. Nếu bắt buộc lấy dữ liệu qua URL, hãy cân nhắc kiểm tra phiên bản hoặc checksum của nội dung sau khi tải.

## 10. Ví dụ tổng hợp

Ví dụ sau kết hợp nhiều nguồn: một tệp giới thiệu, một chuỗi được tạo trong buildfile, một URL cấu hình và một entry trong kho ZIP. Sau đó task `concat` ghép chúng thành một báo cáo.

```xml
<project name="resource-demo" default="create-report" basedir=".">
    <property name="build.dir" location="build" />

    <resources id="report.sources">
        <file file="docs/intro.txt" />
        <string value="--- Build generated content ---" />
        <url url="https://example.com/status.txt" />
        <zipentry zipfile="dist/app.zip" name="docs/readme.txt" />
    </resources>

    <target name="create-report">
        <mkdir dir="${build.dir}" />
        <concat destfile="${build.dir}/report.txt" encoding="UTF-8">
            <resources refid="report.sources" />
        </concat>
    </target>
</project>
```

Luồng xử lý:

```text
FileResource --------+
StringResource ------+
URLResource ---------+--> resources collection --> concat --> report.txt
ZipEntryResource ----+
```

Trong ví dụ:

- `file` đọc nội dung `docs/intro.txt`.
- `string` cung cấp đoạn văn bản được khai báo trực tiếp.
- `url` đọc nội dung từ địa chỉ web.
- `zipentry` đọc một entry trong `dist/app.zip`.
- `resources` gom bốn nguồn vào collection có định danh `report.sources`.
- `concat` đọc collection và nối nội dung vào tệp báo cáo.

Để chạy thành công, các tệp cục bộ và kho ZIP phải tồn tại, entry phải có tên đúng, URL phải truy cập được và môi trường phải hỗ trợ các giao thức cần thiết. Ví dụ này minh họa cách phối hợp resource; trong dự án thực tế, có thể thay URL bằng một nguồn nội bộ hoặc một tệp đã tải xuống để build ổn định hơn.

## 11. Bài thực hành

Tạo dự án:

```text
resource-lab/
├── build.xml
├── docs/
│   ├── intro.txt
│   └── usage.txt
├── config/
│   └── app.properties
└── dist/
    └── app.zip
```

Thực hiện các yêu cầu:

1. Dùng `file` để sao chép `docs/intro.txt` vào thư mục `build`.
2. Dùng `string` để tạo tệp `build/message.txt` chứa thông báo do bạn tự viết.
3. Dùng `url` để lấy một tệp văn bản từ một URL có thể truy cập và lưu vào `build/remote.txt`.
4. Dùng `zipentry` để trích xuất riêng `config/app.properties` từ `dist/app.zip` ra `build/app.properties`.
5. Dùng `zipfileset` để chọn toàn bộ các tệp dưới thư mục `docs` trong archive và sao chép chúng ra thư mục riêng.
6. Khai báo một collection `resources` có `id`, gồm `file`, `string` và `zipentry`, rồi dùng `concat` để ghép chúng thành một báo cáo.

Ví dụ khung buildfile:

```xml
<project name="resource-lab" default="prepare" basedir=".">
    <property name="build.dir" location="build" />

    <resources id="lab.inputs">
        <file file="docs/intro.txt" />
        <string value="Generated by Ant" />
        <zipentry zipfile="dist/app.zip" name="config/app.properties" />
    </resources>

    <target name="prepare">
        <mkdir dir="${build.dir}" />
        <copy tofile="${build.dir}/intro.txt">
            <file file="docs/intro.txt" />
        </copy>
        <copy tofile="${build.dir}/app.properties">
            <zipentry zipfile="dist/app.zip" name="config/app.properties" />
        </copy>
        <concat destfile="${build.dir}/combined.txt" encoding="UTF-8">
            <resources refid="lab.inputs" />
        </concat>
    </target>
</project>
```

Hãy chạy `ant prepare`, kiểm tra các tệp trong `build`, rồi thay đổi thứ tự resource trong `lab.inputs` để quan sát thứ tự nội dung trong `combined.txt`.

### Câu hỏi tự kiểm tra

1. Resource khác ResourceCollection ở điểm nào?
2. Khi chỉ cần đọc một tệp đã biết đường dẫn, nên dùng `file` hay `fileset`?
3. `string` phù hợp với loại nội dung nào? Vì sao không nên dùng nó để nạp một tệp nhị phân lớn?
4. URL resource khác file resource như thế nào?
5. `zipentry` và `zipfileset` khác nhau ở số lượng và cách chọn entry ra sao?
6. Vì sao một URL resource có thể khiến build không tái lập giữa các lần chạy?
7. `id` và `refid` giúp tái sử dụng resource collection như thế nào?
8. Task `concat` xử lý nhiều resource theo thứ tự nào?

### Đáp án gợi ý

- Resource đại diện cho một nguồn dữ liệu; ResourceCollection đại diện cho một nhóm resource.
- `file` phù hợp với một tệp cụ thể; `fileset` phù hợp với nhiều tệp được chọn theo mẫu.
- `string` đại diện cho văn bản ngắn được tạo trong buildfile; dữ liệu nhị phân lớn nên được xử lý như tệp hoặc resource phù hợp.
- `url` truy cập nguồn qua giao thức URL; `file` đọc tệp trên hệ thống tệp cục bộ.
- `zipentry` tham chiếu một entry cụ thể; `zipfileset` chọn nhiều entry bằng mẫu.
- Nội dung tại cùng một URL có thể thay đổi theo thời gian hoặc máy chủ có thể không truy cập được.
- `id` định danh collection; `refid` tham chiếu collection đó tại nơi sử dụng.
- `concat` ghép nội dung theo thứ tự resource được cung cấp trong collection.

## Kết luận

Resource giúp Ant mô tả nguồn dữ liệu độc lập với thao tác xử lý. `file` đại diện cho tệp cục bộ, `string` cung cấp văn bản trong buildfile, `url` trỏ đến nguồn có thể truy cập qua URL, còn `zipentry` tham chiếu một mục trong kho ZIP. Khi cần nhiều nguồn, hãy nhóm chúng trong ResourceCollection như `resources` hoặc dùng `fileset` và `zipfileset` để chọn nhiều mục. Sau đó truyền resource hoặc collection cho task phù hợp như `copy`, `concat` hay `loadresource`.
