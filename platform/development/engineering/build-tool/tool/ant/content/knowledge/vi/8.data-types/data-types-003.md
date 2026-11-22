# PatternSet và chia sẻ mẫu chọn tệp

Trong Apache Ant, nhiều task cần chọn một nhóm tệp để biên dịch, đóng gói, sao chép hoặc xử lý. `FileSet` mô tả một tập tệp nằm dưới một thư mục gốc; các mẫu `include` và `exclude` quyết định đường dẫn nào được giữ lại. Khi nhiều bước build cần cùng một quy tắc chọn tệp, khai báo lặp lại các mẫu ở từng nơi vừa dài vừa dễ lệch nhau.

`PatternSet` là kiểu dữ liệu của Ant dùng để gom các mẫu bao gồm và loại trừ thành một cấu hình có thể tái sử dụng. Có thể khai báo một `PatternSet` với `id`, sau đó tham chiếu nó bằng `refid` từ nhiều `FileSet`. Nhờ đó, quy tắc chọn tệp được định nghĩa một lần nhưng có thể áp dụng cho nhiều thư mục hoặc nhiều bước build.

## 1. PatternSet và FileSet có vai trò gì?

Hai kiểu dữ liệu này có trách nhiệm liên quan nhưng khác nhau:

| Kiểu dữ liệu | Trách nhiệm |
|---|---|
| `FileSet` | Xác định thư mục gốc cần quét và tập tệp được chọn trong thư mục đó |
| `PatternSet` | Xác định các mẫu đường dẫn được bao gồm hoặc loại trừ |

Một `PatternSet` không tự chọn tệp trên ổ đĩa vì nó không chứa thư mục gốc. Nó chỉ giữ các quy tắc tên đường dẫn. Khi đặt `PatternSet` bên trong `FileSet`, Ant áp dụng các quy tắc đó lên những đường dẫn tương đối với thư mục `dir` của `FileSet`.

Ví dụ, một `FileSet` có thư mục gốc là `src` và một mẫu `**/*.java` sẽ chọn các tệp Java trong `src` và các thư mục con. Cùng mẫu đó có thể được dùng với một `FileSet` khác có thư mục gốc là `module-a/src`; kết quả được tính tương đối với thư mục gốc mới.

## 2. Khai báo include và exclude trực tiếp

`PatternSet` hỗ trợ hai nhóm mẫu:

- `include`: chỉ định những đường dẫn có thể được chọn.
- `exclude`: chỉ định những đường dẫn phải bị loại khỏi kết quả, kể cả khi chúng khớp với một mẫu include.

Ví dụ chọn mã nguồn Java nhưng bỏ qua mã được sinh tự động:

```xml
<fileset dir="src">
    <patternset>
        <include name="**/*.java" />
        <exclude name="**/generated/**" />
    </patternset>
</fileset>
```

Ant quét các tệp dưới `src`, chọn những tệp có đường dẫn khớp `**/*.java`, sau đó loại các tệp nằm trong một nhánh thư mục `generated` ở bất kỳ cấp nào.

Có thể viết trực tiếp các phần tử `include` và `exclude` bên trong `fileset`, vì `FileSet` hỗ trợ các mẫu này:

```xml
<fileset dir="src">
    <include name="**/*.java" />
    <exclude name="**/generated/**" />
</fileset>
```

Khi quy tắc chỉ được dùng một lần, cách viết trực tiếp có thể đủ rõ ràng. Khi cần tái sử dụng cùng một nhóm mẫu, nên tách chúng thành `PatternSet` có `id`.

## 3. Cú pháp mẫu đường dẫn của Ant

Mẫu của Ant là mẫu đường dẫn (*path pattern*), không phải biểu thức chính quy. Các ký tự đại diện thường dùng là:

| Ký hiệu | Ý nghĩa | Ví dụ |
|---|---|---|
| `*` | Khớp không hoặc nhiều ký tự trong một thành phần đường dẫn, không đi qua dấu phân cách thư mục | `*.xml` |
| `?` | Khớp đúng một ký tự trong một thành phần đường dẫn | `Test?.java` |
| `**` | Khớp qua nhiều cấp thư mục | `**/*.java` |

Ví dụ cụ thể:

