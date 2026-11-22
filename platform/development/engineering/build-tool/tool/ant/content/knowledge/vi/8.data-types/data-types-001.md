# Vai trò của kiểu dữ liệu và khác biệt với task thực thi

Trong Apache Ant, build script XML gồm các target và task để mô tả quy trình build. Bên cạnh task thực thi công việc, Ant còn có **data type (kiểu dữ liệu)** để mô tả tập tin, đường dẫn, mẫu chọn file, quy tắc đổi tên hoặc cấu hình đầu vào mà task cần sử dụng.

Hai khái niệm này thường xuất hiện lồng nhau trong cùng một đoạn XML, vì vậy người mới học dễ nhầm một phần tử như `<fileset>` hoặc `<path>` là một task. Cách phân biệt cốt lõi là: **task thực hiện hành động; data type mô tả dữ liệu hoặc cấu hình để hành động đó sử dụng.**

## 1. Task và data type có vai trò khác nhau

Task là đơn vị công việc mà Ant thực thi trong target. Ví dụ:

- `<mkdir>` tạo thư mục.
- `<javac>` biên dịch mã nguồn Java.
- `<copy>` sao chép file.
- `<jar>` tạo file JAR.
- `<delete>` xóa file hoặc thư mục.
- `<echo>` ghi thông báo ra log hoặc file.

Data type mô tả dữ liệu mà task cần xử lý. Các kiểu thường gặp gồm:

- `<path>` mô tả một tập hợp đường dẫn, thường dùng làm classpath.
- `<fileset>` mô tả tập file được chọn từ một thư mục theo include/exclude.
- `<filelist>` liệt kê các file cụ thể.
- `<dirset>` mô tả tập thư mục.
- `<patternset>` gom các mẫu include/exclude để tái sử dụng.
- `<mapper>` mô tả quy tắc ánh xạ tên hoặc đường dẫn.
- `<filterset>` mô tả các phép thay thế token trong nội dung file khi task hỗ trợ.

Ví dụ ngắn:

```xml
<target name="copy-resources">
    <copy todir="build/resources">
        <fileset dir="src/main/resources">
            <include name="**/*"/>
            <exclude name="**/*.local.*"/>
        </fileset>
    </copy>
</target>
```

Trong ví dụ này, `<copy>` là task: nó thực hiện việc sao chép. `<fileset>` là data type: nó mô tả những file nào được chọn làm đầu vào. Các phần tử `<include>` và `<exclude>` cấu hình quy tắc chọn file cho fileset.

Nếu bỏ `<copy>` và chỉ giữ `<fileset>`, Ant có thông tin về tập file nhưng không có hành động sao chép nào được yêu cầu. Ngược lại, nếu có `<copy>` mà không chỉ rõ file nguồn, task không có đủ dữ liệu để biết phải sao chép những gì.

## 2. Data type không phải một bước thực thi độc lập

Task được đặt trong target để Ant gọi khi target chạy. Data type thường được khai báo bên trong task đang dùng nó, hoặc khai báo ở cấp project với một `id` để task khác tham chiếu.

Ví dụ khai báo một classpath dùng chung ở cấp project:

```xml
<project name="sample" default="compile" basedir=".">
    <path id="compile.classpath">
        <pathelement location="lib/api.jar"/>
        <fileset dir="lib">
            <include name="**/*.jar"/>
            <exclude name="*-sources.jar"/>
            <exclude name="*-javadoc.jar"/>
        </fileset>
    </path>

    <target name="compile">
        <mkdir dir="build/classes"/>
        <javac srcdir="src/main/java"
               destdir="build/classes"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>
</project>
```

`<path>` tạo một cấu trúc đường dẫn có thể tái sử dụng. `<javac>` mới là task thực hiện biên dịch. Phần `<classpath refid="compile.classpath"/>` yêu cầu task `javac` sử dụng path đã khai báo.

