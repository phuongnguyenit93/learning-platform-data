# Điều phối tập dự án con bằng `subant`

Khi một hệ thống Java được chia thành nhiều dự án con, mỗi dự án thường có `build.xml` riêng. Ví dụ, một ứng dụng có thể gồm module `core`, `service`, `web` và `cli`. Mỗi module có thể biên dịch hoặc đóng gói độc lập, nhưng nhóm vẫn cần một cách gọi các bước build trên toàn bộ hệ thống.

Apache Ant cung cấp task `<subant>` để điều phối nhiều build file con. Thay vì viết một task `<ant>` riêng cho từng module, build file cấp cao có thể xác định một tập dự án con, rồi yêu cầu Ant chạy cùng một target trên từng dự án trong tập đó.

`subant` đặc biệt hữu ích khi các dự án con tuân theo một quy ước chung, chẳng hạn đều có target `clean`, `compile`, `test` và `package`. Build file gốc có thể gọi các target đó trên nhiều module bằng một cấu hình ngắn gọn.

Sau bài học, bạn có thể:

- Phân biệt `<subant>` với `<ant>` và `<antcall>`.
- Chọn dự án con bằng `buildpath`, `fileset` hoặc `dirset`.
- Gọi một target trên từng build file con.
- Dùng `genericantfile` khi các dự án dùng chung tên build file khác `build.xml`.
- Truyền property và reference từ build cha xuống build con.
- Kiểm soát `inheritall`, `inheritrefs` và `failonerror`.
- Tổ chức thứ tự build giữa các module có quan hệ phụ thuộc.
- Xây dựng build file gốc để điều phối clean, compile, test và package cho nhiều dự án.

## 1. Vì sao cần điều phối nhiều dự án con?

Một dự án nhỏ có thể chỉ có một build file:

```text
hello-app/
├── build.xml
└── src/
```

Khi ứng dụng lớn dần, nhóm có thể tách mã nguồn thành nhiều module độc lập:

```text
platform/
├── build.xml                 # build file điều phối
└── modules/
    ├── core/
    │   └── build.xml
    ├── service/
    │   └── build.xml
    ├── web/
    │   └── build.xml
    └── cli/
        └── build.xml
```

Mỗi module có thể quản lý mã nguồn, dependency, thư mục đầu ra và target riêng. Ví dụ:

- `core` chứa mô hình dữ liệu và logic nền tảng.
- `service` sử dụng `core` để cung cấp nghiệp vụ.
- `web` sử dụng `service` để cung cấp giao diện HTTP.
- `cli` sử dụng `core` hoặc `service` để cung cấp giao diện dòng lệnh.

Nếu không có task điều phối, build file gốc phải gọi từng build file con một cách thủ công. Khi số module tăng, danh sách lời gọi trở nên dài và khó cập nhật.

`subant` cho phép mô tả tập dự án con một lần và thực hiện target trên từng dự án:

```xml
<subant target="compile">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

Ant tìm các build file khớp mẫu và gọi target `compile` trong từng build file đó.

## 2. `subant` là gì?

`<subant>` là task lõi của Apache Ant, dùng để chạy một target trên một tập build project con. Task này được thiết kế cho các hệ thống có nhiều build file và có thể lặp qua những dự án được xác định bởi một build path.

Về khái niệm, `subant` thực hiện các bước:

1. Đọc tập đường dẫn hoặc build file con được khai báo.
2. Xác định build file của từng dự án con.
3. Khởi tạo một Ant project con cho từng build file.
4. Truyền các property/reference theo cấu hình kế thừa.
5. Gọi target được chỉ định trong từng project con.
6. Xử lý lỗi theo thuộc tính `failonerror`.

Ví dụ:

```xml
<target name="compile-all">
    <subant target="compile">
        <fileset dir="modules">
            <include name="*/build.xml" />
        </fileset>
    </subant>
</target>
```

Nếu thư mục `modules` có bốn build file tương ứng với `core`, `service`, `web` và `cli`, Ant sẽ gọi target `compile` trong từng project con được chọn.

`subant` không tự hiểu cấu trúc module hay phân tích dependency giữa các module. Nó điều phối các build file theo tập đường dẫn và thứ tự được cung cấp. Việc xác định module nào phải build trước vẫn cần được thiết kế trong build file gốc.

## 3. Phân biệt `subant`, `ant` và `antcall`

Ba task có mục đích khác nhau:

| Task | Phạm vi | Cách sử dụng |
|---|---|---|
| `<antcall>` | Gọi target khác trong cùng build project. | Chuyển sang target khác trong build file hiện tại. |
| `<ant>` | Gọi một build file/project con cụ thể. | Chạy một target của một project con. |
| `<subant>` | Gọi target trên nhiều build project con. | Lặp qua build path và chạy cùng target ở từng project. |

### 3.1. `antcall`: gọi target trong cùng project

```xml
<target name="prepare">
    <echo message="Preparing current project" />
