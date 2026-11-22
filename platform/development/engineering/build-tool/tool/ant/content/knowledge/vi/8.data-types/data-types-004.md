# FileList và tập tệp có danh sách, thứ tự tường minh

Trong một quy trình build, có lúc ta cần lấy tất cả file Java trong một thư mục theo mẫu `**/*.java`. Nhưng cũng có lúc ta chỉ muốn xử lý một danh sách file đã biết trước, theo đúng thứ tự do người viết buildfile chỉ định. Hai nhu cầu này khác nhau: trường hợp đầu phù hợp với `FileSet`, còn trường hợp thứ hai là mục đích chính của **FileList** trong Apache Ant.

`FileList` là một kiểu dữ liệu của Ant dùng để biểu diễn danh sách file được nêu tên tường minh. Danh sách này gắn với một thư mục cơ sở, giữ thứ tự các tên file đã khai báo và có thể chứa những file hiện chưa tồn tại. Nhờ vậy, buildfile có thể mô tả chính xác các đầu vào cần xử lý, kể cả khi một số đầu vào sẽ được tạo ở bước sau hoặc cần được kiểm tra bởi task khác.

## 1. FileList là gì?

`FileList` là một Ant data type và cũng là một resource collection: nó cung cấp một danh sách tài nguyên dạng file cho những task hỗ trợ kiểu dữ liệu này. Thay vì quét thư mục và tìm file theo mẫu, người viết buildfile nêu rõ tên từng file cần đưa vào danh sách.

Ví dụ:

```xml
<filelist
    id="document.files"
    dir="${docs.src}"
    files="introduction.xml,architecture.xml,api.xml"/>
```

Danh sách trên biểu diễn ba đường dẫn tương đối với thư mục `${docs.src}`:

1. `introduction.xml`
2. `architecture.xml`
3. `api.xml`

Thứ tự trong danh sách chính là thứ tự mà FileList cung cấp các file cho task tiêu thụ nó. FileList không tìm kiếm thêm những file khác trong thư mục và cũng không tự sắp xếp lại danh sách theo tên.

Một đặc điểm quan trọng là tên file có thể được khai báo ngay cả khi file chưa tồn tại. FileList ghi nhận danh sách tên được yêu cầu; bản thân nó không tạo file và cũng không bảo đảm task sử dụng danh sách sẽ xử lý được một file còn thiếu. Cách task tiêu thụ phản ứng với tài nguyên không tồn tại phụ thuộc vào task đó.

## 2. Khai báo FileList

FileList thường được khai báo bằng phần tử `<filelist>` với các thuộc tính sau:

| Thuộc tính | Ý nghĩa | Bắt buộc |
|---|---|---|
| `dir` | Thư mục cơ sở để xác định các file trong danh sách | Có |
| `files` | Danh sách tên file, phân cách bằng dấu phẩy hoặc khoảng trắng | Có, trừ khi dùng phần tử con `<file>` |
| `id` | Tên định danh để tham chiếu FileList ở vị trí khác | Không |
| `refid` | Tham chiếu đến một FileList đã khai báo trước | Không; khi dùng thì không khai báo thêm thuộc tính hay phần tử con khác |

Ví dụ khai báo bằng `dir` và `files`:

```xml
<filelist
    id="release.inputs"
    dir="release/metadata"
    files="version.txt,manifest.xml,checksum.sha256"/>
```

`dir` xác định thư mục gốc; các tên trong `files` được hiểu tương đối với thư mục này. Ví dụ, `version.txt` đại diện cho file `release/metadata/version.txt` nếu thư mục làm việc của project được tổ chức như trong ví dụ.

### 2.1. Danh sách phân cách bằng dấu phẩy

Có thể khai báo nhiều tên file trên cùng một dòng, phân cách bằng dấu phẩy:

```xml
<filelist dir="config" files="app.properties,logging.properties,feature.properties"/>
```