Không có target tên `path` để chạy. Data type không phải một lệnh build như `compile` hoặc `jar`; nó được task sử dụng khi Ant thực hiện công việc.

## 3. Cách nhận diện data type trong XML

Không thể chỉ dựa vào tên phần tử để đoán mọi thành phần XML của Ant. Cần xem phần tử đó đang được Ant định nghĩa là task, data type hay phần tử con cấu hình của một task.

Một số dấu hiệu thường gặp:

| Dấu hiệu | Data type | Task |
|---|---|---|
| Vai trò | Mô tả dữ liệu, tập tài nguyên hoặc quy tắc | Thực hiện một hành động |
| Vị trí thường thấy | Lồng trong task hoặc khai báo ở cấp project với `id` | Nằm trong target để được thực thi |
| Cách tái sử dụng | Thường dùng `id` và `refid` khi kiểu đó hỗ trợ reference | Gọi target hoặc gọi task theo cấu trúc build |
| Ví dụ | `path`, `fileset`, `patternset`, `mapper` | `javac`, `copy`, `jar`, `delete` |
| Kết quả trực tiếp | Cung cấp cấu hình hoặc tập dữ liệu cho task | Tạo, sửa, xóa, biên dịch hoặc chạy nội dung |

Các phần tử lồng bên trong data type có thể tiếp tục cấu hình data type đó. Ví dụ `<include>` và `<exclude>` không sao chép file; chúng chỉ xác định mẫu file mà `fileset` sẽ chọn.

## 4. Path: mô tả tập hợp đường dẫn

`path` là một trong những data type quan trọng nhất khi build Java. Compiler và chương trình chạy cần biết nơi tìm class hoặc thư viện. Một path có thể chứa phần tử đường dẫn đơn lẻ, thư mục class đã biên dịch hoặc tập hợp JAR.

```xml
<path id="application.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="lib/common.jar"/>
    <fileset dir="lib/third-party">
        <include name="**/*.jar"/>
    </fileset>
</path>
```

Ở đây:

- `pathelement` thêm một đường dẫn cụ thể.
- `fileset` tìm các JAR trong thư mục `lib/third-party`.
- `path` kết hợp các thành phần trên thành một cấu hình classpath.
- `id` đặt tên reference để task có thể sử dụng lại.

Task `javac` sử dụng path:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false">
    <classpath refid="application.classpath"/>
</javac>
```

Task `java` cũng có thể sử dụng cùng path khi chạy chương trình:

```xml
<java classname="com.example.App" fork="true" failonerror="true">
    <classpath refid="application.classpath"/>
</java>
```

Như vậy, data type cho phép tập trung cấu hình classpath ở một nơi và dùng lại ở nhiều task. Nếu mỗi task tự khai báo một danh sách JAR riêng, cấu hình dễ bị lệch khi dependency thay đổi.

## 5. Fileset: mô tả tập file theo mẫu

`fileset` chọn file trong một thư mục dựa trên các mẫu `include` và `exclude`. Đường dẫn trong mẫu thường được tính tương đối từ thư mục gốc của fileset.

```xml
<fileset dir="src">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
    <exclude name="**/*Test.java"/>
</fileset>
```

Mẫu `**/*.java` chọn file Java ở mọi cấp thư mục. Mẫu `**/generated/**` loại các file nằm trong cây thư mục `generated`; mẫu `**/*Test.java` loại các file test.

Một fileset có thể được dùng bởi nhiều task. Ví dụ `copy` sao chép tài nguyên:

```xml
<copy todir="build/resources">
    <fileset dir="src/main/resources">
        <include name="**/*"/>
    </fileset>
</copy>
```

Task `jar` cũng có thể lấy file từ fileset:

```xml
<jar destfile="dist/resources.jar">
    <fileset dir="build/resources">
        <include name="**/*"/>
    </fileset>
