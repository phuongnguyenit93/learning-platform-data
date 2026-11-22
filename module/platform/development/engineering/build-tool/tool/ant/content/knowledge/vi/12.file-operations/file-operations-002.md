# Sao chép bằng `copy` với `FileSet` và tập tài nguyên trong Apache Ant

Apache Ant cung cấp task `copy` để sao chép file và tài nguyên từ nguồn đến một file đích hoặc một thư mục đích. Khi cần sao chép nhiều file, buildfile thường mô tả tập nguồn bằng `FileSet` hoặc một ResourceCollection khác. Cách làm này giúp chọn file theo thư mục, mẫu tên, quy tắc include/exclude và kết hợp nhiều nguồn ngay trong buildfile.

`copy` thực hiện thao tác sao chép; `FileSet` và các ResourceCollection mô tả những tài nguyên nào được đưa vào thao tác đó. Phân biệt hai trách nhiệm này giúp buildfile dễ đọc: phần chọn nguồn nằm trong collection, còn phần đích và tùy chọn sao chép nằm ở task.

## 1. Hai cách sử dụng cơ bản của `copy`

### Sao chép một file cụ thể

Khi nguồn chỉ có một file và muốn đặt tên đích cụ thể, dùng `file` cùng `tofile`:

```xml
<target name="copy-readme">
    <mkdir dir="build/docs"/>
    <copy file="README.md"
          tofile="build/docs/PROJECT-README.md"
          overwrite="true"/>
</target>
```

`file` xác định một file nguồn, còn `tofile` xác định đầy đủ đường dẫn và tên file đích. Cặp thuộc tính này phù hợp khi chỉ sao chép một file. Nếu nguồn là nhiều file, hãy dùng `todir` và một FileSet hoặc ResourceCollection.

### Sao chép nhiều file vào thư mục

Khi có nhiều file, dùng `todir` làm thư mục đích và đặt các collection nguồn bên trong task:

```xml
<target name="copy-config">
    <mkdir dir="build/config"/>
    <copy todir="build/config">
        <fileset dir="src/main/config">
            <include name="**/*.properties"/>
            <include name="**/*.xml"/>
            <exclude name="**/local/**"/>
        </fileset>
    </copy>
</target>
```

Ant quét thư mục `src/main/config`, chọn file `.properties` và `.xml`, loại các file nằm dưới đường dẫn `local`, sau đó sao chép vào `build/config`. Cấu trúc thư mục tương đối bên dưới thư mục gốc của FileSet được giữ lại theo mặc định.

Ví dụ, nếu nguồn có:

```text
src/main/config/
├── app.properties
├── database/
│   └── connection.xml
└── local/
    └── developer.properties
```

thì kết quả có dạng:

```text
build/config/
├── app.properties
└── database/
    └── connection.xml
```

File `developer.properties` không được sao chép vì khớp quy tắc exclude.

## 2. Chọn file bằng `FileSet`

`FileSet` biểu diễn các file nằm dưới một thư mục gốc. Thuộc tính `dir` xác định thư mục bắt đầu; các phần tử `include` và `exclude` giới hạn tập file được chọn.

```xml
<fileset dir="src/main/resources">
    <include name="**/*.yml"/>
    <include name="**/*.yaml"/>
    <exclude name="**/application-local.*"/>
    <exclude name="**/samples/**"/>
</fileset>
```

Các pattern được viết tương đối với `dir` của FileSet:

| Pattern | Ý nghĩa |
|---|---|
| `*.properties` | File properties ở ngay thư mục gốc của FileSet |
| `**/*.properties` | File properties ở thư mục gốc hoặc các thư mục con |
| `config/**` | Nội dung nằm dưới thư mục `config` |
| `**/test-*.xml` | File XML có tên bắt đầu bằng `test-` ở các cấp thư mục |
| `**/*.local` | File có phần mở rộng `.local` ở mọi cấp |

Có thể viết include/exclude trực tiếp trên `fileset` khi biểu thức ngắn:

```xml
<fileset dir="src/main/resources"
         includes="**/*.properties,**/*.yml"
         excludes="**/application-local.*,**/samples/**"/>
```

