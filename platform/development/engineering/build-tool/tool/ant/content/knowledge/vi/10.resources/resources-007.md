# Khác biệt giữa tập tài nguyên tổng quát và task chỉ nhận tệp hệ thống

## 1. Resource trong Apache Ant là gì?

Khi một task Ant cần đọc, sao chép, đóng gói hoặc xử lý đầu vào, đầu vào đó không nhất thiết phải là một tệp thông thường nằm trực tiếp trên filesystem. Nó có thể đến từ thư mục dự án, một mục bên trong ZIP, URL, classpath hoặc một nguồn dữ liệu khác.

Ant mô hình hóa một đầu vào đơn lẻ bằng khái niệm **Resource**. Resource mô tả một tài nguyên có tên và có thể cung cấp thông tin như:

- Tên tài nguyên.
- Tài nguyên có tồn tại hay không.
- Kích thước và thời điểm sửa đổi, nếu nguồn có cung cấp.
- Nội dung thông qua input stream.
- Khả năng ánh xạ tới một đối tượng tệp hệ thống, nếu loại resource hỗ trợ.

Một Resource không nhất thiết là `java.io.File`. Ví dụ, nội dung của một URL có thể đọc được qua stream mà không tồn tại dưới dạng tệp cục bộ.

**ResourceCollection** là abstraction biểu diễn một tập Resource. Một collection có thể chứa một hoặc nhiều tài nguyên. Tùy loại collection, nó có thể quét thư mục, liệt kê danh sách, kết hợp nhiều nguồn hoặc lọc một tập đầu vào khác.

Vì vậy, cần phân biệt hai câu hỏi:

1. Task có nhận được một tập tài nguyên hay không?
2. Task có yêu cầu mỗi tài nguyên phải là một tệp thực sự trên filesystem hay không?

Hai yêu cầu này không tương đương.

## 2. ResourceCollection và các nguồn tài nguyên

Một số loại Resource và ResourceCollection thường gặp trong Ant:

| Loại | Mục đích | Đặc điểm |
|---|---|---|
| `FileResource` | Đại diện cho một tệp hệ thống | Có thể ánh xạ tới `java.io.File` |
| `FileSet` | Quét thư mục và chọn tệp theo pattern | Các phần tử được chọn là tài nguyên dựa trên tệp hệ thống |
| `FileList` | Khai báo danh sách đường dẫn tệp tường minh | Không quét pattern như FileSet; có thể khai báo tệp chưa tồn tại |
| `Path` | Tập hợp các phần tử đường dẫn | Thường dùng cho classpath hoặc đường dẫn công cụ |
| `ZipFileSet` | Chọn các entry trong một tệp ZIP | Entry là tài nguyên trong archive, không phải tệp độc lập đã được giải nén |
| `URLResource` | Đại diện cho tài nguyên được truy cập qua URL | Nội dung được đọc từ nguồn URL |
| `JavaResource` | Tìm tài nguyên qua classloader/classpath | Có thể nằm trong thư mục classpath hoặc JAR |
| `StringResource` | Đại diện cho nội dung chuỗi | Không cần tệp vật lý để chứa nội dung |

Ant còn cung cấp các collection dùng để kết hợp hoặc lọc tài nguyên, ví dụ `Union`, `Restrict`, `Difference`, `Intersect` và `Sort`. Chúng cho phép xây dựng một tập đầu vào từ những nguồn khác nhau mà không cần tạo bản sao của từng tệp.

Ví dụ, một `FileSet` là một ResourceCollection phù hợp với tệp hệ thống:

```xml
<copy todir="${basedir}/build/classes">
    <fileset dir="${basedir}/src">
        <include name="**/*.java"/>
        <exclude name="**/generated/**"/>
    </fileset>
</copy>
```

Một collection tổng quát có thể kết hợp một tệp cục bộ và một URL:

```xml
<concat destfile="${basedir}/build/release-bundle.txt">
    <resources>
        <file file="${basedir}/README.md"/>
        <url url="https://example.org/release-notes.txt"/>
    </resources>
</concat>
```

Collection thứ hai có hai Resource với nguồn khác nhau. Tệp README có thể ánh xạ tới một `File`, còn nội dung URL được truy cập qua kết nối mạng. Không thể coi cả hai phần tử như hai đường dẫn tệp cục bộ.

## 3. Resource có thể đọc được không đồng nghĩa với có File

Một Resource tổng quát thường cho phép task đọc nội dung bằng stream. Task không cần biết dữ liệu nằm trong file, archive hay một nguồn từ xa; nó chỉ cần biết cách lấy nội dung.