</jar>
```

Trong cả hai trường hợp, fileset chỉ chọn nguồn. Task `copy` thực hiện sao chép; task `jar` tạo archive. Cùng một kiểu dữ liệu có thể phục vụ nhiều hành động khác nhau.

## 6. Filelist và dirset: chọn file cụ thể hoặc chọn thư mục

Không phải lúc nào cũng muốn quét file theo mẫu. Ant có các data type khác để mô tả tập tài nguyên theo cách phù hợp hơn.

### 6.1. Filelist

`filelist` liệt kê các file cụ thể theo thứ tự khai báo. Nó phù hợp khi danh sách file đã biết và không cần quét toàn bộ thư mục.

```xml
<filelist id="release.notes"
          dir="docs"
          files="README.md,CHANGELOG.md,LICENSE.txt"/>
```

Task hỗ trợ nested filelist có thể dùng danh sách này để xử lý các file đã chọn. Khác với fileset, filelist không dùng include/exclude để quét mẫu file; nó mô tả danh sách file tường minh.

### 6.2. Dirset

`dirset` chọn thư mục theo mẫu:

```xml
<dirset dir="modules">
    <include name="*/src/main"/>
    <exclude name="legacy/**"/>
</dirset>
```

Dirset hữu ích khi task cần làm việc với tập thư mục. Nếu mục tiêu là chọn các file bên trong thư mục, fileset thường phù hợp hơn.

## 7. Patternset: tái sử dụng quy tắc include và exclude

Khi nhiều fileset cần cùng quy tắc chọn file, có thể định nghĩa `patternset` một lần:

```xml
<patternset id="production.resources">
    <include name="**/*.properties"/>
    <include name="**/*.xml"/>
    <exclude name="**/*.local.properties"/>
    <exclude name="**/sample/**"/>
</patternset>
```

Sau đó tham chiếu patternset trong fileset:

```xml
<fileset dir="src/main/resources">
    <patternset refid="production.resources"/>
</fileset>
```

Patternset chỉ mô tả mẫu lựa chọn. Nó không tìm và sao chép file độc lập. Fileset sử dụng mẫu đó để tạo tập file, còn task như `copy` hoặc `jar` thực hiện công việc trên tập file được chọn.

Tái sử dụng patternset giúp quy tắc đóng gói nhất quán. Ví dụ, nếu cần loại file cấu hình cục bộ khỏi cả thư mục copy và JAR, có thể tham chiếu cùng patternset ở cả hai nơi.

## 8. Mapper: mô tả quy tắc đổi tên đường dẫn

Một số task cần ánh xạ tên file nguồn sang tên file đích. `mapper` mô tả quy tắc ánh xạ đó; task thực hiện copy hoặc xử lý file sẽ sử dụng quy tắc.

Ví dụ dùng glob mapper để đổi phần mở rộng từ `.txt` sang `.bak` khi copy:

```xml
<copy todir="build/backup">
    <fileset dir="docs">
        <include name="*.txt"/>
    </fileset>
    <mapper type="glob" from="*.txt" to="*.bak"/>
</copy>
```

Với file nguồn `docs/guide.txt`, task copy tạo file đích `build/backup/guide.bak`. Mapper không tự đổi tên file khi đứng riêng; nó chỉ cung cấp quy tắc cho task có hỗ trợ mapper.

Mapper có nhiều kiểu như `glob`, `regexp`, `identity`, `flatten` hoặc `merge`. Mỗi kiểu phục vụ cách biến đổi tên khác nhau. Hãy chọn kiểu đơn giản nhất diễn đạt được quy tắc cần dùng và kiểm tra đường dẫn đích để tránh nhiều file nguồn ánh xạ vào cùng một tên.

## 9. Filterset: mô tả phép thay token trong nội dung file

`filterset` định nghĩa các cặp token và giá trị thay thế. Khi task hỗ trợ filtering, data type này cho biết nội dung file cần được biến đổi như thế nào.

Ví dụ file nguồn `config/app.properties`:

```properties
app.name=Catalog
app.environment=@APP_ENV@
```

Task copy có thể thay token trong lúc sao chép:

```xml
<property name="environment" value="development"/>