```xml
<patternset>
    <!-- Tệp XML nằm ngay trong thư mục gốc của FileSet -->
    <include name="*.xml" />

    <!-- Tệp Java ở thư mục gốc hoặc bất kỳ cấp thư mục con nào -->
    <include name="**/*.java" />

    <!-- Tệp có tên bắt đầu bằng Test và kết thúc bằng .java -->
    <include name="**/Test*.java" />

    <!-- Loại tệp tạm ở mọi cấp -->
    <exclude name="**/*.tmp" />
</patternset>
```

Phân biệt `*` và `**` là điều đặc biệt quan trọng. `*.java` chỉ khớp tên tệp trong thư mục gốc của `FileSet`; nó không đi sâu vào thư mục con. `**/*.java` có thể khớp tệp Java ở nhiều cấp, kể cả tệp nằm ngay trong thư mục gốc.

Các mẫu thường được viết bằng dấu `/` để biểu diễn cấp thư mục. Ant xử lý mẫu theo đường dẫn của nó, nên cách viết này phù hợp cho buildfile chạy trên nhiều hệ điều hành.

Ví dụ nếu `FileSet` có `dir="project"`, mẫu `src/**/*.java` được so khớp với các đường dẫn tương đối như `src/App.java` hoặc `src/main/java/App.java`. Mẫu `**/test/**` có thể dùng để loại các tệp nằm dưới thư mục `test` ở bất kỳ vị trí nào.

## 4. Quy tắc kết hợp include và exclude

Có thể hiểu quá trình chọn tệp theo hai bước:

1. Xác định tập ứng viên bằng các mẫu include.
2. Loại mọi tệp khớp với một trong các mẫu exclude.

Nếu không khai báo mẫu include nào, Ant mặc định xem mọi tệp trong phạm vi `FileSet` là ứng viên, sau đó áp dụng các mẫu exclude và các loại trừ mặc định của Ant.

Ví dụ:

```xml
<fileset dir="web">
    <patternset>
        <include name="**/*.html" />
        <include name="**/*.css" />
        <include name="**/*.js" />

        <exclude name="**/node_modules/**" />
        <exclude name="**/*.min.js" />
        <exclude name="**/draft/**" />
    </patternset>
</fileset>
```

Tập kết quả chỉ gồm HTML, CSS và JavaScript được chọn, ngoại trừ các tệp trong `node_modules`, các tệp JavaScript minified và các tệp dưới thư mục `draft`.

Các mẫu include được kết hợp theo hướng cho phép tệp khớp với một mẫu trong nhóm. Exclude có hiệu lực loại bỏ: nếu tệp khớp một mẫu exclude thì tệp không còn trong kết quả, dù trước đó đã khớp include.

## 5. Chia sẻ PatternSet bằng id và refid

Khi nhiều `FileSet` cần cùng một quy tắc, khai báo `PatternSet` một lần ở cấp project và đặt `id` cho nó:

```xml
<project name="shared-patterns" default="package">

    <patternset id="java.sources">
        <include name="**/*.java" />
        <exclude name="**/generated/**" />
        <exclude name="**/test/**" />
    </patternset>

    <target name="package">
        <zip destfile="build/module-a-sources.zip">
            <fileset dir="module-a/src">
                <patternset refid="java.sources" />
            </fileset>
        </zip>

        <zip destfile="build/module-b-sources.zip">
            <fileset dir="module-b/src">
                <patternset refid="java.sources" />
            </fileset>
        </zip>
    </target>

</project>
```

Trong ví dụ:

- `<patternset id="java.sources">` tạo một `PatternSet` có tên tham chiếu là `java.sources`.
- Hai phần tử `<patternset refid="java.sources" />` sử dụng lại cùng cấu hình.
- `module-a/src` và `module-b/src` là hai thư mục gốc khác nhau.
- Mẫu `**/*.java` được đánh giá tương đối với từng thư mục gốc của `FileSet`.
- Các thư mục `generated` và `test` bị loại ở cả hai gói ZIP.

`id` xác định đối tượng dữ liệu trong project Ant; `refid` yêu cầu Ant sử dụng đối tượng đã được định danh đó. Khi tham chiếu bằng `refid`, không khai báo thêm các mẫu khác bên trong cùng phần tử tham chiếu. Nếu cần một quy tắc khác, hãy tạo một `PatternSet` riêng hoặc cấu hình phần bổ sung tại `FileSet` phù hợp.

