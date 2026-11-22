# Tham chiếu đối tượng bằng `id` và `refid` trong Apache Ant

Trong Apache Ant, một buildfile thường cần dùng lại cùng một cấu hình ở nhiều task. Ví dụ, nhiều task có thể cần chung classpath; nhiều `fileset` có thể cần cùng bộ quy tắc include/exclude; hoặc nhiều bước đóng gói có thể cần cùng một tập tài nguyên. Nếu lặp lại toàn bộ cấu hình ở từng nơi, buildfile sẽ dài hơn và các bản sao dễ lệch nhau khi dự án thay đổi.

Ant giải quyết việc này bằng cơ chế tham chiếu đối tượng. Thuộc tính `id` đặt tên cho một đối tượng dữ liệu để các phần khác của buildfile có thể tìm lại. Thuộc tính `refid` chỉ đến đối tượng đã được đặt tên đó. Hai thuộc tính thường xuất hiện cùng nhau, nhưng chúng làm hai việc khác nhau:

- `id`: khai báo tên tham chiếu cho một đối tượng dữ liệu.
- `refid`: sử dụng tên đó để tham chiếu lại đối tượng.

## 1. Vì sao cần tham chiếu đối tượng?

Giả sử task biên dịch và task chạy ứng dụng đều cần các thư viện trong thư mục `lib`. Nếu khai báo classpath riêng ở từng task, hai cấu hình có thể dần khác nhau: task biên dịch đã có thư viện mới nhưng task chạy vẫn thiếu thư viện đó. Khai báo một `path` có `id`, sau đó dùng `refid` ở các task cần thiết, giúp giữ một định nghĩa dùng chung.

Ví dụ dưới đây khai báo classpath một lần rồi dùng lại trong task `javac`:

```xml
<project name="ant-reference-demo" default="compile">
    <property name="src.dir" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="lib.dir" location="lib"/>

    <path id="compile.classpath">
        <pathelement location="${lib.dir}/commons-lang3.jar"/>
        <pathelement location="${lib.dir}/jackson-databind.jar"/>
    </path>

    <target name="compile">
        <mkdir dir="${build.dir}/classes"/>
        <javac srcdir="${src.dir}"
               destdir="${build.dir}/classes"
               includeantruntime="false">
            <classpath refid="compile.classpath"/>
        </javac>
    </target>
</project>
```

Trong ví dụ:

1. Phần tử `<path>` tạo một đối tượng đường dẫn gồm hai file JAR.
2. `id="compile.classpath"` đăng ký đối tượng đó với tên `compile.classpath` trong project Ant hiện tại.
3. Phần tử `<classpath refid="compile.classpath"/>` yêu cầu `javac` sử dụng lại path đã khai báo.
4. Khi cần thêm hoặc bỏ một thư viện, ta sửa định nghĩa `compile.classpath` tại một nơi.

`compile.classpath` là tên tham chiếu do buildfile đặt ra. Dấu chấm trong tên chỉ giúp tên dễ đọc; nó không phải cú pháp truy cập thuộc tính hay tên package Java.

## 2. Phân biệt `id`, `refid` và property `${...}`

Người mới học Ant dễ nhầm tham chiếu đối tượng với property. Cả hai đều giúp tránh lặp lại, nhưng chúng đại diện cho hai loại dữ liệu khác nhau.

| Cú pháp | Vai trò | Ví dụ |
|---|---|---|
| `id="compile.classpath"` | Đặt tên tham chiếu cho đối tượng dữ liệu | `<path id="compile.classpath">...</path>` |
| `refid="compile.classpath"` | Lấy lại đối tượng đã được đăng ký | `<classpath refid="compile.classpath"/>` |
| `${lib.dir}` | Thay property bằng giá trị dạng văn bản của property | `<pathelement location="${lib.dir}/app.jar"/>` |

Property phù hợp với giá trị như thư mục, tên môi trường, phiên bản hoặc chuỗi cấu hình. `id` và `refid` phù hợp với các kiểu dữ liệu Ant như `path`, `fileset` và `patternset`.