Với nhiều quy tắc, dạng phần tử con thường dễ đọc và dễ thêm chú thích hơn. Nếu muốn hiểu chính xác cú pháp pattern, hãy nhớ rằng `*` khớp một phần tên trong một cấp đường dẫn, còn `**` cho phép đi qua nhiều cấp thư mục.

### FileSet và thư mục nguồn

`FileSet` chọn file bên trong thư mục được chỉ định; bản thân thư mục gốc không được copy như một thư mục bao ngoài. Khi dùng `copy todir`, Ant tạo đường dẫn đích dựa trên đường dẫn tương đối của file trong FileSet. Điều này giúp nội dung thư mục nguồn được đặt trực tiếp dưới `todir`.

Nếu cần copy nhiều thư mục nguồn, hãy khai báo nhiều `fileset` trong cùng một task `copy` hoặc kết hợp chúng bằng ResourceCollection phù hợp.

## 3. Sao chép từ nhiều FileSet hoặc ResourceCollection

Task `copy` có thể nhận nhiều ResourceCollection. Ví dụ, có thể gom tài nguyên cấu hình và tài nguyên được sinh tự động vào cùng thư mục staging:

```xml
<target name="stage-resources">
    <mkdir dir="build/stage"/>
    <copy todir="build/stage">
        <fileset dir="src/main/resources">
            <exclude name="**/*.local"/>
        </fileset>
        <fileset dir="build/generated-resources"/>
    </copy>
</target>
```

Ở đây, hai FileSet là hai nguồn độc lập. Task `copy` xử lý tài nguyên từ cả hai collection. Nếu nhiều nguồn có file cùng đường dẫn tương đối, chúng có thể cùng nhắm đến một đường dẫn đích. Cần thiết kế cấu trúc nguồn hoặc quy tắc đổi tên để tránh ghi đè ngoài ý muốn.

### Dùng `union` để đặt tên tập nguồn dùng chung

Khi nhiều target cần cùng một tập file, khai báo collection với `id` rồi tham chiếu lại:

```xml
<union id="application.resources">
    <fileset dir="src/main/resources">
        <exclude name="**/*.local"/>
    </fileset>
    <fileset dir="build/generated-resources"/>
</union>

<target name="stage-resources">
    <copy todir="build/stage">
        <union refid="application.resources"/>
    </copy>
</target>

<target name="backup-resources">
    <copy todir="build/backup">
        <union refid="application.resources"/>
    </copy>
</target>
```

`id` đặt tên cho ResourceCollection; `refid` dùng lại collection ở vị trí mà task hỗ trợ. `union` kết hợp các tập nguồn thành một collection. Các phép toán ResourceCollection như `union`, `intersect` và `difference` được giải thích riêng ở bài học về kết hợp tập tài nguyên.

## 4. Cấu trúc thư mục đích và `flatten`

Mặc định, khi copy FileSet vào một thư mục, Ant giữ đường dẫn tương đối từ thư mục gốc của FileSet. Đây thường là lựa chọn an toàn nhất vì nó giữ cấu trúc và tránh xung đột tên file.

Ví dụ:

```xml
<copy todir="build/config">
    <fileset dir="src/config"/>
</copy>
```

Nguồn `src/config/database/connection.xml` sẽ được đặt tại `build/config/database/connection.xml`.

Nếu muốn bỏ cấu trúc thư mục và chỉ giữ tên file, có thể dùng `flatten="true"`:

```xml
<copy todir="build/lib" flatten="true">
    <fileset dir="dependencies">
        <include name="**/*.jar"/>
    </fileset>
</copy>
```

Ví dụ này đưa các JAR từ mọi thư mục con của `dependencies` trực tiếp vào `build/lib`. Hãy cẩn thận: hai thư mục nguồn có thể chứa các file cùng tên như `common.jar`. Khi flatten, chúng cùng nhắm đến `build/lib/common.jar`; kết quả có thể phụ thuộc thứ tự xử lý và cấu hình ghi đè. Nếu cần giữ cả hai file, hãy giữ cấu trúc thư mục hoặc dùng mapper để tạo tên đích duy nhất.