Ant nhận danh sách theo thứ tự được viết: `app.properties`, rồi `logging.properties`, rồi `feature.properties`.

### 2.2. Danh sách phân cách bằng khoảng trắng hoặc xuống dòng

Danh sách cũng có thể được trình bày trên nhiều dòng:

```xml
<filelist dir="docs" files="
    overview.xml
    installation.xml
    configuration.xml
    troubleshooting.xml"/>
```

Cách trình bày nhiều dòng giúp buildfile dễ đọc khi có nhiều đầu vào. Khoảng trắng và dấu phẩy là ký tự phân cách trong thuộc tính `files`; do đó, cách viết này không phù hợp với tên file có chứa khoảng trắng hoặc dấu phẩy.

### 2.3. Dùng phần tử con `<file>`

Từ Apache Ant 1.6.2, FileList hỗ trợ phần tử con `<file name="..."/>`. Cách này cho phép khai báo tên file có khoảng trắng hoặc dấu phẩy mà không bị tách thành nhiều phần tử.

```xml
<filelist dir="release/notes">
    <file name="Release Notes, Q4.txt"/>
    <file name="Migration Guide v2.txt"/>
    <file name="Known Issues.txt"/>
</filelist>
```

Các phần tử con được viết theo thứ tự nào thì danh sách được tạo theo thứ tự đó. Khi tên file chứa dấu phẩy hoặc khoảng trắng, nên dùng `<file>` thay cho thuộc tính `files`.

### 2.4. Tham chiếu FileList bằng refid

Nếu cùng một danh sách được dùng ở nhiều task, có thể khai báo một lần với `id`, sau đó tham chiếu bằng `refid`:

```xml
<filelist
    id="ordered.docs"
    dir="docs/source"
    files="overview.xml,architecture.xml,reference.xml"/>

<target name="print-docs">
    <concat>
        <filelist refid="ordered.docs"/>
    </concat>
</target>
```

Khi dùng `refid`, phần tử FileList chỉ tham chiếu đến danh sách đã định nghĩa. Không kết hợp `refid` với `dir`, `files` hoặc các phần tử con khác trong cùng phần tử tham chiếu.

## 3. FileList giữ thứ tự tường minh như thế nào?

Điểm nổi bật của FileList là danh sách được định nghĩa theo ý định của người viết buildfile. Ví dụ:

```xml
<filelist dir="docs/chapters" files="01-intro.xml,02-install.xml,03-config.xml,04-deploy.xml"/>
```

Danh sách có thứ tự:

```text
docs/chapters/01-intro.xml
        ↓
docs/chapters/02-install.xml
        ↓
docs/chapters/03-config.xml
        ↓
docs/chapters/04-deploy.xml
```

Thứ tự này có ý nghĩa khi task cần xử lý nội dung lần lượt, ví dụ ghép nhiều chương thành một tài liệu, tạo classpath có thứ tự hoặc gọi các build con theo danh sách đã chọn.

FileList không thực hiện sắp xếp theo bảng chữ cái. Nếu muốn đổi thứ tự, hãy thay đổi thứ tự khai báo tên file. Điều này làm cho ý định của buildfile được thể hiện trực tiếp và dễ xem xét trong code review.

### 3.1. Ví dụ ghép tài liệu theo thứ tự

Giả sử tài liệu phát hành gồm các phần:

```text
docs/
└── chapters/
    ├── 01-introduction.xml
    ├── 02-architecture.xml
    ├── 03-installation.xml
    └── 04-operations.xml
```

Ta muốn tạo một file `manual.xml` với nội dung lần lượt từ phần giới thiệu, kiến trúc, cài đặt đến vận hành. Có thể dùng task `concat` kết hợp FileList:

```xml
<target name="assemble-manual">
    <concat destfile="build/manual.xml" encoding="UTF-8">
        <filelist
            dir="docs/chapters"
            files="01-introduction.xml,02-architecture.xml,03-installation.xml,04-operations.xml"/>
    </concat>
</target>
```