Việc chia sẻ này giúp sửa quy tắc ở một nơi. Chẳng hạn, nếu nhóm quyết định loại thêm thư mục `generated-sources`, chỉ cần bổ sung một mẫu exclude trong `java.sources`; mọi `FileSet` tham chiếu cấu hình đó sẽ nhận quy tắc chung.

## 6. Đưa mẫu vào tệp cấu hình riêng

Khi danh sách mẫu dài hoặc được nhóm phát triển quản lý riêng, có thể đặt mẫu trong các tệp văn bản rồi nạp bằng `includesfile` và `excludesfile`.

Ví dụ cấu trúc:

```text
project/
├── build.xml
├── config/
│   ├── source-includes.txt
│   └── source-excludes.txt
└── src/
    ├── main/
    └── generated/
```

Nội dung `config/source-includes.txt`:

```text
**/*.java
**/*.properties
**/*.xml
```

Nội dung `config/source-excludes.txt`:

```text
**/generated/**
**/test/**
**/*.bak
```

Buildfile tham chiếu các tệp mẫu:

```xml
<patternset id="project.sources">
    <includesfile name="config/source-includes.txt" />
    <excludesfile name="config/source-excludes.txt" />
</patternset>

<target name="archive-sources">
    <zip destfile="build/sources.zip">
        <fileset dir="src">
            <patternset refid="project.sources" />
        </fileset>
    </zip>
</target>
```

Mỗi dòng trong tệp include hoặc exclude là một mẫu đường dẫn. Cách này phù hợp khi danh sách mẫu được cập nhật thường xuyên hoặc cần được đọc, sửa mà không phải thay đổi cấu trúc buildfile.

Tệp chứa mẫu là đầu vào của build. Cần bảo đảm đường dẫn tới tệp đó đúng với vị trí buildfile và quy ước thư mục của dự án; nếu Ant không tìm thấy tệp mẫu, cấu hình `PatternSet` không thể được nạp như mong muốn.

## 7. Dùng PatternSet cùng các tùy chọn của FileSet

Một số hành vi chọn tệp thuộc về `FileSet`, không phải bản thân `PatternSet`.

### Phân biệt chữ hoa và chữ thường

Mặc định, việc so khớp tên đường dẫn của `FileSet` có phân biệt chữ hoa và chữ thường. Có thể đặt `casesensitive="false"` trên `FileSet` nếu dự án cần so khớp không phân biệt chữ hoa, chữ thường:

```xml
<fileset dir="assets" casesensitive="false">
    <patternset>
        <include name="**/*.png" />
    </patternset>
</fileset>
```

Với tùy chọn này, các tên phần mở rộng như `.png` và `.PNG` có thể được khớp theo quy tắc không phân biệt hoa thường. Hãy chọn cách so khớp phù hợp với quy ước tên tệp của dự án và môi trường build.

### Default excludes

Ant có một tập mẫu loại trừ mặc định để bỏ qua một số tệp và thư mục phụ trợ phổ biến, chẳng hạn metadata của hệ thống quản lý phiên bản hoặc tệp tạm. `FileSet` bật default excludes theo mặc định.

Nếu thực sự cần đưa các tệp thuộc nhóm mặc định đó vào kết quả, có thể tắt cơ chế này trên `FileSet`:

```xml
<fileset dir="repository" defaultexcludes="no">
    <patternset>
        <include name="**/*" />
    </patternset>
</fileset>
```

Chỉ nên tắt default excludes khi mục tiêu đóng gói hoặc xử lý yêu cầu các tệp đó. Trong phần lớn trường hợp, giữ mặc định giúp tránh đưa metadata và tệp phụ trợ không cần thiết vào artifact.

## 8. PatternSet không thay thế các bộ lọc khác

`PatternSet` tập trung vào tên và cấu trúc đường dẫn. Nó phù hợp khi quy tắc chọn tệp có dạng “mọi tệp Java”, “mọi tệp XML trong cấu hình” hoặc “mọi tệp ngoại trừ thư mục sinh tự động”.