Ví dụ, dòng sau mở rộng property `lib.dir` thành một đường dẫn:

```xml
<property name="lib.dir" location="lib"/>
<pathelement location="${lib.dir}/app.jar"/>
```

Còn đoạn sau tham chiếu đến một đối tượng `path` đã được khai báo:

```xml
<path id="app.classpath">
    <pathelement location="lib/app.jar"/>
</path>

<javac srcdir="src" destdir="build/classes">
    <classpath refid="app.classpath"/>
</javac>
```

Không thể thay `refid` bằng `${app.classpath}` chỉ vì hai tên trông giống nhau. Property và reference được lưu trữ, tra cứu theo hai cơ chế khác nhau.

## 3. Cách Ant quản lý reference

Khi một data type được khai báo với `id`, Ant đăng ký đối tượng đó trong bảng reference của `Project` đang thực thi buildfile. Khi gặp `refid`, Ant tra cứu tên trong bảng này và cung cấp đối tượng cho phần tử đang sử dụng.

```mermaid
flowchart LR
    A["Khai báo data type với id"] --> B["Ant đăng ký reference trong Project"]
    B --> C["Phần tử khác dùng refid"]
    C --> D["Task nhận đối tượng dữ liệu đã khai báo"]
```

Một số hệ quả quan trọng:

- Reference thuộc về ngữ cảnh `Project` Ant hiện tại. Đừng xem `id` như tên toàn cục có thể tự động dùng trong mọi lần chạy Ant hoặc mọi project lồng nhau.
- Tên reference phải nhất quán. Ant phân biệt các chuỗi tên; `compile.classpath` và `Compile.classpath` không nên được xem là cùng một tên.
- Mỗi `id` nên có tên duy nhất trong project. Nếu cùng một tên được đăng ký nhiều lần, reference có thể bị ghi đè hoặc Ant phát cảnh báo; hãy tránh tình huống này.
- Nên đặt khai báo data type trước các nơi sử dụng để buildfile dễ đọc và dễ lần theo nguồn của reference.
- Reference giữ nguyên kiểu dữ liệu của đối tượng. `refid` không biến một `fileset` thành `path` hay ngược lại.

## 4. Tái sử dụng `path` ở nhiều task

`path` là một trong những data type được tham chiếu thường xuyên nhất. Nó biểu diễn một chuỗi đường dẫn mà các task như `javac`, `java` hoặc các task khác có thể nhận làm classpath.

Có thể tạo một path chạy ứng dụng dựa trên path biên dịch:

```xml
<property name="build.dir" location="build"/>
<property name="lib.dir" location="lib"/>

<path id="compile.classpath">
    <pathelement location="${lib.dir}/commons-lang3.jar"/>
    <pathelement location="${lib.dir}/jackson-databind.jar"/>
</path>

<path id="runtime.classpath">
    <pathelement location="${build.dir}/classes"/>
    <path refid="compile.classpath"/>
</path>

<target name="run">
    <java classname="com.example.Main" fork="true">
        <classpath refid="runtime.classpath"/>
    </java>
</target>
```

Ở đây, `runtime.classpath` gồm thư mục chứa class đã biên dịch và toàn bộ phần tử trong `compile.classpath`. Phần tử `<path refid="compile.classpath"/>` lồng bên trong một `path` khác giúp ghép một path đã có vào path mới.

Có thể dùng cùng một reference trong nhiều task nếu các vị trí đó chấp nhận kiểu dữ liệu tương ứng. Chẳng hạn, `javac` và `java` đều có thể nhận một classpath. Tuy nhiên, một reference chỉ dùng được ở nơi hỗ trợ kiểu dữ liệu đó; không phải mọi task đều nhận mọi loại reference.

## 5. Tái sử dụng `patternset` và `fileset`

`patternset` gom các quy tắc chọn hoặc loại file. Khi nhiều `fileset` cần cùng quy tắc, ta có thể đặt `id` cho `patternset` rồi dùng `refid` để áp dụng lại.