Task `concat` đọc các tài nguyên theo thứ tự được FileList cung cấp và nối chúng vào file đích. Nếu một file đầu vào chưa tồn tại, FileList vẫn có thể biểu diễn tên đó, nhưng `concat` cần đọc nội dung nên lượt chạy có thể thất bại. Cần bảo đảm các file cần đọc đã được tạo trước khi target `assemble-manual` chạy.

### 3.2. Thứ tự trong classpath

Một số task cần classpath, chẳng hạn `javac`. Khi classpath gồm nhiều thư viện, thứ tự có thể ảnh hưởng đến việc lớp nào được tìm thấy trước nếu nhiều JAR chứa cùng tên class. Có thể dùng FileList để khai báo thứ tự thư viện rõ ràng:

```xml
<path id="compile.classpath">
    <filelist
        dir="lib"
        files="core-api.jar,logging-adapter.jar,legacy-compat.jar"/>
</path>

<target name="compile">
    <javac srcdir="src/main/java" destdir="build/classes">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Trong ví dụ, FileList cung cấp các JAR theo thứ tự được liệt kê. Phần tử `<path>` kết hợp danh sách tài nguyên thành một path; task `javac` nhận path thông qua `classpath refid`. Nếu thứ tự thư viện có ý nghĩa đối với cách compiler phân giải class, danh sách tường minh giúp người đọc nhận biết và kiểm soát thứ tự đó.

## 4. Phân biệt FileList và FileSet

`FileList` và `FileSet` đều có thể cung cấp danh sách file cho task, nhưng cách xác định thành viên của danh sách khác nhau.

| Tiêu chí | FileList | FileSet |
|---|---|---|
| Cách chọn file | Nêu rõ từng tên file | Quét thư mục và lọc theo pattern, selector |
| File không tồn tại | Vẫn có thể được ghi trong danh sách | Không được trả về như một file khớp |
| Wildcard | Không mở rộng wildcard; tên có wildcard được giữ nguyên như tên được khai báo | Hỗ trợ pattern như `*.java`, `**/*.xml` |
| Thứ tự | Thứ tự tường minh theo danh sách khai báo | Không nên dựa vào một thứ tự cố định khi quét tập file |
| Khi phù hợp | Đầu vào đã biết, thứ tự xử lý có ý nghĩa | Muốn lấy mọi file đáp ứng một quy tắc lọc |

Ví dụ FileList:

```xml
<filelist dir="src" files="Main.java,Config.java,Launcher.java"/>
```

Ví dụ FileSet:

```xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/*Test.java"/>
</fileset>
```

FileList biểu diễn đúng ba tên đã nêu. FileSet tìm các file Java đang tồn tại dưới `src`, loại những file có tên kết thúc bằng `Test.java`. Nếu ngày mai thêm `NewFeature.java`, FileSet có thể tự đưa file mới vào kết quả mà không cần sửa buildfile; FileList vẫn chỉ chứa ba tên đã khai báo cho đến khi người viết cập nhật danh sách.

### 4.1. FileList không hỗ trợ wildcard expansion

Một nhầm lẫn phổ biến là viết:

```xml
<filelist dir="src" files="**/*.java"/>
```

và mong Ant tìm mọi file Java trong toàn bộ cây thư mục. FileList không làm việc đó. Chuỗi `**/*.java` được xem là một tên file được chỉ định nguyên văn; nó không được mở rộng thành các file khớp pattern.

Nếu muốn tìm tất cả file Java, hãy dùng FileSet:

```xml
<fileset dir="src" includes="**/*.java"/>
```

Nếu muốn chọn một vài file Java cụ thể theo thứ tự, hãy dùng FileList:

```xml
<filelist dir="src" files="com/example/Main.java,com/example/Config.java"/>
```

## 5. FileList có thể chứa file chưa tồn tại

FileList mô tả danh sách tên file chứ không phải kết quả quét file system. Vì vậy, nó có thể đại diện cho những file chưa được tạo tại thời điểm khai báo.

Ví dụ:

```xml
<filelist
    id="generated.inputs"
    dir="build/generated"
    files="version.properties,build-info.xml"/>