</target>

<target name="package">
    <antcall target="prepare" />
    <echo message="Packaging current project" />
</target>
```

`antcall` tạo một lần thực thi target khác trong cùng build project. Nó không tìm các build file trong thư mục con.

### 3.2. `ant`: gọi một project con cụ thể

```xml
<target name="compile-core">
    <ant antfile="modules/core/build.xml" target="compile" />
</target>
```

Task `ant` phù hợp khi build file gốc cần gọi một project con cụ thể hoặc cần truyền cấu hình riêng cho một lần gọi.

### 3.3. `subant`: gọi nhiều project con

```xml
<target name="compile-modules">
    <subant target="compile">
        <fileset dir="modules">
            <include name="*/build.xml" />
        </fileset>
    </subant>
</target>
```

Task `subant` phù hợp khi nhiều project con có cùng quy ước target. Nó giúp tránh lặp nhiều task `<ant>` tương tự nhau.

## 4. Chọn dự án con bằng `buildpath`

`buildpath` xác định những thư mục hoặc build file mà `subant` sẽ xử lý. Có thể khai báo bằng thuộc tính, reference hoặc phần tử lồng nhau.

### 4.1. Dùng `fileset` để chọn build file

Đây là cách phổ biến khi mỗi module có một file tên `build.xml`:

```xml
<subant target="compile">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

`fileset` chọn các tệp `build.xml` nằm ngay trong thư mục con trực tiếp của `modules`.

Ví dụ, với cấu trúc:

```text
modules/
├── core/build.xml
├── service/build.xml
├── web/build.xml
└── cli/build.xml
```

mẫu `*/build.xml` chọn cả bốn build file.

Nếu chỉ muốn điều phối một nhóm module, có thể liệt kê mẫu cụ thể:

```xml
<subant target="test">
    <fileset dir="modules">
        <include name="core/build.xml" />
        <include name="service/build.xml" />
    </fileset>
</subant>
```

Hoặc loại một module khỏi tập được chọn:

```xml
<subant target="package">
    <fileset dir="modules">
        <include name="*/build.xml" />
        <exclude name="experimental/build.xml" />
    </fileset>
</subant>
```

Mẫu được tính tương đối với thư mục `dir` của FileSet. Nếu cấu trúc module có nhiều cấp, điều chỉnh mẫu `include` cho phù hợp, ví dụ `**/build.xml`.

### 4.2. Dùng `dirset` để chọn thư mục dự án

Nếu các project con đều có build file tên mặc định `build.xml`, có thể chọn các thư mục bằng `dirset`:

```xml
<subant target="compile">
    <dirset dir="modules">
        <include name="core" />
        <include name="service" />
        <include name="web" />
    </dirset>
</subant>
```

Mỗi thư mục được chọn được xem như một dự án con. Ant tìm build file theo tên được chỉ định bởi `genericantfile`, mặc định là `build.xml`.

`dirset` phù hợp khi bạn muốn mô tả tập thư mục module. `fileset` phù hợp khi muốn chọn chính xác từng build file, nhất là khi build file có tên khác nhau hoặc nằm ở vị trí không đồng nhất.

### 4.3. Dùng `buildpath` lồng nhau

Có thể khai báo rõ từng vị trí bằng path element:

```xml
<subant target="clean">
    <buildpath>
        <pathelement location="modules/core" />
        <pathelement location="modules/service" />
        <pathelement location="modules/web" />
    </buildpath>
</subant>
```

Mỗi path element ở đây là thư mục chứa build file con. Cách khai báo tường minh hữu ích khi chỉ có một số module cố định và thứ tự cần được kiểm soát.

### 4.4. Dùng `buildpathref`

Nếu nhiều target dùng chung một tập module, có thể khai báo path một lần bằng `id` rồi tham chiếu:

```xml
<path id="all.modules">
    <pathelement location="modules/core" />
    <pathelement location="modules/service" />
    <pathelement location="modules/web" />
</path>

<target name="clean-all">
    <subant target="clean" buildpathref="all.modules" />
</target>

<target name="compile-all">
    <subant target="compile" buildpathref="all.modules" />
</target>
```