Ngược lại, một task thao tác trực tiếp với filesystem có thể cần một đường dẫn tệp thật để gọi API của hệ điều hành hoặc Java. Ví dụ:

- Đổi quyền truy cập của một tệp.
- Đổi thời điểm sửa đổi của tệp.
- Xóa hoặc đổi tên một tệp.
- Tạo khóa hoặc thao tác trên một đường dẫn vật lý.
- Gọi một chương trình native yêu cầu đối số là đường dẫn tệp cục bộ.

Một URL có thể cung cấp nội dung đọc được, nhưng không có quyền truy cập filesystem để Ant đổi permission của URL. Một entry trong ZIP cũng có tên và nội dung, nhưng bản thân entry không phải một tệp riêng trên đĩa.

Một số Resource có thể cung cấp khả năng ánh xạ thông qua interface `FileProvider`. Task hoặc đoạn code cần `File` có thể kiểm tra khả năng này. Không nên mặc định mọi Resource đều triển khai `FileProvider`, cũng không nên tự biến tên resource thành đường dẫn filesystem.

Có thể hình dung hai nhóm như sau:

```text
Resource
  |
  +-- Resource đọc được qua stream
  |      +-- URLResource
  |      +-- JavaResource
  |      +-- StringResource
  |      +-- tài nguyên trong archive
  |
  +-- Resource có thể ánh xạ tới File
         +-- FileResource
         +-- các phần tử tệp trong FileSet
```

Sơ đồ chỉ mô tả khả năng thường gặp. Một task cụ thể vẫn phải kiểm tra contract của loại Resource mà nó nhận.

## 4. Task nhận ResourceCollection tổng quát

Một task được thiết kế theo ResourceCollection có thể duyệt qua các Resource và xử lý nội dung theo cách phù hợp với từng nguồn. Task có thể đọc stream, dùng metadata của resource hoặc chuyển nội dung sang đầu ra khác.

Ví dụ, `concat` có thể ghép nội dung của một collection vào một tệp kết quả:

```xml
<concat destfile="${basedir}/build/release-bundle.txt">
    <resources>
        <file file="${basedir}/config/defaults.txt"/>
        <url url="https://example.org/release-notes.txt"/>
    </resources>
</concat>
```

Trong ví dụ này, task xử lý nội dung của collection. Tệp đầu vào thứ nhất được đọc từ filesystem; tài nguyên thứ hai được đọc từ URL. Kết quả ghép được ghi vào tệp đích.

Một ví dụ khác là `loadresource`, dùng để nạp nội dung một Resource vào property:

```xml
<loadresource property="remote.release.notes">
    <url url="https://example.org/release-notes.txt"/>
</loadresource>

<echo message="${remote.release.notes}"/>
```

Task này đọc nội dung resource và đưa nội dung đó vào property. Nó không yêu cầu URL phải được tải thành một tệp cục bộ trước.

Khi dùng resource từ xa, build phụ thuộc vào kết nối mạng, quyền truy cập, trạng thái máy chủ và nội dung trả về. Với build cần tính tái lập cao, nên cân nhắc tải và kiểm soát phiên bản nội dung trước khi dùng, hoặc lưu bản đầu vào đã xác minh trong hệ thống artifact của dự án.

## 5. Task chỉ nhận tệp hệ thống

Một task file-oriented làm việc với đường dẫn filesystem cụ thể. Ví dụ `touch` cập nhật thời điểm sửa đổi của tệp:

```xml
<target name="mark-release">
    <touch file="${basedir}/build/release.marker"/>
</target>
```

Thuộc tính `file` cần một đường dẫn tệp mà filesystem có thể thao tác. Không thể thay đường dẫn này bằng một URLResource hoặc một ZipResource rồi mong Ant tự đổi timestamp của tài nguyên ở nguồn đó.

Tương tự, task `chmod` thay đổi quyền truy cập trên filesystem:

```xml
<chmod file="${basedir}/scripts/deploy.sh" perm="755"/>
```

`chmod` cần một tệp hệ thống mà hệ điều hành cho phép thay đổi permission. Một resource chỉ đọc được qua stream không cung cấp đối tượng tệp để thao tác permission.

Với nhiều tệp, task file-oriented có thể cung cấp giao diện nhận `FileSet` hoặc một collection được giới hạn ở các resource hệ thống. Ví dụ minh họa chọn các script từ thư mục:

```xml
<chmod perm="755">
    <fileset dir="${basedir}/scripts">
        <include name="*.sh"/>
    </fileset>
</chmod>
```