```

Hai file có thể được tạo bởi target trước đó. Việc FileList có thể khai báo chúng trước khi chúng tồn tại giúp buildfile mô tả danh sách đầu vào ổn định.

Tuy nhiên, cần phân biệt ba việc:

1. **Khai báo:** FileList ghi nhận tên file trong danh sách.
2. **Tạo file:** một task khác như `echo`, `copy`, `javac` hoặc công cụ sinh mã phải tạo file nếu cần.
3. **Tiêu thụ file:** task sử dụng FileList sẽ đọc, sao chép, kiểm tra hoặc xử lý file theo chức năng của nó.

FileList chỉ đảm nhiệm việc thứ nhất. Nó không tự tạo file và cũng không tự bỏ qua lỗi nếu task tiêu thụ yêu cầu file phải tồn tại.

### 5.1. Dùng FileList với dependset

Một tình huống phù hợp với khả năng liệt kê file chưa tồn tại là kiểm tra đầu vào và đầu ra bằng task `dependset`. Ví dụ, tài liệu HTML đầu ra cần được tạo lại nếu một trong các file XML nguồn mới hơn hoặc bị thiếu:

```xml
<target name="check-generated-docs">
    <dependset>
        <srcfiles>
            <filelist
                dir="docs/source"
                files="overview.xml,api.xml,examples.xml"/>
        </srcfiles>
        <targetfiles>
            <filelist
                dir="build/docs"
                files="manual.html"/>
        </targetfiles>
    </dependset>
</target>
```

`dependset` so sánh các file nguồn và file đích. Nếu file nguồn mới hơn file đích hoặc một file nguồn được liệt kê bị thiếu, task có thể xóa các file đích để báo rằng kết quả cần được tạo lại. Đây là ví dụ cho thấy việc FileList có thể nhắc đến file chưa tồn tại có giá trị thực tế trong một số thao tác kiểm tra dependency.

Lưu ý: `dependset` chỉ thực hiện kiểm tra và xóa đầu ra cũ theo quy tắc của nó; nó không tự biên dịch hoặc sinh lại tài liệu. Một target tạo tài liệu phải chạy sau đó để tạo đầu ra mới.

## 6. Dùng FileList như một resource collection

FileList có thể được khai báo độc lập rồi đưa vào task hỗ trợ resource collection. Cách sử dụng phụ thuộc vào task cụ thể; không phải task Ant nào cũng nhận FileList.

Một số ví dụ sử dụng thường gặp:

- `concat`: nối nội dung của danh sách file theo thứ tự.
- `path`: đưa danh sách file vào classpath hoặc một path-like structure.
- `subant`: dùng danh sách đường dẫn để xác định các build con theo thứ tự.
- Một số task file khác hỗ trợ FileList như một nested resource collection.

Trước khi đặt `<filelist>` vào một task, cần xem task đó có hỗ trợ FileList hoặc resource collection hay không.

### 6.1. Tái sử dụng danh sách với id và refid

Ví dụ khai báo một danh sách dùng chung:

```xml
<filelist
    id="ordered.config.files"
    dir="config"
    files="defaults.properties,application.properties,logging.properties"/>

<target name="merge-config-report">
    <concat destfile="build/config-report.txt">
        <filelist refid="ordered.config.files"/>
    </concat>
</target>
```

Việc đặt `id` giúp tránh lặp lại danh sách tên file ở nhiều nơi. Khi muốn đổi thứ tự hoặc thêm một file, người viết build chỉ cần cập nhật định nghĩa gốc.

### 6.2. Kết hợp nhiều resource collection

Một task như `concat` có thể nhận nhiều resource collection. Ví dụ:

```xml
<concat destfile="build/all-docs.xml" encoding="UTF-8">
    <filelist
        dir="docs/required"
        files="overview.xml,architecture.xml"/>

    <fileset dir="docs/generated" includes="*.xml"/>