`buildpathref` trỏ đến một path đã khai báo. Cách này giúp tập dự án con nhất quán giữa các target và tránh lặp danh sách thư mục.

## 5. `genericantfile` và tên build file của dự án con

Mặc định, khi build path chứa thư mục, `subant` tìm build file tên `build.xml` trong mỗi thư mục. Nếu các module dùng cùng một tên khác, có thể chỉ định bằng `genericantfile`.

Ví dụ, mỗi module có tệp `module-build.xml`:

```text
modules/
├── core/module-build.xml
├── service/module-build.xml
└── web/module-build.xml
```

Build file gốc:

```xml
<subant target="compile" genericantfile="module-build.xml">
    <dirset dir="modules">
        <include name="core" />
        <include name="service" />
        <include name="web" />
    </dirset>
</subant>
```

`genericantfile` là tên build file được dùng chung tương đối với từng thư mục dự án con. Nếu mỗi module có một build file riêng và được chọn trực tiếp bằng FileSet, bạn có thể để `subant` xử lý các đường dẫn build file đã chọn.

Hãy phân biệt:

- **Build path là thư mục:** Ant cần tên build file để tìm trong mỗi thư mục; mặc định là `build.xml`, có thể đổi bằng `genericantfile`.
- **Build path là các build file:** FileSet có thể chọn trực tiếp từng file cần chạy.

Không nên khai báo `genericantfile` không khớp với cấu trúc thư mục. Nếu Ant không tìm thấy file, hãy kiểm tra build path và tên file trước khi điều tra target bên trong.

## 6. Gọi target trong project con

Thuộc tính `target` xác định target sẽ được gọi ở từng project con:

```xml
<subant target="test" failonerror="true">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

Mỗi build file con cần có target tương ứng hoặc có target mặc định phù hợp nếu bạn không chỉ định `target`. Với một quy ước build nhiều module, nên chuẩn hóa các target cơ bản như:

```text
clean
init
compile
test
package
```

Ví dụ build file con:

```xml
<project name="core" default="package" basedir=".">
    <property name="src.dir" location="src/main/java" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />

    <target name="clean">
        <delete dir="${build.dir}" />
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}" />
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false" />
    </target>

    <target name="package" depends="compile">
        <jar destfile="${build.dir}/core.jar"
             basedir="${classes.dir}" />
    </target>
</project>
```

Build file gốc có thể gọi target `package` trên tất cả module:

```xml
<target name="package-all">
    <subant target="package">
        <fileset dir="modules">
            <include name="*/build.xml" />
        </fileset>
    </subant>
</target>
```

Mỗi project con tự xử lý dependency nội bộ trong build file của nó. `subant` chỉ đảm nhiệm việc gọi target đã chọn trên các project trong tập.

## 7. Truyền property từ build cha xuống build con

Build file gốc thường có các giá trị chung như version phát hành, mức Java, môi trường build hoặc thư mục đầu ra. `subant` có thể truyền property xuống các project con.

Ví dụ build file gốc:

```xml
<project name="platform-build" default="compile-all">
    <property name="release.version" value="1.0.0" />
    <property name="java.release" value="17" />

    <target name="compile-all">
        <subant target="compile">
            <property name="release.version" value="${release.version}" />
            <property name="java.release" value="${java.release}" />
            <fileset dir="modules">
                <include name="*/build.xml" />
            </fileset>
        </subant>
    </target>
</project>
```

Trong project con, có thể dùng các property được truyền:

```xml
<project name="core" default="compile">
    <property name="release.version" value="dev" />
    <property name="java.release" value="17" />

    <target name="compile">
        <echo message="Building ${ant.project.name} version ${release.version}" />
        <javac srcdir="src/main/java"
               destdir="build/classes"
               release="${java.release}"
               includeantruntime="false" />
    </target>
</project>
```

Property được truyền vào project con đã tồn tại trước khi các khai báo mặc định cùng tên trong project con được xử lý. Vì property Ant thông thường bất biến, giá trị truyền từ cha sẽ được giữ lại.

### 7.1. Truyền property qua dòng lệnh

Có thể truyền một giá trị cho build cha:

```bash
ant -Drelease.version=2.3.0 -Djava.release=17 compile-all
```

Build cha truyền các giá trị đó xuống các build con bằng nested `<property>`. Cách này hữu ích khi CI cần bảo đảm mọi module dùng cùng version và cùng mức Java.

### 7.2. `inheritall`

Thuộc tính `inheritall` quyết định việc truyền các property của project cha sang project con.

```xml
<subant target="compile" inheritall="true">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