```xml
<property name="src.dir" location="src"/>
<property name="dist.dir" location="dist"/>

<patternset id="java.source.patterns">
    <include name="**/*.java"/>
    <exclude name="**/generated/**"/>
</patternset>

<target name="copy-main-sources">
    <copy todir="${dist.dir}/main-sources">
        <fileset dir="${src.dir}/main">
            <patternset refid="java.source.patterns"/>
        </fileset>
    </copy>
</target>

<target name="copy-test-sources">
    <copy todir="${dist.dir}/test-sources">
        <fileset dir="${src.dir}/test">
            <patternset refid="java.source.patterns"/>
        </fileset>
    </copy>
</target>
```

Cả hai `fileset` đều dùng cùng bộ lọc: lấy file Java và bỏ qua thư mục `generated`. Thư mục gốc vẫn được chỉ định riêng ở từng `fileset`, vì vậy hai task có thể quét hai vùng khác nhau nhưng áp dụng chung quy tắc chọn file.

`fileset` cũng có thể được đặt tên nếu cần dùng lại cả tập file, không chỉ các pattern:

```xml
<fileset id="release.resources" dir="src/main/resources">
    <include name="**/*"/>
    <exclude name="**/*.tmp"/>
</fileset>

<target name="stage-resources">
    <copy todir="build/resources">
        <fileset refid="release.resources"/>
    </copy>
</target>
```

Trong trường hợp này, `refid` tham chiếu đến cả `fileset`, bao gồm thư mục gốc và các quy tắc chọn file đã khai báo.

## 6. Những data type thường gặp

`id` và `refid` hữu ích nhất với các data type có hỗ trợ cơ chế reference. Một số loại thường gặp:

| Data type | Nội dung được gom lại | Tình huống sử dụng |
|---|---|---|
| `path` | Các phần tử đường dẫn | Dùng chung classpath hoặc path tài nguyên |
| `fileset` | Thư mục gốc và tập file được chọn | Dùng lại tập file trong copy, archive hoặc task tương thích |
| `patternset` | Quy tắc include/exclude | Áp dụng cùng bộ lọc cho nhiều fileset |
| `filterset` | Các cặp token và giá trị thay thế | Dùng chung quy tắc lọc nội dung file |
| `mapper` | Quy tắc ánh xạ tên đường dẫn | Dùng lại quy tắc đổi tên ở các task hỗ trợ mapper |

Khả năng nhận reference phụ thuộc vào data type hoặc task cụ thể. Khi dùng một loại mới, hãy kiểm tra tài liệu của phần tử đó để biết nó có hỗ trợ `id`/`refid` hay không và kiểu dữ liệu nào được chấp nhận.

## 7. Phạm vi và giới hạn cần nhớ

### Reference không phải là reference đến task

`id`/`refid` là cơ chế tham chiếu data type của Ant. Không thể dùng cơ chế này như cách đặt tên một task `javac` rồi gọi lại task đó bằng `refid`. Nếu muốn tái sử dụng chuỗi thao tác build, hãy tổ chức thành `target` và dùng quan hệ `depends`, hoặc đóng gói logic phù hợp bằng `macrodef`/`presetdef`.

### `refid` phải trỏ đến kiểu dữ liệu phù hợp

Ví dụ, một vị trí nhận `path` cần reference tương thích với `path`. Nếu đưa reference của `patternset` vào vị trí yêu cầu `path`, Ant không thể tự chuyển đổi hai kiểu dữ liệu đó.

### Reference và thứ tự thực thi target là hai vấn đề khác nhau

`refid` nói rằng phần tử cần dùng một đối tượng dữ liệu nào. Nó không yêu cầu target chứa đối tượng đó phải chạy trước. Để điều khiển thứ tự chạy các target, dùng `depends` hoặc cơ chế điều phối target phù hợp.

### Không dùng reference như một property

Không viết `${compile.classpath}` để thay cho `refid="compile.classpath"`. Nếu cần một chuỗi văn bản, hãy dùng property; nếu task cần một data type Ant, hãy dùng reference mà phần tử đó hỗ trợ.