</concat>
```

FileList cung cấp nhóm file bắt buộc theo danh sách tường minh; FileSet cung cấp các file được tìm thấy theo pattern. Các resource collection được đưa vào task theo thứ tự phần tử xuất hiện, nhưng thứ tự bên trong một FileSet không được bảo đảm như danh sách tường minh của FileList. Nếu toàn bộ thứ tự đầu vào có ý nghĩa, hãy thiết kế danh sách và cách kết hợp sao cho không phụ thuộc vào thứ tự quét của FileSet.

## 7. FileList trong task subant

Khi repository có nhiều dự án con, task `subant` có thể gọi build của từng thư mục con. Nếu thứ tự build quan trọng, FileList là lựa chọn phù hợp để khai báo danh sách build con theo thứ tự rõ ràng.

Ví dụ minh họa:

```xml
<target name="build-modules">
    <subant target="jar" genericantfile="build.xml">
        <filelist dir="modules" files="core,api,worker"/>
    </subant>
</target>
```

Trong cách dùng này, danh sách đường dẫn được khai báo theo thứ tự `core`, `api`, `worker`. Thuộc tính `genericantfile` yêu cầu `subant` dùng cùng một buildfile tương đối cho các thư mục được liệt kê. Mỗi thư mục con cần có cấu trúc phù hợp và file `build.xml` tương ứng.

Nếu dùng FileSet hoặc DirSet để tìm thư mục con, thứ tự kết quả không nên được xem là thứ tự phụ thuộc đáng tin cậy. Khi module `api` cần `core` được build trước, hãy thể hiện thứ tự đó tường minh trong FileList hoặc thiết kế quan hệ phụ thuộc phù hợp giữa các build.

Ví dụ trên chỉ minh họa cơ chế liệt kê và gọi build con. Với một repository thật, cần cấu hình `genericantfile`, target và đường dẫn module theo cấu trúc thực tế của dự án.

## 8. Những lỗi thường gặp khi dùng FileList

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| FileList không tìm thấy file như mong muốn | `dir` hoặc tên file tương đối bị sai | Kiểm tra thư mục cơ sở và đường dẫn từng phần tử |
| Wildcard không tìm ra nhiều file | FileList không hỗ trợ mở rộng pattern | Dùng FileSet nếu cần pattern matching |
| Tên file có dấu cách bị tách thành nhiều tên | Dùng thuộc tính `files` với tên chứa khoảng trắng | Dùng phần tử con `<file name="..."/>` |
| Tên file có dấu phẩy bị tách | Dấu phẩy là ký tự phân cách trong `files` | Dùng phần tử con `<file>` |
| Task thất bại dù FileList đã khai báo file | FileList có thể chứa tên chưa tồn tại; task tiêu thụ yêu cầu đọc file thật | Kiểm tra target tạo file trước và quy tắc xử lý file thiếu của task |
| Danh sách dùng nhầm thư mục | `dir` được hiểu là thư mục cơ sở của FileList | Kiểm tra basedir và đường dẫn thực tế |
| Thứ tự đầu vào không như dự kiến | Danh sách được khai báo sai thứ tự hoặc trộn với collection không có thứ tự xác định | Sắp xếp lại FileList và xem quy tắc thứ tự của từng resource collection |
| Lỗi khi dùng refid | Vừa dùng `refid` vừa khai báo thêm thuộc tính hoặc phần tử con | Khi tham chiếu, chỉ dùng `refid`; không kết hợp với `dir`, `files`, `id` hoặc phần tử con |

### 8.1. Nhầm FileList với FileSet

Không dùng FileList khi mục tiêu là quét thư mục theo mẫu:

```xml
<!-- Không mở rộng thành tất cả file Java. -->
<filelist dir="src" files="**/*.java"/>
```

Thay bằng:

```xml
<fileset dir="src" includes="**/*.java"/>
```

Ngược lại, nếu cần ghép đúng ba file theo thứ tự do tài liệu quy định, FileSet có thể không diễn đạt được ý định về thứ tự một cách rõ ràng. Khi đó, FileList phù hợp hơn:

```xml
<filelist dir="docs" files="intro.xml,concepts.xml,reference.xml"/>
```

### 8.2. Không kiểm tra file đầu vào trước khi task sử dụng

Do FileList không lọc theo sự tồn tại, danh sách có thể hợp lệ về mặt khai báo nhưng task vẫn lỗi khi đọc một file bị thiếu.

Nếu các file phải được sinh ra trước, hãy thể hiện thứ tự target:

```xml
<target name="generate-sources">
    <!-- Tạo các file đầu vào cần thiết. -->