`inheritall` mặc định là `true`. Khi bật, các property của project cha được truyền sang project con. Khi đặt `false`, việc kế thừa property thông thường bị giới hạn; các user property được truyền từ dòng lệnh vẫn có cơ chế kế thừa riêng. Nếu project con cần những giá trị cụ thể, có thể truyền rõ bằng nested `<property>`.

Ví dụ chủ động giới hạn property:

```xml
<subant target="compile" inheritall="false">
    <property name="release.version" value="${release.version}" />
    <property name="java.release" value="${java.release}" />
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

Khi dùng `inheritall="false"`, build file con nhận các property được truyền rõ ràng và user property theo quy tắc của Ant. Cách này giúp giảm sự phụ thuộc ngầm vào toàn bộ cấu hình của build cha.

### 7.3. Property được khai báo lại trong project con

Property Ant không thể bị ghi đè sau khi đã đặt. Vì vậy, nếu build cha truyền `release.version=2.3.0`, khai báo mặc định `release.version=dev` trong project con không thay thế giá trị đó.

Đây là cách hữu ích để project con có giá trị mặc định khi chạy độc lập, đồng thời nhận giá trị chung khi được build từ project cha.

## 8. Truyền reference và `inheritrefs`

Ngoài property, Ant còn có reference như `path`, `fileset`, `mapper` hoặc datatype có `id`. Có thể điều khiển việc truyền reference từ project cha sang project con bằng `inheritrefs`.

Mặc định, `inheritrefs` là `false`. Nếu muốn project con nhận các reference từ project cha, có thể bật:

```xml
<path id="shared.tools.classpath">
    <pathelement location="tools/shared.jar" />
</path>

<subant target="compile" inheritrefs="true">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

Trong project con, reference có thể được dùng theo ID nếu nó được truyền và datatype có thể chia sẻ/copy theo cơ chế reference của Ant:

```xml
<target name="compile">
    <javac srcdir="src/main/java" destdir="build/classes">
        <classpath refid="shared.tools.classpath" />
    </javac>
</target>
```

Không nên bật `inheritrefs` một cách máy móc. Reference có thể mang trạng thái hoặc chứa đường dẫn phụ thuộc vào thư mục của project cha. Khi project con dùng chung ID với reference riêng, có thể phát sinh xung đột hoặc kết quả khó hiểu.

Với cấu hình classpath, thường dễ bảo trì hơn nếu mỗi project con tự tạo reference dựa trên thư viện và thư mục của chính nó. Chỉ truyền reference khi có một tài nguyên thực sự dùng chung và đường dẫn của nó có ý nghĩa đối với tất cả project con.

## 9. Kiểm soát lỗi bằng `failonerror`

`failonerror` quyết định điều gì xảy ra khi một build con thất bại.

Mặc định, `failonerror="true"`. Nếu một project con không chạy được target hoặc target trả lỗi, task `subant` báo lỗi và build cha thất bại.

```xml
<subant target="test" failonerror="true">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

Đây thường là lựa chọn phù hợp cho build tích hợp: nếu một module bắt buộc không biên dịch hoặc test thất bại, toàn bộ build cần được đánh dấu thất bại.

Có thể đặt `failonerror="false"` để không dừng toàn bộ quá trình khi một project con lỗi:

```xml
<subant target="test" failonerror="false">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

Chế độ này có thể hữu ích khi muốn chạy tiếp các module khác để thu thập thêm kết quả. Tuy nhiên, cần có cách tổng hợp và hiển thị lỗi rõ ràng; nếu không, build cha có thể kết thúc mà người dùng không nhận ra một module đã thất bại.

Với build phát hành, thông thường nên giữ `failonerror="true"` để không tạo artifact tổng hợp từ một tập module không đầy đủ.

## 10. Thư mục cơ sở của project con

Mỗi build file có thể có thuộc tính `basedir` trong phần tử `<project>`. Khi được gọi từ `subant`, thư mục cơ sở của project con ảnh hưởng đến cách phân giải đường dẫn tương đối trong build file đó.

Ví dụ:

```xml
<project name="core" default="compile" basedir=".">
    <property name="src.dir" location="src/main/java" />
    <property name="build.dir" location="build" />
</project>
```

Mặc định, `subant` sử dụng thư mục chứa build file con làm cơ sở cho project đó. Thuộc tính `useNativeBasedir="true"` cho phép sử dụng `basedir` được khai báo trong build file con:

```xml
<subant target="compile" useNativeBasedir="true">
    <fileset dir="modules">
        <include name="*/build.xml" />
    </fileset>
</subant>
```