Nếu cần chọn theo đặc tính khác như kích thước, thời gian sửa đổi hoặc thuộc tính của tệp, hãy xem xét các selector của Ant trong `FileSet`. PatternSet và selector giải quyết hai kiểu tiêu chí khác nhau; có thể kết hợp chúng trong cùng một `FileSet` khi task hỗ trợ.

Ví dụ, `PatternSet` có thể giới hạn tập ứng viên vào các tệp log, còn selector có thể lọc tiếp theo điều kiện kích thước. Không nên cố biểu diễn điều kiện kích thước bằng một chuỗi wildcard vì wildcard chỉ mô tả tên đường dẫn.

## 9. Lỗi thường gặp khi dùng PatternSet

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Mẫu `*.java` không chọn tệp trong thư mục con | `*` không đi qua dấu phân cách thư mục | Dùng `**/*.java` nếu cần quét nhiều cấp |
| Tệp đã khớp include nhưng không xuất hiện | Tệp cũng khớp một mẫu exclude hoặc default excludes | Kiểm tra toàn bộ mẫu exclude và trạng thái default excludes |
| Cùng PatternSet cho kết quả khác nhau giữa hai FileSet | Hai FileSet có thư mục gốc khác nhau nên đường dẫn tương đối khác nhau | Đánh giá mẫu từ `dir` của từng FileSet |
| `refid` không được phân giải | Không có PatternSet với `id` tương ứng hoặc tham chiếu sai tên | So sánh chính xác giá trị `id` và `refid`, đồng thời bảo đảm cấu hình được khai báo trong project |
| Ant không đọc được mẫu từ tệp ngoài | Đường dẫn `includesfile` hoặc `excludesfile` sai hoặc tệp không tồn tại | Kiểm tra vị trí tệp, tên tệp và đường dẫn được dùng trong buildfile |
| Tệp `.JAVA` không được chọn | FileSet đang so khớp phân biệt hoa thường | Xem lại quy ước tên tệp hoặc đặt `casesensitive="false"` khi phù hợp |
| FileSet lấy cả tệp phụ trợ của hệ thống quản lý phiên bản | Default excludes đã bị tắt | Bỏ `defaultexcludes="no"` nếu không có yêu cầu đặc biệt |
| Quy tắc bị lặp ở nhiều target và dần không đồng nhất | Các mẫu được sao chép thay vì chia sẻ | Đưa nhóm mẫu chung vào PatternSet có `id` rồi tham chiếu bằng `refid` |

Khi kết quả chọn tệp không như mong đợi, hãy kiểm tra theo thứ tự: thư mục `dir`, đường dẫn tương đối thực tế, mẫu include, mẫu exclude, default excludes và tùy chọn phân biệt chữ hoa thường. Trình tự này giúp xác định đúng tầng cấu hình gây ra kết quả.

## 10. Quy trình tổ chức mẫu chọn tệp trong buildfile

Khi một dự án có nhiều target cùng xử lý mã nguồn hoặc tài nguyên, có thể tổ chức theo các bước sau:

1. Xác định nhóm tệp cần xử lý, chẳng hạn mã nguồn, tài nguyên runtime, tài liệu hoặc tệp cấu hình.
2. Viết các mẫu include đủ hẹp để mô tả đúng nhóm tệp.
3. Bổ sung exclude cho mã được sinh tự động, dữ liệu thử nghiệm hoặc tệp không được phát hành.
4. Nếu các target hoặc module dùng cùng quy tắc, khai báo `PatternSet` cấp project với `id` có ý nghĩa.
5. Tham chiếu bằng `refid` trong từng `FileSet`, để mỗi nơi chỉ cần xác định thư mục gốc riêng.
6. Chỉ chuyển danh sách mẫu sang `includesfile` hoặc `excludesfile` khi việc quản lý bên ngoài buildfile đem lại lợi ích rõ ràng.
7. Chạy target với cấu trúc thư mục đại diện và kiểm tra nội dung đầu ra, ví dụ danh sách tệp trong ZIP.

`PatternSet` giúp tách quy tắc chọn tệp khỏi vị trí chứa tệp. `FileSet` chịu trách nhiệm xác định thư mục gốc, còn `PatternSet` mô tả đường dẫn nào được giữ lại. Khi kết hợp `id` và `refid`, một quy tắc có thể được chia sẻ nhất quán giữa nhiều module và target mà không phải sao chép các mẫu include/exclude.