<copy file="config/app.properties"
      tofile="build/config/app.properties">
    <filterset>
        <filter token="APP_ENV" value="${environment}"/>
    </filterset>
</copy>
```

File đích sẽ có nội dung `app.environment=development`. `<filterset>` mô tả token và giá trị thay thế; `<copy>` là task đọc file nguồn, áp dụng filter và ghi file đích.

Chỉ dùng filtering với file văn bản có định dạng phù hợp. Nếu áp dụng filter cho file nhị phân như ảnh hoặc JAR, nội dung có thể bị hỏng. Cũng cần tránh ghi bí mật vào file đầu ra hoặc log khi thay token từ property nhạy cảm.

## 10. Kết hợp nhiều data type trong một task

Một task có thể nhận nhiều data type để xác định nguồn, bộ lọc và quy tắc đổi tên. Ví dụ:

```xml
<target name="prepare-distribution">
    <property name="environment" value="production"/>

    <copy todir="dist/config">
        <fileset dir="src/main/resources">
            <patternset>
                <include name="**/*.properties"/>
                <exclude name="**/*.local.properties"/>
            </patternset>
        </fileset>
        <filterset>
            <filter token="APP_ENV" value="${environment}"/>
        </filterset>
    </copy>
</target>
```

Trong ví dụ này:

1. `fileset` chọn file trong thư mục resource.
2. `patternset` giới hạn file properties và loại cấu hình local.
3. `filterset` mô tả token cần thay thế.
4. `copy` thực hiện việc sao chép và áp dụng filtering.

Lưu ý về property: Ant property là bất biến. Nếu `environment` đã được đặt từ command line hoặc file cấu hình trước đó, khai báo mặc định bên trong target sẽ không ghi đè giá trị đã có. Trong dự án thật, hãy đặt default ở cấp project và truyền giá trị môi trường qua cấu hình build có chủ đích.

## 11. Tái sử dụng data type bằng id và refid

Một data type có thể được đặt tên bằng `id` khi kiểu đó hỗ trợ reference. Task khác dùng `refid` để tham chiếu cùng cấu hình thay vì khai báo lặp lại.

Ví dụ kết hợp patternset và fileset:

```xml
<project name="reuse-types" default="package" basedir=".">
    <patternset id="app.files">
        <include name="**/*.class"/>
        <include name="**/*.properties"/>
        <exclude name="**/*Test.class"/>
    </patternset>

    <fileset id="package.files" dir="build/classes">
        <patternset refid="app.files"/>
    </fileset>

    <target name="package">
        <jar destfile="dist/app.jar">
            <fileset refid="package.files"/>
        </jar>
    </target>
</project>
```

`app.files` là quy tắc chọn file. `package.files` kết hợp quy tắc đó với thư mục gốc `build/classes`. Task `jar` tham chiếu fileset để biết những file nào được đưa vào archive.

Không phải mọi phần tử XML đều chấp nhận `id` hoặc `refid`. Chỉ dùng hai thuộc tính này khi data type hoặc task được tài liệu Ant xác nhận hỗ trợ. Một reference cần có kiểu tương thích với vị trí sử dụng; không thể lấy một `fileset` thay cho một `path` chỉ vì cả hai đều mô tả file.

## 12. Task và data type có thể lồng nhau nhiều cấp

Trong Ant, một task có thể chứa data type; data type lại có thể chứa các thành phần cấu hình khác. Cấu trúc XML thể hiện quan hệ dữ liệu đó.

```xml
<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath>
            <pathelement location="build/classes"/>
            <fileset dir="lib">
                <include name="**/*.jar"/>
            </fileset>
        </classpath>
    </javac>