## 5. Đổi tên file khi sao chép bằng mapper

Khi cần kiểm soát tên đích, có thể dùng nested `mapper`. Ví dụ, đổi phần mở rộng `.template` thành `.properties` khi copy:

```xml
<copy todir="build/config">
    <fileset dir="src/config">
        <include name="**/*.template"/>
    </fileset>
    <globmapper from="*.template" to="*.properties"/>
</copy>
```

Mapper ánh xạ tên đường dẫn nguồn sang tên đường dẫn đích. Hãy kiểm tra pattern mapper có phù hợp với đường dẫn tương đối do collection cung cấp hay không. Nếu mapper tạo nhiều tên đích cho một nguồn hoặc nhiều nguồn cùng ánh xạ đến một đích, cần xác định rõ hành vi mong muốn.

`flatten="true"` là cách đơn giản để bỏ đường dẫn thư mục; mapper phù hợp hơn khi cần quy tắc đổi tên có chủ đích. Không nên dùng cả hai nếu chưa hiểu cách task áp dụng mapper và flatten trong cấu hình cụ thể.

## 6. Điều khiển thời điểm và cách ghi file

Task `copy` có các thuộc tính giúp quyết định khi nào file được sao chép và metadata nào được giữ lại.

| Thuộc tính | Tác dụng |
|---|---|
| `overwrite` | Khi `true`, ghi đè file đích ngay cả khi file đích không cũ hơn nguồn; mặc định là `false` |
| `preserveLastModified` | Giữ thời điểm sửa đổi cuối của file nguồn trên file đích |
| `flatten` | Bỏ cấu trúc thư mục tương đối khi tạo đường dẫn đích |
| `includeEmptyDirs` | Có đưa các thư mục rỗng từ FileSet vào đích hay không |
| `failonerror` | Có làm build thất bại khi xảy ra lỗi copy hay không; mặc định là `true` |
| `verbose` | In chi tiết file được xử lý trong log |

Ví dụ chỉ copy khi cần cập nhật và giữ timestamp của nguồn:

```xml
<copy todir="build/resources"
      overwrite="false"
      preserveLastModified="true">
    <fileset dir="src/main/resources"/>
</copy>
```

Khi `overwrite` là `false`, Ant thông thường chỉ copy nếu file đích chưa tồn tại hoặc file nguồn mới hơn file đích (có xét độ phân giải timestamp của filesystem). Khi `overwrite` là `true`, Ant copy bất kể so sánh thời gian. `preserveLastModified` điều khiển timestamp trên file đích sau khi copy.

Không nên bật `overwrite="true"` theo thói quen cho mọi task. Hãy chọn theo mục tiêu: cập nhật file đã thay đổi, tái tạo staging hoặc cố ý thay thế đầu ra.

## 7. Filtering nội dung file

Trong một số build, file cấu hình chứa token cần thay bằng giá trị của môi trường hoặc ứng dụng. `copy` hỗ trợ `filterset` để thay token trong nội dung file khi sao chép.

Ví dụ file nguồn `src/config/app.properties`:

```properties
app.name=@app.name@
app.environment=@app.environment@
```

Buildfile:

```xml
<property name="app.name" value="inventory-service"/>
<property name="app.environment" value="staging"/>

<copy file="src/config/app.properties"
      tofile="build/config/app.properties">
    <filterset>
        <filter token="app.name" value="${app.name}"/>
        <filter token="app.environment" value="${app.environment}"/>
    </filterset>
</copy>
```

Kết quả trong file đích là:

```properties
app.name=inventory-service
app.environment=staging
```

Filtering làm thay đổi nội dung file. Chỉ dùng với file văn bản có encoding và token đã biết. Không bật filtering cho JAR, ảnh, PDF hoặc dữ liệu nhị phân vì thay thế byte có thể làm hỏng file. Nếu cần chỉ định encoding khi filter, cấu hình encoding phù hợp với cách file nguồn được mã hóa và phiên bản Ant đang sử dụng.