Thuộc tính này hữu ích khi build file con được đặt ở một thư mục nhưng cố ý dùng một thư mục cơ sở khác. Nếu không có nhu cầu đó, giữ cách phân giải mặc định giúp mỗi module hoạt động tương đối độc lập với vị trí gọi nó.

Khi đường dẫn trong project con bị sai chỉ khi chạy từ build cha, hãy kiểm tra `basedir`, vị trí thực tế của build file và `useNativeBasedir`.

## 11. Thứ tự chạy các project con

`subant` xử lý các mục trong build path theo thứ tự được cung cấp. Nó không tự phân tích quan hệ phụ thuộc module để sắp xếp theo đồ thị dependency.

Giả sử:

```text
web --> service --> core
```

Nếu target `compile` của `service` cần JAR đã tạo từ `core`, thì `core` phải được xử lý trước `service`. Tương tự, `web` cần `service` trước.

Có thể khai báo thứ tự build path rõ ràng:

```xml
<subant target="package">
    <buildpath>
        <pathelement location="modules/core" />
        <pathelement location="modules/service" />
        <pathelement location="modules/web" />
    </buildpath>
</subant>
```

Không nên dựa vào thứ tự duyệt file ngẫu nhiên hoặc thứ tự do hệ thống tệp trả về. Nếu thứ tự là quan trọng, hãy khai báo path tường minh.

### 11.1. Dependency giữa module nên được biểu diễn rõ

Có hai cách tổ chức phổ biến:

1. Build cha gọi từng nhóm module theo thứ tự dependency.
2. Mỗi module tự resolve artifact phụ thuộc từ repository hoặc từ một output location ổn định.

Ví dụ gọi tuần tự theo nhóm:

```xml
<target name="package-core">
    <subant target="package">
        <dirset dir="modules">
            <include name="core" />
        </dirset>
    </subant>
</target>

<target name="package-services" depends="package-core">
    <subant target="package">
        <dirset dir="modules">
            <include name="service" />
        </dirset>
    </subant>
</target>

<target name="package-web" depends="package-services">
    <subant target="package">
        <dirset dir="modules">
            <include name="web" />
        </dirset>
    </subant>
</target>
```

Với hệ thống lớn, nên quản lý dependency module bằng một quy ước rõ ràng hoặc công cụ quản lý build/dependency phù hợp. `subant` là bộ điều phối target, không thay thế dependency manager.

### 11.2. Tránh chu trình phụ thuộc

Nếu `core` cần `service` trong khi `service` cũng cần `core`, cấu trúc dependency có chu trình. Việc đổi thứ tự `subant` không giải quyết được vấn đề kiến trúc này.

Hãy xác định module nền tảng và module phụ thuộc theo hướng một chiều. Khi phát hiện chu trình, xem xét tách interface hoặc module chung để các module không phụ thuộc lẫn nhau trực tiếp.

## 12. Điều phối các target thường gặp

Build file gốc thường cung cấp các target tổng hợp như `clean-all`, `compile-all`, `test-all` và `package-all`.

Ví dụ:

```xml
<project name="platform" default="compile-all" basedir=".">
    <property name="modules.dir" location="modules" />

    <target name="clean-all">
        <subant target="clean" failonerror="true">
            <fileset dir="${modules.dir}">
                <include name="*/build.xml" />
            </fileset>
        </subant>
    </target>

    <target name="compile-all">
        <subant target="compile" failonerror="true">
            <fileset dir="${modules.dir}">
                <include name="*/build.xml" />
            </fileset>
        </subant>
    </target>

    <target name="test-all">
        <subant target="test" failonerror="true">
            <fileset dir="${modules.dir}">
                <include name="*/build.xml" />
            </fileset>
        </subant>
    </target>

    <target name="package-all">
        <subant target="package" failonerror="true">
            <fileset dir="${modules.dir}">
                <include name="*/build.xml" />
            </fileset>
        </subant>
    </target>
</project>
```

Trong ví dụ, mọi module được chọn phải cung cấp các target tương ứng. Nếu một module không có target `test`, việc gọi `test-all` có thể thất bại. Có thể dùng các FileSet khác nhau để chọn nhóm module phù hợp với từng thao tác.

## 13. Kết hợp `subant` với `buildpathref`

Để tránh lặp FileSet trong nhiều target, có thể khai báo một reference chứa danh sách dự án con:

```xml
<path id="module.buildpath">
    <pathelement location="modules/core" />
    <pathelement location="modules/service" />
    <pathelement location="modules/web" />
</path>

<target name="clean-all">
    <subant target="clean" buildpathref="module.buildpath" />
</target>

<target name="compile-all">
    <subant target="compile" buildpathref="module.buildpath" />
</target>

<target name="test-all">
    <subant target="test" buildpathref="module.buildpath" />
</target>
```

Path được định nghĩa một lần, các target dùng lại bằng `buildpathref`. Thứ tự các `pathelement` cũng thể hiện thứ tự gọi module, nên có thể kiểm soát thứ tự bằng cách sắp xếp các phần tử.

Nếu cần chọn module động theo mẫu, FileSet hoặc DirSet thường linh hoạt hơn một path liệt kê tĩnh.

## 14. Dùng `genericantfile` với nhiều module có chung cấu trúc

Một số repository tổ chức build file con dưới tên như `ant/build.xml` hoặc `module-build.xml`. Nếu các module cùng tuân theo một quy ước, `genericantfile` giúp gọi chúng mà không cần liệt kê từng file riêng.

Ví dụ:

```text
modules/
├── core/
│   └── ant/module-build.xml
├── service/
│   └── ant/module-build.xml
└── web/
    └── ant/module-build.xml
```

Khi build path trỏ đến các thư mục module, có thể dùng:

```xml
<subant target="compile" genericantfile="ant/module-build.xml">
    <dirset dir="modules">
        <include name="core" />
        <include name="service" />
        <include name="web" />
    </dirset>
</subant>
```

`genericantfile` được phân giải tương đối với mỗi thư mục dự án con. Cách này phù hợp khi cấu trúc module thống nhất.

Nếu build file con có tên hoặc vị trí khác nhau, dùng FileSet để chọn trực tiếp các build file thay vì cố ép chúng theo một generic path.

## 15. Điều phối build nhiều dự án theo quy ước target

Để `subant` phát huy hiệu quả, các build file con nên có giao diện target nhất quán. Ví dụ:

| Target chuẩn | Trách nhiệm của project con |
|---|---|
| `clean` | Xóa đầu ra có thể tạo lại của chính module. |
| `init` | Tạo thư mục đầu ra và chuẩn bị cấu hình cục bộ. |
| `compile` | Biên dịch mã nguồn module. |
| `test` | Chạy kiểm thử của module. |
| `package` | Tạo JAR/WAR hoặc artifact của module. |
| `javadoc` | Tạo tài liệu API nếu module có API công khai. |

Build file gốc không cần biết chi tiết từng lệnh `javac` hoặc `jar` trong module. Nó chỉ cần biết target chuẩn mà module cung cấp.

Đây là một dạng hợp đồng giữa build cha và build con. Khi một module không tuân theo hợp đồng, cần quyết định rõ: loại module đó khỏi nhóm target, bổ sung target tương thích hoặc tách nhóm điều phối.

## 16. Ví dụ hoàn chỉnh: build nhiều module theo thứ tự

Giả sử hệ thống có ba module:

```text
multi-project/
├── build.xml
└── modules/
    ├── core/
    │   ├── build.xml
    │   └── src/main/java/
    ├── service/
    │   ├── build.xml
    │   └── src/main/java/
    └── web/
        ├── build.xml
        └── src/main/java/
```

Quan hệ phụ thuộc:

```text
core
  |
  v
service
  |
  v
web
```

Build file gốc:

```xml
<project name="multi-project" default="package-all" basedir=".">
    <property name="modules.dir" location="modules" />
    <property name="release.version" value="1.0.0" />
    <property name="java.release" value="17" />

    <target name="clean-all">
        <subant target="clean" failonerror="true">
            <buildpath>
                <pathelement location="${modules.dir}/core" />
                <pathelement location="${modules.dir}/service" />
                <pathelement location="${modules.dir}/web" />
            </buildpath>
        </subant>
    </target>

    <target name="compile-core">
        <subant target="compile" genericantfile="build.xml"
                failonerror="true">
            <buildpath>
                <pathelement location="${modules.dir}/core" />
            </buildpath>
            <property name="release.version" value="${release.version}" />
            <property name="java.release" value="${java.release}" />
        </subant>
    </target>

    <target name="compile-service" depends="compile-core">
        <subant target="compile" genericantfile="build.xml"
                failonerror="true">
            <buildpath>
                <pathelement location="${modules.dir}/service" />
            </buildpath>
            <property name="release.version" value="${release.version}" />
            <property name="java.release" value="${java.release}" />
        </subant>
    </target>

    <target name="compile-web" depends="compile-service">
        <subant target="compile" genericantfile="build.xml"
                failonerror="true">
            <buildpath>
                <pathelement location="${modules.dir}/web" />
            </buildpath>
            <property name="release.version" value="${release.version}" />
            <property name="java.release" value="${java.release}" />
        </subant>
    </target>

    <target name="package-all" depends="compile-web">
        <subant target="package" genericantfile="build.xml"
                failonerror="true">
            <buildpath>
                <pathelement location="${modules.dir}/core" />
                <pathelement location="${modules.dir}/service" />
                <pathelement location="${modules.dir}/web" />
            </buildpath>
            <property name="release.version" value="${release.version}" />
        </subant>
    </target>
</project>
```