## 8. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách kiểm tra |
|---|---|---|
| Ant báo không tìm thấy reference | Sai chính tả, sai chữ hoa/thường, reference chưa được khai báo hoặc nằm trong `Project` khác | So sánh chính xác giá trị `id` và `refid`; kiểm tra nơi khai báo |
| Ant báo kiểu dữ liệu không phù hợp | Reference tồn tại nhưng phần tử đang dùng yêu cầu kiểu khác | Kiểm tra tài liệu của nested element hoặc thuộc tính nhận reference |
| Thay đổi một nơi nhưng task khác không nhận cấu hình mới | Task đang dùng một định nghĩa khác hoặc một bản cấu hình được khai báo riêng | Lần theo `refid` đến đúng `id`; loại bỏ phần khai báo trùng không cần thiết |
| Buildfile có nhiều cấu hình gần giống nhau | Chưa gom phần dùng chung thành data type có `id` | Tách phần dùng chung thành `path`, `patternset` hoặc data type phù hợp |
| Nhầm `${...}` với `refid` | Đang trộn property dạng văn bản với reference đối tượng | Xác định task cần giá trị chuỗi hay một data type Ant |

Khi gặp lỗi reference, hãy tìm cả hai phía: nơi khai báo `id` và tất cả nơi sử dụng `refid`. Kiểm tra tên trước, sau đó kiểm tra phạm vi `Project` và kiểu dữ liệu mà vị trí sử dụng yêu cầu.

## 9. Quy tắc tổ chức buildfile dễ bảo trì

- Đặt các data type dùng chung ở phần đầu buildfile, gần các property cấu hình liên quan.
- Dùng tên mô tả mục đích, chẳng hạn `compile.classpath`, `test.classpath`, `runtime.classpath`, `java.source.patterns`.
- Chia reference theo mục đích. Một classpath quá rộng dùng cho mọi task có thể che giấu dependency thừa hoặc thiếu.
- Dùng property cho giá trị cấu hình đơn giản và dùng reference cho cấu trúc dữ liệu Ant.
- Chỉ tham chiếu một data type ở vị trí có hỗ trợ kiểu đó; không giả định rằng mọi task đều chấp nhận `refid`.
- Khi ghép nhiều `path`, dùng phần tử `path` lồng với `refid` để thể hiện rõ phần nào được kế thừa từ cấu hình có sẵn.
- Giữ quan hệ target riêng biệt: `depends` mô tả thứ tự thực thi, còn `refid` mô tả việc tái sử dụng dữ liệu.

## 10. Bài tập tự kiểm tra

**Bài 1.** Buildfile có một classpath được khai báo như sau:

```xml
<path id="test.classpath">
    <pathelement location="lib/junit.jar"/>
</path>
```

Muốn task `javac` dùng classpath đó, phần tử nested cần viết thế nào?

**Đáp án:**

```xml
<classpath refid="test.classpath"/>
```

**Bài 2.** Hai `fileset` cần cùng quy tắc loại file `**/*.tmp`. Nên đặt `id` cho data type nào?

**Đáp án:** Đặt `id` cho một `patternset` chứa quy tắc `<exclude name="**/*.tmp"/>`, sau đó đặt `<patternset refid="..."/>` bên trong từng `fileset`.

**Bài 3.** `${runtime.classpath}` có thể thay cho `refid="runtime.classpath"` không?

**Đáp án:** Không. `${...}` mở rộng property thành giá trị văn bản; `refid` tra cứu một đối tượng data type trong bảng reference của Ant.

## Kết luận

`id` và `refid` giúp buildfile chia sẻ các data type đã khai báo. `id` đặt tên cho đối tượng; `refid` yêu cầu Ant dùng lại đối tượng đó ở nơi tương thích. Nắm rõ khác biệt giữa reference, property và quan hệ target sẽ giúp buildfile ngắn gọn hơn, nhất quán hơn và dễ bảo trì khi classpath, tập file hoặc quy tắc lọc thay đổi.