## 8. Sao chép ResourceCollection không chỉ là FileSet

`FileSet` là nguồn thường gặp nhất, nhưng task `copy` có thể tiêu thụ những ResourceCollection tương thích khác. Ví dụ, `zipfileset` chọn tài nguyên nằm trong một file ZIP:

```xml
<copy todir="build/unpacked-config">
    <zipfileset src="distribution/config-bundle.zip"
                includes="**/*.xml"/>
</copy>
```

Ví dụ này sao chép các tài nguyên XML được chọn trong ZIP vào thư mục đích. Các collection không phải file thông thường có thể có đặc điểm về tên, đường dẫn và timestamp khác với FileSet; hãy kiểm tra tài liệu task và kiểu resource cụ thể.

Khi một task cần duyệt tài nguyên từ nhiều định dạng, ResourceCollection giúp giữ phần chọn dữ liệu tách khỏi thao tác copy. Tuy nhiên, task vẫn phải hỗ trợ collection đó và tài nguyên phải cung cấp nội dung có thể đọc được.

## 9. Ví dụ buildfile hoàn chỉnh

Giả sử dự án có cấu trúc:

```text
project/
├── build.xml
├── src/main/resources/
│   ├── app.properties
│   ├── logback.xml
│   └── local/
│       └── developer.properties
└── config/generated/
    └── build-info.properties
```

Buildfile sau copy tài nguyên cấu hình, loại cấu hình local, thêm file sinh tự động và thay token trong file thuộc diện filtering:

```xml
<project name="copy-demo" default="copy-resources" basedir=".">

    <property name="resources.dir" location="src/main/resources"/>
    <property name="generated.dir" location="config/generated"/>
    <property name="build.dir" location="build"/>
    <property name="output.dir" location="${build.dir}/resources"/>
    <property name="app.environment" value="development"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="copy-resources">
        <mkdir dir="${output.dir}"/>

        <copy todir="${output.dir}"
              preserveLastModified="true">
            <fileset dir="${resources.dir}">
                <exclude name="local/**"/>
                <exclude name="app.properties"/>
            </fileset>
            <fileset dir="${generated.dir}"/>
        </copy>

        <copy file="${resources.dir}/app.properties"
              tofile="${output.dir}/app.properties"
              overwrite="true">
            <filterset>
                <filter token="app.environment"
                        value="${app.environment}"/>
            </filterset>
        </copy>
    </target>

</project>
```

Trong ví dụ, bước copy đầu tiên giữ cấu trúc thư mục tương đối, loại nội dung dưới `local/` và loại `app.properties` để file này không bị copy trước khi filtering. Bước thứ hai copy riêng `app.properties` với filterset để thay token. Cách tách này giúp mỗi file chỉ đi qua đúng một quy trình xử lý.

## 10. Các lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không có file nào được copy | Pattern include không khớp, `dir` sai hoặc nguồn không tồn tại | Kiểm tra đường dẫn gốc và pattern tương đối với `dir` |
| File đích nằm sai thư mục | Nhầm `tofile` với `todir` hoặc hiểu sai cấu trúc tương đối | Dùng `tofile` cho một file có tên đích cụ thể; dùng `todir` cho collection |
| File ở thư mục con bị dồn vào cùng chỗ | Đặt `flatten="true"` | Bỏ flatten hoặc cấu hình mapper giữ đường dẫn mong muốn |
| Một file bị ghi đè bởi file khác cùng tên | Nhiều nguồn ánh xạ đến cùng đường dẫn đích | Giữ cấu trúc thư mục, đổi tên bằng mapper hoặc staging riêng |
| File cấu hình không được thay token | Filterset không khớp token hoặc file không đi qua bước filtering | Kiểm tra dấu token, filterset và đường copy thực tế |
| File nhị phân bị hỏng | Filtering áp dụng lên nội dung nhị phân | Chỉ filter file văn bản; copy binary mà không thay nội dung |
| File đích không được cập nhật | File đích mới hơn nguồn và overwrite đang là false | Kiểm tra timestamp hoặc bật overwrite nếu muốn thay thế luôn |
| Build tiếp tục dù copy lỗi | Đã cấu hình `failonerror="false"` hoặc task khác xử lý lỗi | Giữ failonerror mặc định hoặc đặt true khi lỗi copy phải làm build thất bại |
| File đã bị xóa khỏi nguồn nhưng vẫn còn ở đích | `copy` không xóa file đích dư thừa | Dùng cơ chế đồng bộ/mirror phù hợp nếu cần xóa phần dư |