</target>

<target name="assemble" depends="generate-sources">
    <concat destfile="build/combined.txt">
        <filelist dir="build/generated" files="header.txt,body.txt,footer.txt"/>
    </concat>
</target>
```

Quan hệ `depends` bảo đảm target tạo nguồn chạy trước target tiêu thụ danh sách. Nếu file vẫn không được tạo, task `concat` sẽ báo lỗi và build không thể được xem là thành công.

## 9. Cách lựa chọn giữa FileList, FileSet và Path

Ba kiểu dữ liệu này có thể cùng xuất hiện trong một buildfile, nhưng phục vụ mục đích khác nhau:

| Kiểu dữ liệu | Vai trò chính | Ví dụ phù hợp |
|---|---|---|
| `FileList` | Danh sách file được nêu tên và có thứ tự rõ ràng | Ghép chương tài liệu theo thứ tự, chọn thư viện cụ thể |
| `FileSet` | Tập file được chọn bằng pattern và selector | Tìm tất cả file `.java`, loại file test hoặc file tạm |
| `Path` | Biểu diễn một đường dẫn gồm nhiều file/thư mục, thường dùng cho classpath | Cung cấp classpath cho `javac`, `java` hoặc task cần path |

FileList có thể được đặt bên trong Path, còn FileSet cũng có thể là một phần của Path. Ví dụ:

```xml
<path id="application.classpath">
    <!-- Các thư viện nền tảng theo thứ tự đã chỉ định. -->
    <filelist dir="lib/core" files="api.jar,implementation.jar"/>

    <!-- Các thư viện plugin tìm theo mẫu. -->
    <fileset dir="lib/plugins" includes="*.jar"/>

    <!-- Thư mục class đã biên dịch. -->
    <pathelement location="build/classes"/>
</path>
```

Path kết hợp các phần tử theo thứ tự được khai báo, nhưng những phần tử collection có quy tắc thứ tự riêng. FileList cung cấp thứ tự tên tường minh; FileSet quét theo pattern nên không nên dựa vào thứ tự file được phát hiện. Khi thứ tự classpath quan trọng, hãy kiểm soát các phần tử có thứ tự không xác định.

## 10. Kết luận

`FileList` là kiểu dữ liệu của Apache Ant dùng để mô tả một danh sách file được chỉ định tường minh. Danh sách gắn với thư mục cơ sở `dir`, có thể khai báo qua thuộc tính `files` hoặc các phần tử con `<file>`, có thể tái sử dụng bằng `id` và `refid`, đồng thời giữ thứ tự các tên đã khai báo. FileList không mở rộng wildcard và có thể chứa tên file chưa tồn tại.

Khi cần tìm file theo pattern, hãy dùng `FileSet`. Khi cần một danh sách đầu vào cố định và thứ tự xử lý có ý nghĩa, hãy dùng `FileList`. Nếu task cần một classpath hoặc path-like structure, có thể kết hợp FileList bên trong `Path`. Việc lựa chọn đúng kiểu dữ liệu giúp buildfile diễn đạt rõ ý định, kiểm soát thứ tự và tránh nhầm lẫn giữa danh sách tên file với kết quả quét hệ thống file.