</target>
```

Đọc từ ngoài vào trong:

- `<target>` xác định một nhóm công việc có tên `compile`.
- `<javac>` là task thực thi compiler.
- `<classpath>` mô tả classpath mà compiler sử dụng.
- `<pathelement>` thêm một vị trí cụ thể vào path.
- `<fileset>` chọn các JAR trong thư mục `lib`.
- `<include>` xác định mẫu file được chọn.

Chỉ task `javac` thực hiện biên dịch. Các phần tử còn lại cung cấp dữ liệu và cấu hình cho task đó.

## 13. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `fileset` tự sao chép file | Fileset chỉ chọn file; task như `copy` mới sao chép |
| `path` tự biên dịch Java | Path mô tả classpath; `javac` mới biên dịch |
| `patternset` là một target | Patternset là data type mô tả include/exclude |
| `mapper` tự đổi tên file | Mapper mô tả ánh xạ; task hỗ trợ mapper thực hiện thao tác file |
| Có `id` nghĩa là một task sẽ chạy | `id` đặt tên reference; nó không kích hoạt hành động |
| Có data type trong build.xml thì Ant tự xử lý dữ liệu ngay | Task sử dụng data type khi target chạy; định nghĩa type tự nó không phải thao tác build |
| Mọi data type đều dùng được ở mọi task | Mỗi task chỉ hỗ trợ một số kiểu lồng và cấu trúc nhất định |

Khi đọc tài liệu Ant, hãy kiểm tra phần mô tả task để biết task nhận những nested element nào. Không phải cứ một data type tồn tại trong Ant là có thể đặt nó tùy ý bên trong mọi task.

## 14. Bài tập thực hành

Tạo dự án Java nhỏ với thư mục `src/main/java`, `src/main/resources`, `lib`, `build/classes` và `dist`.

1. Khai báo một `path` có `id="compile.classpath"`, thêm thư mục class và các JAR trong `lib`.
2. Dùng `javac` với nested `classpath` tham chiếu bằng `refid` để biên dịch source.
3. Dùng `fileset` để chọn resource, sau đó dùng task `copy` đưa chúng vào `build/resources`.
4. Tạo một `patternset` để loại file `*.local.properties` và tham chiếu nó trong fileset.
5. Tạo một `filterset` thay token `APP_ENV` khi copy file cấu hình.
6. Dùng `mapper` để đổi tên file văn bản trong một bước copy riêng.
7. Dùng task `jar` để đóng gói class và resource đã chọn.
8. Giải thích trong từng đoạn XML phần tử nào là task và phần tử nào là data type.

Sau khi hoàn thành, người học cần đọc được cấu trúc XML lồng nhau và trả lời được ba câu hỏi: task nào thực sự thực hiện công việc, data type nào cung cấp đầu vào, và reference nào giúp tái sử dụng cấu hình.

## 15. Cách tư duy khi thiết kế build script

Khi viết một target mới, trước hết hãy xác định hành động cần thực hiện: biên dịch, sao chép, đóng gói, xóa hay chạy chương trình. Chọn task tương ứng làm phần thực thi. Sau đó xác định dữ liệu mà task cần: đường dẫn, tập file, mẫu chọn, quy tắc đổi tên hoặc bộ token thay thế. Dùng data type phù hợp để mô tả những dữ liệu đó.

Nếu nhiều task cần cùng một cấu hình, cân nhắc đặt data type ở cấp project với `id` rồi tham chiếu bằng `refid`. Nếu cấu hình chỉ có ý nghĩa ở một vị trí, khai báo lồng ngay trong task giúp người đọc thấy rõ đầu vào tại chỗ.

Tách rõ hai vai trò giúp `build.xml` dễ đọc và bảo trì: target mô tả luồng công việc, task thực hiện hành động, còn data type mô tả dữ liệu và quy tắc mà hành động cần dùng.