Khả năng nhận phần tử lồng nhau cụ thể phụ thuộc vào task và phiên bản Ant. Hãy đọc tài liệu task để biết nó chấp nhận `FileSet`, `FileList`, `Path` hay một ResourceCollection rộng hơn. Không được suy luận rằng một task nhận `FileSet` thì cũng nhận mọi loại ResourceCollection.

## 6. So sánh contract của hai nhóm task

| Tiêu chí | Task nhận ResourceCollection tổng quát | Task chỉ nhận tệp hệ thống |
|---|---|---|
| Đầu vào | Một tập Resource có thể đến từ nhiều nguồn | File hoặc collection mà các phần tử ánh xạ tới filesystem |
| Cách đọc dữ liệu | Thường qua stream và metadata | Có thể dùng đường dẫn, File API hoặc API của hệ điều hành |
| URLResource | Có thể nhận nếu task hỗ trợ ResourceCollection | Không thể thao tác trực tiếp như một file cục bộ |
| Zip entry | Có thể đọc nếu task hỗ trợ resource từ archive | Cần giải nén/materialize nếu task cần file độc lập |
| FileSet | Thường có thể dùng vì đây là collection của file resource | Thường phù hợp nếu task hỗ trợ FileSet |
| Ví dụ thao tác | Ghép nội dung, nạp nội dung vào property, xử lý stream | Đổi quyền, đổi timestamp, xóa hoặc đổi tên tệp |

Điểm phân biệt không nằm ở việc một collection có nhiều hay ít phần tử. Nó nằm ở loại phần tử và hợp đồng đầu vào mà task yêu cầu.

Một ResourceCollection có thể chứa hoàn toàn FileResource, nhưng không phải mọi ResourceCollection đều là filesystem-only. Ngược lại, FileSet là một loại collection được xây dựng để quét và chọn tệp trong một cây thư mục.

## 7. Chuyển tài nguyên tổng quát thành tệp hệ thống

Khi cần đưa một resource không nằm trên filesystem vào task chỉ nhận tệp, phải tạo một tệp vật lý trước. Quy trình tổng quát:

1. Đọc hoặc tải Resource từ nguồn.
2. Ghi nội dung vào một đường dẫn đích trên filesystem.
3. Xác nhận tệp đích đã được tạo thành công.
4. Truyền đường dẫn đó cho task file-oriented.

Ví dụ, tải một tệp từ URL về thư mục build rồi thay đổi quyền:

```xml
<target name="prepare-script">
    <mkdir dir="${basedir}/build/downloads"/>

    <get src="https://example.org/deploy.sh"
         dest="${basedir}/build/downloads/deploy.sh"
         usetimestamp="true"/>

    <chmod file="${basedir}/build/downloads/deploy.sh"
           perm="755"/>
</target>
```

`get` ghi nội dung URL thành tệp trên filesystem. Sau khi có tệp cục bộ, `chmod` mới có thể thao tác quyền của tệp đó.

Với tài nguyên nằm trong ZIP, giải nén entry cần dùng trước khi gọi task file-oriented:

```xml
<target name="prepare-config">
    <mkdir dir="${basedir}/build/extracted"/>

    <unzip src="${basedir}/dist/configuration.zip"
           dest="${basedir}/build/extracted">
        <patternset>
            <include name="config/runtime.properties"/>
        </patternset>
    </unzip>

    <touch file="${basedir}/build/extracted/config/runtime.properties"/>
</target>
```

Entry trong ZIP được trích xuất thành tệp thật ở thư mục đích. Task `touch` sau đó thao tác trên tệp đã giải nén.

Khi materialize tài nguyên, cần quyết định nơi lưu, thời điểm dọn dẹp và cách xác minh nội dung. Nếu tài nguyên từ xa thay đổi theo thời gian, nên kiểm soát phiên bản hoặc checksum để build không vô tình sử dụng đầu vào khác nhau giữa các lần chạy.

## 8. Kiểm tra một ResourceCollection có chỉ chứa file hay không

Trong API của Ant, `ResourceCollection` cung cấp thông tin về collection, bao gồm khả năng kiểm tra nó có chỉ chứa resource thuộc filesystem hay không thông qua `isFilesystemOnly()`.

Ví dụ ý tưởng trong Java:

```java
import org.apache.tools.ant.types.ResourceCollection;

public class ResourceInspector {
    public static void inspect(ResourceCollection resources) {
        if (resources.isFilesystemOnly()) {
            System.out.println("All resources are filesystem-backed.");
        } else {
            System.out.println("The collection may contain non-file resources.");
        }
    }
}
```