Trong ví dụ này, build cha chia việc compile thành ba target để thể hiện quan hệ phụ thuộc. `compile-core` chạy trước `compile-service`, rồi `compile-web`. Sau khi các module đã biên dịch, `package-all` gọi target `package` trên từng module.

Nếu build file con dùng `basedir="."` và đặt trong thư mục module, các đường dẫn tương đối như `src/main/java` sẽ được phân giải từ thư mục module. Nếu build file con nằm ở vị trí khác hoặc dùng `basedir` riêng, xem xét `useNativeBasedir`.

Ví dụ giả định build file của `service` và `web` có cách lấy artifact của module phụ thuộc phù hợp. Trong hệ thống thực tế, dependency giữa module có thể được giải quyết bằng repository cục bộ, Ivy, output path dùng chung hoặc cơ chế build được nhóm lựa chọn. `subant` chỉ đảm bảo target được gọi theo thứ tự mà build cha mô tả.

## 17. Lỗi thường gặp khi dùng `subant`

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant không tìm thấy build file con | `buildpath`, `fileset` hoặc `genericantfile` không khớp cấu trúc thư mục. | Kiểm tra đường dẫn và tên build file thực tế. |
| Target không tồn tại trong một module | Các build file con không tuân theo cùng quy ước target. | Chuẩn hóa target hoặc chia module thành các nhóm điều phối riêng. |
| Project con không nhận property mong muốn | `inheritall` bị tắt hoặc property chưa được truyền rõ. | Kiểm tra `inheritall` và thêm nested `<property>`. |
| Reference không có trong project con | `inheritrefs` mặc định là false. | Bật `inheritrefs` có chủ đích hoặc tạo reference cục bộ trong project con. |
| Đường dẫn tương đối bị sai | `basedir` của project con khác dự kiến. | Kiểm tra vị trí build file và `useNativeBasedir`. |
| Một module lỗi làm dừng toàn bộ build | `failonerror` mặc định là true. | Giữ mặc định nếu module bắt buộc; dùng false chỉ khi có quy trình tổng hợp lỗi rõ ràng. |
| Module phụ thuộc chưa được build | Thứ tự build path không thể hiện dependency. | Khai báo thứ tự tường minh hoặc chia target theo dependency graph. |
| Kết quả build thay đổi theo máy | Dựa vào thứ tự duyệt thư mục, property môi trường hoặc đường dẫn tuyệt đối. | Khai báo build path và property rõ ràng, chuẩn hóa môi trường. |
| Build lặp lại một module ngoài dự kiến | Cùng module được gọi qua nhiều target hoặc nhiều lần `subant`. | Xem lại dependency target và tập build path của từng bước. |
| Module con không tìm được JAR của module khác | `subant` không tự quản lý dependency artifact. | Cấu hình classpath hoặc dependency manager như Ivy. |

## 18. Khi nào nên dùng `subant` và khi nào nên dùng task khác?

`subant` phù hợp khi nhiều build project có cấu trúc tương tự và cần chạy cùng một target trên tập dự án đó.

| Tình huống | Cách nên xem xét |
|---|---|
| Gọi target trong cùng build file | `<antcall>` hoặc dependency `depends` giữa các target. |
| Gọi một build file con cụ thể | `<ant>`. |
| Gọi cùng target trên nhiều build file | `<subant>`. |
| Quản lý dependency thư viện giữa các module | Ivy hoặc dependency manager phù hợp. |
| Điều phối một đồ thị module phức tạp với nhiều quan hệ | Thiết kế target gốc theo dependency graph hoặc cân nhắc hệ thống build có hỗ trợ multi-project chuyên biệt. |

Không nên dùng `subant` chỉ để thay thế một target `depends` trong cùng project. Nó tạo project con riêng và có các quy tắc truyền property/reference, basedir và kết quả thực thi riêng.

## 19. Bài thực hành

Tạo cấu trúc sau:

```text
subant-lab/
├── build.xml
└── modules/
    ├── core/
    │   └── build.xml
    ├── service/
    │   └── build.xml
    └── web/
        └── build.xml
```

Trong mỗi project con, khai báo các target `clean`, `compile` và `package`. Mỗi module có thể dùng một thư mục `build` riêng.

Viết build file gốc để:

1. Khai báo property `modules.dir`, `release.version` và `java.release`.
2. Tạo target `clean-all` dùng `subant` gọi target `clean` trên cả ba module.
3. Tạo target `compile-all` gọi `compile` trên các module theo thứ tự `core`, `service`, `web`.
4. Truyền `release.version` và `java.release` xuống project con.
5. Thử `inheritall="false"` và chỉ truyền các property cần thiết.
6. Tạo target `package-all` gọi `package` trên từng module.
7. Thử dùng `buildpathref` để tái sử dụng danh sách module.
8. Thử dùng `fileset` chọn build file và `dirset` chọn thư mục dự án.
9. Tạm thời đổi tên một build file để quan sát lỗi tìm build file.
10. Tạo một target con cố ý thất bại để so sánh `failonerror="true"` và `false`.

Ví dụ target điều phối:

```xml
<path id="module.buildpath">
    <pathelement location="modules/core" />
    <pathelement location="modules/service" />
    <pathelement location="modules/web" />
</path>

<target name="compile-all">
    <subant target="compile"
            buildpathref="module.buildpath"
            failonerror="true"
            inheritall="false">
        <property name="release.version" value="${release.version}" />
        <property name="java.release" value="${java.release}" />
    </subant>
</target>
```

Chạy:

```bash
ant clean-all
ant -Drelease.version=2.0.0 -Djava.release=17 compile-all
ant -Drelease.version=2.0.0 package-all
```

Quan sát log để xác định thứ tự các project con được gọi. Sau đó đảo thứ tự path và so sánh kết quả. Nếu module phụ thuộc artifact của module khác, hãy bảo đảm artifact cần thiết đã được tạo hoặc được lấy từ dependency repository trước khi biên dịch module phụ thuộc.

### Câu hỏi tự kiểm tra

1. `<subant>` giải quyết vấn đề gì trong một hệ thống có nhiều build file?
2. Khác biệt giữa `<ant>` và `<subant>` là gì?
3. Khi nào nên dùng `fileset`, khi nào nên dùng `dirset`?
4. `genericantfile` dùng để làm gì?
5. `buildpathref` có lợi ích gì?
6. `inheritall` mặc định là `true` hay `false`?
7. `inheritrefs` mặc định là `true` hay `false`?
8. `failonerror="false"` có thể gây rủi ro gì cho build tổng hợp?
9. `subant` có tự sắp xếp module theo dependency không?
10. `useNativeBasedir` ảnh hưởng đến cách xác định thư mục cơ sở như thế nào?

### Đáp án gợi ý

- `subant` gọi cùng target trên một tập build project con được xác định bằng build path.
- `ant` gọi một project con; `subant` lặp qua nhiều project con.
- `fileset` chọn trực tiếp build file; `dirset` chọn thư mục module chứa build file theo tên mặc định hoặc `genericantfile`.
- `genericantfile` chỉ định tên build file dùng chung trong các thư mục dự án con.
- `buildpathref` cho phép nhiều target dùng lại một path đã khai báo.
- `inheritall` mặc định là `true`.
- `inheritrefs` mặc định là `false`.
- Build cha có thể tiếp tục dù một module thất bại, khiến kết quả tổng hợp không đầy đủ nếu không thu thập lỗi rõ ràng.
- Không. `subant` theo thứ tự build path; build cha phải xác định thứ tự cần thiết.
- Khi bật `useNativeBasedir`, Ant dùng `basedir` được khai báo trong build file con thay vì mặc định lấy thư mục chứa build file.

## Kết luận

`<subant>` là task lõi của Ant để điều phối cùng một target trên nhiều build project con. Dùng `fileset` khi muốn chọn build file, `dirset` hoặc `buildpath` khi muốn chọn thư mục dự án, `genericantfile` khi các module dùng chung tên build file và `buildpathref` khi cần tái sử dụng danh sách module. Các thuộc tính `inheritall`, `inheritrefs`, `failonerror` và `useNativeBasedir` quyết định cách project con nhận cấu hình, xử lý lỗi và phân giải đường dẫn. Hãy khai báo thứ tự module theo dependency một cách tường minh, vì `subant` điều phối các lần gọi nhưng không tự suy luận đồ thị phụ thuộc giữa dự án con.