`copy` là thao tác bổ sung hoặc cập nhật file đích; nó không tự làm cho thư mục đích trở thành bản sao phản chiếu chính xác của nguồn. Nếu một file đã bị xóa khỏi nguồn, file cũ ở đích có thể vẫn còn. Hãy chọn task đồng bộ phù hợp khi yêu cầu là mirror cả việc thêm, cập nhật và xóa.

## 11. Quy tắc tổ chức buildfile

- Dùng `file` + `tofile` cho một file nguồn với tên đích cụ thể; dùng `todir` với FileSet/ResourceCollection cho nhiều file.
- Đặt `dir` của FileSet rõ ràng và viết include/exclude theo đường dẫn tương đối với thư mục đó.
- Giữ cấu trúc thư mục mặc định trừ khi có yêu cầu rõ ràng phải flatten hoặc đổi tên.
- Tách collection nguồn theo mục đích như `main.resources`, `generated.resources`, `release.resources` để dễ hiểu và tái sử dụng.
- Kiểm tra trùng tên đích khi copy nhiều nguồn hoặc bật flatten.
- Chỉ dùng filterset cho nội dung văn bản; giữ nguyên nội dung nhị phân.
- Chọn `overwrite` và `preserveLastModified` theo chính sách cập nhật đầu ra.
- Không coi `copy` là công cụ mirror; xử lý file dư ở đích bằng một bước đồng bộ riêng khi cần.
- Giữ `failonerror` bật khi copy là điều kiện bắt buộc để build thành công.

## 12. Bài tập tự kiểm tra

**Bài 1.** Muốn copy tất cả file XML từ `src/data` vào `build/data` và giữ cấu trúc thư mục con, hãy viết task như thế nào?

**Đáp án:**

```xml
<copy todir="build/data">
    <fileset dir="src/data" includes="**/*.xml"/>
</copy>
```

**Bài 2.** `flatten="true"` có tác dụng gì và rủi ro chính là gì?

**Đáp án:** Nó bỏ các thư mục tương đối, đưa file về trực tiếp dưới thư mục đích. Các file cùng tên từ nhiều thư mục nguồn có thể ghi đè nhau.

**Bài 3.** Khi nào dùng `file`/`tofile`, khi nào dùng `todir`?

**Đáp án:** Dùng `file` và `tofile` để copy một file đến một đường dẫn/tên đích cụ thể. Dùng `todir` khi copy một hoặc nhiều ResourceCollection vào thư mục đích.

**Bài 4.** Vì sao không nên áp dụng filterset cho JAR hoặc ảnh?

**Đáp án:** Filter thay thế token trong nội dung byte của file. Dữ liệu nhị phân không phải văn bản token và có thể bị thay đổi làm hỏng định dạng.

**Bài 5.** Sau khi copy, một file cũ vẫn tồn tại ở thư mục đích dù đã bị xóa khỏi nguồn. Vì sao?

**Đáp án:** `copy` không xóa file đích không còn trong tập nguồn. Cần dùng một bước đồng bộ/mirror có chính sách xóa phần dư nếu đó là yêu cầu.

## Kết luận

Task `copy` kết hợp với `FileSet` và ResourceCollection tạo nên cách sao chép tài nguyên linh hoạt trong Apache Ant. FileSet chọn nguồn bằng thư mục gốc và pattern; ResourceCollection có thể gom nhiều tập; `copy` quyết định nơi ghi, cấu trúc đường dẫn, overwrite, timestamp và filtering. Khi kiểm soát được đường dẫn tương đối, va chạm tên, loại nội dung và chính sách cập nhật, quy trình sao chép sẽ ổn định giữa máy phát triển và CI.