Giá trị `true` cho biết collection được báo cáo là chỉ gồm các resource filesystem theo contract của Ant. Giá trị `false` có nghĩa consumer không được giả định tất cả phần tử đều có thể chuyển thành File.

Đối với một Resource riêng lẻ, API `FileProvider` là cách kiểm tra khả năng cung cấp `File`:

```java
import java.io.File;
import org.apache.tools.ant.types.Resource;
import org.apache.tools.ant.types.resources.FileProvider;

public class ResourceFileAccess {
    public static File asFile(Resource resource) {
        FileProvider provider = resource.as(FileProvider.class);
        return provider == null ? null : provider.getFile();
    }
}
```

Nếu `as(FileProvider.class)` không trả về provider, resource không cung cấp khả năng ánh xạ tới một File theo interface đó. Code gọi không nên tự dựng đường dẫn từ `resource.getName()` để thay thế, vì tên có thể chỉ là tên logic hoặc tên entry trong archive.

Trong code task tùy biến, nên khai báo rõ task nhận `ResourceCollection` hay yêu cầu filesystem-only. Nếu task cần `File`, kiểm tra collection trước và báo lỗi có ngữ cảnh khi gặp resource không tương thích.

## 9. Lỗi thường gặp khi trộn hai loại đầu vào

### Đưa URL hoặc archive entry vào task cần File

Task có thể từ chối collection hoặc không thể lấy đường dẫn vật lý. Hãy dùng task hỗ trợ ResourceCollection để đọc nội dung, hoặc materialize resource thành tệp trước.

### Nhầm tên Resource với đường dẫn trên đĩa

`getName()` trả về tên tài nguyên theo abstraction của resource. Tên này không bảo đảm là đường dẫn tuyệt đối hay tương đối hợp lệ trên filesystem. Hãy dùng `FileProvider` khi cần File.

### Cho rằng FileSet và mọi ResourceCollection là tương đương

`FileSet` là một loại ResourceCollection chuyên quét tệp hệ thống. Một collection có URL, string hoặc archive entry vẫn là ResourceCollection nhưng không phải filesystem-only.

### Dùng task có API hẹp nhưng truyền collection rộng

Một task chỉ khai báo thuộc tính `file`, hoặc chỉ nhận FileSet, không tự động hiểu `<resources>` hay URLResource. Cần xem tài liệu task và kiểu dữ liệu của phần tử lồng nhau mà task hỗ trợ.

### Tải tài nguyên từ xa nhưng không kiểm soát nội dung

URL có thể trả nội dung khác giữa các lần build, bị gián đoạn hoặc không truy cập được. Với đầu vào quan trọng, hãy pin phiên bản, xác minh checksum hoặc đưa artifact vào repository được kiểm soát.

### Xóa hoặc thay đổi tệp trước khi xác nhận nguồn

Khi task có tác động phá hủy hoặc sửa metadata, hãy xác định rõ FileSet nào được chọn và đường dẫn đích thực tế. Không truyền một collection chưa được hiểu rõ vào task xóa hoặc thay đổi quyền.

## 10. Nguyên tắc thiết kế build

- Chọn ResourceCollection khi task thực sự xử lý được nội dung từ nhiều loại nguồn.
- Chọn FileSet hoặc một đầu vào filesystem-only khi task cần các đường dẫn tệp hệ thống.
- Đọc contract của từng task thay vì suy luận từ tên phần tử XML hoặc từ việc một collection có thể lặp qua các Resource.
- Khi viết custom task, khai báo rõ yêu cầu đầu vào: resource tổng quát hay filesystem-only.
- Dùng `isFilesystemOnly()` hoặc `FileProvider` để kiểm tra khả năng tương thích trước khi thao tác bằng File API.
- Materialize resource vào thư mục build khi cần chuyển từ stream/entry/URL thành một tệp vật lý.
- Xác minh nguồn, nội dung và đường dẫn đích trước các thao tác thay đổi permission, timestamp hoặc xóa tệp.
- Với tài nguyên từ xa, kiểm soát phiên bản và checksum để tăng tính tái lập của build.

ResourceCollection giúp Ant xử lý đầu vào theo một abstraction chung, còn FileSet và FileResource thể hiện những tài nguyên gắn với filesystem. Một task có thể làm việc với tập tài nguyên tổng quát nếu nó đọc được resource theo contract của Ant; task thao tác trực tiếp trên tệp hệ thống cần đầu vào có thể ánh xạ tới File. Hiểu rõ sự khác nhau này giúp chọn đúng kiểu collection, tránh lỗi kiểu dữ liệu và biết khi nào cần materialize tài nguyên trước khi xử lý.

