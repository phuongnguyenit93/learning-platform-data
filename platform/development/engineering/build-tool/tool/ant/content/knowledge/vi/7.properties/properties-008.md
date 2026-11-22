# Thời điểm mở rộng property, property chưa được đặt và ký tự escape

Trong Apache Ant, property là cách lưu các giá trị cấu hình để tái sử dụng trong `build.xml`. Bạn thường gặp cú pháp `${tên-property}` trong đường dẫn, tên tệp, classpath hoặc thông điệp. Tuy nhiên, một property chỉ thay thế được khi nó đã có giá trị tại thời điểm Ant xử lý phần tham chiếu đó.

Điều này đặc biệt quan trọng khi property được đặt bên trong target, khi một target phụ thuộc vào target khác, hoặc khi buildfile cần giữ nguyên một chuỗi trông giống property reference. Nếu hiểu sai thời điểm mở rộng, bạn có thể thấy `${...}` vẫn xuất hiện trong đầu ra, hoặc một đường dẫn nhận giá trị không như mong đợi.

Sau bài học, bạn có thể:

- Giải thích cách Ant mở rộng biểu thức `${property.name}`.
- Xác định khi nào một property cần được đặt để task sử dụng được nó.
- Hiểu điều gì xảy ra khi tham chiếu một property chưa tồn tại.
- Phân biệt property chưa được đặt với property có giá trị rỗng.
- Dùng `$${...}` để giữ nguyên một property reference dưới dạng văn bản.
- Phân biệt escape của Ant với escape của XML và tệp `.properties`.

## 1. Property và cú pháp tham chiếu

Property lưu một giá trị cấu hình dưới một tên. Có thể khai báo property bằng task `<property>`:

```xml
<project name="property-demo" default="show">
    <property name="app.name" value="HelloApp" />
    <property name="build.dir" location="build" />

    <target name="show">
        <echo message="Application: ${app.name}" />
        <echo message="Build directory: ${build.dir}" />
    </target>
</project>
```

Khi Ant xử lý các task trong target `show`, các biểu thức:

- `${app.name}` được thay bằng giá trị của property `app.name`.
- `${build.dir}` được thay bằng đường dẫn đã được xác định cho property `build.dir`.

Kết quả thông báo có dạng:

```text
Application: HelloApp
Build directory: .../build
```

Đường dẫn đầy đủ phụ thuộc vào thư mục dự án trên máy đang chạy build.

Tên property phân biệt chữ hoa và chữ thường. `${build.dir}` và `${Build.dir}` là hai tham chiếu khác nhau. Nên đặt tên có ý nghĩa và dùng nhất quán, ví dụ `src.dir`, `build.dir`, `classes.dir`, `jar.file`.

Property thường được dùng trong thuộc tính task:

```xml
<mkdir dir="${build.dir}/classes" />
<javac srcdir="${src.dir}" destdir="${build.dir}/classes" />
```

Khi Ant cấu hình task để thực thi, nó thay thế các tham chiếu property có thể giải quyết bằng giá trị hiện có. Property vì vậy giúp tránh lặp lại các đường dẫn và thông tin cấu hình ở nhiều nơi.

## 2. Thời điểm mở rộng property

Điểm cần ghi nhớ là Ant mở rộng property reference dựa trên những property đang có tại thời điểm giá trị được xử lý. Với các task nằm trong target, việc cấu hình và thực thi task diễn ra khi target được chạy. Do đó, một task có thể sử dụng property do task trước đó trong cùng luồng thực thi đặt ra.

Ví dụ:

```xml
<project name="timing-demo" default="show">
    <target name="show">
        <property name="greeting" value="Hello from Ant" />
        <echo message="${greeting}" />
    </target>
</project>
```

Khi chạy `ant show`, Ant thực hiện task `<property>` trước, sau đó mới cấu hình và thực hiện task `<echo>`. Vì `greeting` đã được đặt trước khi `<echo>` cần giá trị đó, kết quả là:

```text
Hello from Ant
```

Thứ tự task bên trong target có ý nghĩa. Nếu một task cần property do task khác tạo ra, task thiết lập property phải chạy trước task sử dụng nó.

### 2.1. Property được đặt trong target phụ thuộc

Property cũng có thể được đặt ở một target riêng, rồi dùng trong target phụ thuộc vào nó:

```xml
<project name="timing-demo" default="package">
    <property name="build.dir" location="build" />

    <target name="define-output">
        <property name="release.dir" value="${build.dir}/release" />
    </target>

    <target name="package" depends="define-output">
        <mkdir dir="${release.dir}" />
        <jar destfile="${release.dir}/app.jar" basedir="${build.dir}/classes" />
    </target>
</project>
```

Khi chạy `ant package`, Ant giải quyết phụ thuộc `define-output` trước. Target này đặt `release.dir`; sau đó target `package` mới thực hiện các task sử dụng `${release.dir}`.

Trình tự có thể biểu diễn như sau:

```text
ant package
     |
     v
define-output
     |
     +-- đặt release.dir
     |
     v
package
     |
     +-- mở rộng ${release.dir}
     +-- tạo thư mục và tệp JAR
```

Đây là lý do `depends` không chỉ giúp sắp xếp các bước build mà còn bảo đảm property cần thiết được đặt trước khi target sử dụng nó.

### 2.2. Tham chiếu trước khi property được đặt

Nếu task sử dụng property trước khi property đó tồn tại, Ant không thể thay thế tham chiếu bằng giá trị mong muốn. Ví dụ:

```xml
<project name="timing-demo" default="wrong-order">
    <target name="show-version">
        <echo message="Version: ${app.version}" />
    </target>

    <target name="set-version">
        <property name="app.version" value="1.0" />
    </target>

    <target name="wrong-order" depends="show-version,set-version">
        <echo message="Build requested" />
    </target>
</project>
```

Khi chạy `ant wrong-order`, target `show-version` được xử lý trước `set-version`. Tại thời điểm task `<echo>` trong `show-version` được cấu hình, `app.version` chưa tồn tại. Ant thường giữ nguyên tham chiếu chưa giải quyết, nên thông điệp có dạng:

```text
Version: ${app.version}
```

Sau đó `set-version` mới đặt property `app.version`. Việc đặt property muộn không quay lại cấu hình và thực hiện lại task `<echo>` đã chạy trước đó.

Sửa thứ tự phụ thuộc:

```xml
<target name="correct-order" depends="set-version,show-version">
    <echo message="Build requested" />
</target>
```

Khi chạy `ant correct-order`, `set-version` được thực hiện trước `show-version`, vì vậy thông điệp sẽ là:

```text
Version: 1.0
```

Trong buildfile thực tế, hãy khai báo quan hệ phụ thuộc theo dữ liệu mà target sau cần. Đừng dựa vào việc property có thể được đặt ở một target nào đó mà không bảo đảm target đó chạy trước.

### 2.3. Property khai báo ở cấp project và property trong target

Property có thể được khai báo ở cấp `<project>` hoặc bên trong `<target>`:

```xml
<project name="demo" default="compile">
    <!-- Cấu hình chung của project -->
    <property name="src.dir" location="src" />

    <target name="compile">
        <!-- Cấu hình chỉ được đặt khi target này chạy -->
        <property name="classes.dir" location="build/classes" />
        <mkdir dir="${classes.dir}" />
        <javac srcdir="${src.dir}" destdir="${classes.dir}" />
    </target>
</project>
```

Property ở cấp project thường dùng cho cấu hình chung mà nhiều target cần. Property đặt trong target hữu ích khi giá trị chỉ cần được thiết lập khi target đó chạy hoặc khi việc thiết lập phụ thuộc vào một bước trước đó.

Không nên hiểu rằng property khai báo trong target chỉ có hiệu lực cục bộ trong target đó. Property thông thường của Ant là property cấp project và có thể được các target chạy sau sử dụng. Nếu cần phạm vi cục bộ, Ant có cơ chế riêng như task `<local>` trong các phiên bản hỗ trợ; đó là chủ đề nâng cao và khác với property thông thường.

## 3. Property chưa được đặt: điều gì xảy ra?

Một property chưa được đặt là property không tồn tại trong tập property hiện có tại thời điểm Ant xử lý tham chiếu. Ví dụ:

```xml
<target name="show">
    <echo message="Output: ${output.dir}" />
</target>
```

Nếu không có khai báo nào đặt `output.dir` trước khi task `<echo>` được cấu hình, Ant thường để nguyên chuỗi `${output.dir}`. Ant không mặc định thay property chưa tồn tại thành chuỗi rỗng.

Điều này quan trọng khi dùng property trong đường dẫn:

```xml
<copy file="config/app.properties" todir="${deploy.dir}" />
```

Nếu `deploy.dir` chưa được đặt, task có thể nhận chuỗi chứa nguyên tham chiếu `${deploy.dir}` làm đường dẫn và thất bại khi thực thi. Khi thấy một property reference xuất hiện nguyên dạng trong log hoặc thông báo, hãy kiểm tra xem property đó đã được khai báo hay chưa và target thiết lập nó có chạy trước hay không.

### 3.1. Các cách đặt property

Property có thể được đặt từ nhiều nguồn. Một số cách thường dùng:

**Khai báo trực tiếp trong buildfile:**

```xml
<property name="app.version" value="1.0" />
```

**Đọc từ tệp property:**

```xml
<property file="build.properties" />
```

Ví dụ nội dung `build.properties`:

```properties
app.version=1.0
deploy.dir=build/deploy
```

**Nhận giá trị từ dòng lệnh:**

```bash
ant -Dapp.version=2.0 package
```

Trong buildfile, có thể tham chiếu `${app.version}`. Giá trị truyền bằng `-D` được đặt từ lúc khởi chạy Ant và thường được dùng để ghi đè giá trị mặc định trong buildfile, bởi property của Ant không thể bị thay đổi sau khi đã được đặt.

**Đọc biến môi trường:**

```xml
<property environment="env" />
<echo message="Java home: ${env.JAVA_HOME}" />
```

Với khai báo `environment="env"`, Ant đưa các biến môi trường vào property có tiền tố `env.`. Chẳng hạn, biến môi trường `JAVA_HOME` được tham chiếu bằng `${env.JAVA_HOME}`.

### 3.2. Thứ tự khai báo và tính bất biến

Property thông thường của Ant là bất biến: sau khi đã có giá trị, một lần khai báo thông thường tiếp theo không thay đổi giá trị đó.

```xml
<property name="environment" value="development" />
<property name="environment" value="production" />

<echo message="Environment: ${environment}" />
```

Thông điệp vẫn là:

```text
Environment: development
```

Lệnh khai báo thứ hai không ghi đè giá trị đã có. Quy tắc này cũng giải thích vì sao property truyền bằng `-D` có thể giữ giá trị ưu tiên: khi buildfile chạy đến khai báo cùng tên, property đã tồn tại nên giá trị mới không thay thế nó.

Vì vậy, nếu một property chưa được đặt, bạn có thể đặt nó ở bước sau để các task tiếp theo sử dụng. Nhưng nếu property đã được đặt, không thể xem nó như một biến thông thường để gán lại nhiều lần. Hãy dùng tên property khác cho các giá trị khác nhau hoặc chọn một cơ chế cấu hình phù hợp.

## 4. Phân biệt property chưa đặt và property rỗng

Hai trạng thái này không giống nhau:

- **Chưa đặt:** Ant không có property với tên đó.
- **Đã đặt giá trị rỗng:** property tồn tại, nhưng giá trị của nó là chuỗi rỗng.

Ví dụ:

```xml
<property name="optional.suffix" value="" />
<echo message="Suffix=[${optional.suffix}]" />
```

Property `optional.suffix` tồn tại và có giá trị rỗng, nên thông điệp có dạng `Suffix=[]`. Nếu property chưa được khai báo, tham chiếu có thể vẫn xuất hiện nguyên dạng là `${optional.suffix}`.

Sự khác biệt này đặc biệt quan trọng với điều kiện `if` và `unless` của target. Các thuộc tính này kiểm tra **sự tồn tại của property**, không kiểm tra xem giá trị có phải chuỗi `true` hay không.

```xml
<target name="publish" if="publish.enabled">
    <echo message="Publish target is enabled" />
</target>

<target name="local-only" unless="ci.build">
    <echo message="Local build" />
</target>
```

- Target `publish` được xét để chạy khi property `publish.enabled` đã tồn tại.
- Target `local-only` được xét để chạy khi property `ci.build` chưa tồn tại.
- Nếu đặt `publish.enabled` thành chuỗi `false`, property vẫn tồn tại; điều kiện `if="publish.enabled"` vẫn được thỏa mãn.
- Một property có giá trị rỗng vẫn là property đã được đặt.

Nếu cần kiểm tra điều kiện theo giá trị, hãy dùng các task điều kiện như `<condition>` cùng những điều kiện con phù hợp, thay vì coi `if`/`unless` của target là phép so sánh boolean.

Ví dụ kiểm tra một property có tồn tại:

```xml
<target name="check-version">
    <condition property="version.is.set">
        <isset property="app.version" />
    </condition>
    <echo message="Version property exists: ${version.is.set}" />
</target>
```

`<isset>` kiểm tra sự tồn tại của property `app.version`; task `<condition>` đặt `version.is.set` khi điều kiện đúng. Đây là cách hữu ích khi muốn biến trạng thái tồn tại thành một property khác để các bước sau sử dụng.

## 5. Ký tự escape trong property reference

Ant nhận diện cú pháp `${...}` là tham chiếu property. Đôi khi bạn muốn giữ nguyên cú pháp này dưới dạng văn bản, ví dụ khi tạo tệp mẫu, viết hướng dẫn hoặc truyền một placeholder cho công cụ khác xử lý sau.

Trong Ant hiện đại, có thể dùng hai ký tự `$` để escape phần mở đầu của property reference. Cú pháp thường dùng là `$${tên-property}`. Ant bỏ một ký tự `$` escape và giữ lại chuỗi `${tên-property}` thay vì mở rộng property đó ở lần xử lý hiện tại.

Ví dụ:

```xml
<project name="escape-demo" default="show">
    <property name="app.version" value="1.0" />

    <target name="show">
        <echo message="Expanded: ${app.version}" />
        <echo message="Literal: $${app.version}" />
    </target>
</project>
```

Kết quả minh họa:

```text
Expanded: 1.0
Literal: ${app.version}
```

Ở dòng đầu, Ant thay `${app.version}` bằng giá trị `1.0`. Ở dòng thứ hai, `$${app.version}` yêu cầu Ant giữ cú pháp `${app.version}` như văn bản.

### 5.1. Khi nào cần giữ nguyên `${...}`?

Một số trường hợp thực tế:

- Tạo tệp cấu hình mẫu có placeholder để ứng dụng thay thế ở thời điểm chạy.
- Sinh một script hoặc tệp build khác có cú pháp `${...}` riêng.
- In hướng dẫn cho người dùng, trong đó cần hiển thị cú pháp property.
- Truyền một biểu thức đến công cụ xử lý ở bước sau thay vì để Ant thay thế ngay.

Ví dụ tạo tệp mẫu:

```xml
<target name="write-template">
    <echo file="build/app-template.properties" message="api.url=$${API_URL}${line.separator}api.key=$${API_KEY}" />
</target>
```

Khi task `<echo>` ghi tệp, các placeholder `${API_URL}` và `${API_KEY}` được giữ lại để ứng dụng hoặc công cụ triển khai thay thế sau. `${line.separator}` là property của Ant, nên nó được mở rộng thành ký tự xuống dòng của hệ điều hành.

Lưu ý: ví dụ trên minh họa việc escape placeholder cho một bước xử lý sau. Nếu tệp đầu ra cần một định dạng cụ thể, hãy kiểm tra thêm quy tắc escape của chính định dạng đó.

### 5.2. Escape không giống dấu gạch chéo ngược

Không nên mặc định dùng dấu gạch chéo ngược để escape property reference trong buildfile:

```xml
<echo message="${app.version}" />
```

Đây là property reference thông thường. Việc viết `\${app.version}` không phải cách escape property reference đáng tin cậy trong cú pháp Ant; hãy dùng `$${app.version}` khi muốn giữ nguyên placeholder.

Trong XML, dấu `$` không phải ký tự đặc biệt. Escape `$` là quy tắc của cơ chế property expansion của Ant, không phải quy tắc của XML.

## 6. Phân biệt escape của Ant, XML và tệp `.properties`

Một buildfile XML có thể trải qua nhiều lớp xử lý. Mỗi lớp có quy tắc riêng:

| Ngữ cảnh | Ký hiệu hoặc cách viết | Ý nghĩa |
|---|---|---|
| Ant property expansion | `${name}` | Tham chiếu property tên `name`. |
| Escape property expansion của Ant | `$${name}` | Giữ lại chuỗi `${name}` như văn bản. |
| XML attribute | `&amp;` | Biểu diễn ký tự `&` trong nội dung XML. |
| XML attribute | `&lt;` và `&gt;` | Biểu diễn ký tự `<` và `>` trong nội dung XML. |
| XML attribute | `&quot;` và `&apos;` | Biểu diễn dấu nháy kép và nháy đơn khi cần. |
| Java properties file | `\n`, `\t`, `\\`, `\uXXXX` | Các dạng escape theo cú pháp tệp properties của Java. |

Ví dụ:

```xml
<echo message="A &amp; B" />
<echo message="Literal placeholder: $${user.name}" />
```

Dòng thứ nhất dùng `&amp;` để XML biểu diễn dấu `&`. Dòng thứ hai dùng `$${user.name}` để Ant không mở rộng property reference. Hai cách escape giải quyết hai vấn đề khác nhau.

Nếu nạp tệp bằng `<property file="build.properties" />`, nội dung tệp được đọc theo quy tắc của Java properties. Ví dụ:

```properties
message=Line one\nLine two
windows.path=C:\\tools\\java
```

Ở đây `\n` và `\\` thuộc cú pháp của tệp properties; chúng không phải cú pháp escape `${...}` của Ant.

## 7. Những tình huống cần chú ý về thời điểm mở rộng

### 7.1. Giá trị property được mở rộng khi property được thiết lập

Khi một task `<property>` đặt giá trị dựa trên property khác, các tham chiếu trong giá trị được xử lý tại thời điểm task property thiết lập giá trị đó. Ví dụ:

```xml
<property name="base.dir" location="project" />
<property name="classes.dir" location="${base.dir}/build/classes" />
```

`classes.dir` được tạo từ giá trị `base.dir` đang có ở thời điểm khai báo thứ hai được xử lý. Vì vậy, nên đặt các property nền trước các property dẫn xuất.

Nếu tham chiếu chưa tồn tại tại thời điểm thiết lập property, đừng kỳ vọng nó tự động được tính lại sau khi một property khác xuất hiện. Hãy sắp xếp lại thứ tự khai báo hoặc đặt property dẫn xuất trong target chạy sau khi các giá trị nền đã sẵn sàng.

### 7.2. Giá trị property không tự thay đổi khi nguồn thay đổi

Property bất biến nên một giá trị dẫn xuất không hoạt động như công thức spreadsheet được tính lại mỗi khi đầu vào đổi. Ví dụ:

```xml
<property name="root.dir" value="build" />
<property name="output.dir" value="${root.dir}/classes" />
```

Sau khi `output.dir` được đặt, nó giữ giá trị đã thiết lập. Việc có một khai báo khác cho `root.dir` sau đó không làm `output.dir` tự tính lại.

### 7.3. Giá trị đến từ dòng lệnh

Khi người dùng truyền property bằng `-D`, giá trị đó có sẵn từ lúc Ant khởi chạy:

```bash
ant -Dbuild.dir=build-ci package
```

Trong buildfile:

```xml
<property name="build.dir" value="build" />
<target name="package">
    <echo message="Output directory: ${build.dir}" />
</target>
```

Giá trị `build-ci` từ dòng lệnh được giữ lại vì property đã được đặt trước khi task `<property>` trong buildfile cố đặt giá trị mặc định `build`. Đây là cách thường dùng để cho phép thay đổi đường dẫn hoặc chế độ build mà không sửa buildfile.

### 7.4. Giá trị được đặt bởi tệp property

Có thể kết hợp giá trị mặc định với tệp cấu hình:

```xml
<property name="build.dir" value="build" />
<property file="build.properties" />
```

Nếu `build.properties` có `build.dir=build-local`, giá trị mặc định đã được đặt trước nên tệp properties không ghi đè nó. Nếu muốn tệp cấu hình cung cấp giá trị trước, hãy đặt `<property file="build.properties" />` trước khai báo mặc định hoặc dùng cấu trúc fallback thích hợp. Vì property bất biến, thứ tự nguồn cấu hình có ảnh hưởng đến kết quả.

## 8. Ví dụ tổng hợp: quản lý cấu hình và placeholder

Ví dụ sau kết hợp property cấp project, property được đặt trong target, property truyền từ dòng lệnh, property chưa được đặt và escape placeholder:

```xml
<project name="property-lifecycle" default="show">
    <!-- Giá trị mặc định; có thể được thay bằng -D từ dòng lệnh -->
    <property name="app.name" value="SampleApp" />
    <property name="build.dir" value="build" />

    <target name="define-release">
        <property name="release.dir" value="${build.dir}/release" />
        <property name="app.version" value="1.0" />
    </target>

    <target name="show" depends="define-release">
        <echo message="Application: ${app.name}" />
        <echo message="Version: ${app.version}" />
        <echo message="Release directory: ${release.dir}" />
        <echo message="Template placeholder: $${DEPLOY_ENV}" />
        <echo message="Optional value: ${optional.value}" />
    </target>
</project>
```

Chạy:

```bash
ant show
```

Kết quả minh họa:

```text
Application: SampleApp
Version: 1.0
Release directory: build/release
Template placeholder: ${DEPLOY_ENV}
Optional value: ${optional.value}
```

Giải thích:

- `app.name` và `build.dir` được đặt ở cấp project.
- `release.dir` và `app.version` được đặt khi target `define-release` chạy.
- `show` phụ thuộc `define-release`, nên các property trong target này đã tồn tại khi task echo cần chúng.
- `$${DEPLOY_ENV}` giữ nguyên placeholder để một hệ thống khác thay thế sau.
- `optional.value` chưa được đặt, nên tham chiếu của nó vẫn hiển thị nguyên dạng.

Thử truyền giá trị khác:

```bash
ant -Dapp.name=TrainingApp -Dbuild.dir=out show
```

Các giá trị `app.name` và `build.dir` từ dòng lệnh được ưu tiên vì chúng đã được đặt trước khi các khai báo mặc định trong buildfile được xử lý. Khi đó `release.dir` được thiết lập dựa trên `build.dir` có giá trị `out`.

## 9. Bài thực hành

### Bài 1: Property được đặt trước hay sau khi sử dụng?

Cho buildfile:

```xml
<project name="timing" default="run">
    <target name="print">
        <echo message="Name=${app.name}" />
    </target>

    <target name="set-name">
        <property name="app.name" value="AntDemo" />
    </target>

    <target name="run" depends="print,set-name" />
</project>
```

Hãy dự đoán thông điệp được in ra khi chạy `ant run`. Sau đó đổi thứ tự thành `depends="set-name,print"` và giải thích sự khác biệt.

### Bài 2: Property chưa đặt và property rỗng

Xét hai trường hợp:

```xml
<property name="empty.value" value="" />

<target name="inspect">
    <echo message="Empty=[${empty.value}]" />
    <echo message="Missing=[${missing.value}]" />
</target>
```

Hãy giải thích vì sao hai thông điệp có kết quả khác nhau. Sau đó thử dùng `if="empty.value"` và `if="missing.value"` trên hai target riêng để quan sát điều kiện kiểm tra sự tồn tại.

### Bài 3: Giữ nguyên placeholder

Cho yêu cầu tạo một tệp mẫu có nội dung:

```text
server.url=${SERVER_URL}
```

Viết task `<echo>` dùng Ant để ghi nội dung đó vào tệp, kể cả khi property `SERVER_URL` chưa được đặt. Sử dụng cú pháp escape phù hợp.

### Bài 4: Thứ tự nguồn cấu hình

Xét buildfile:

```xml
<property name="mode" value="development" />
<property file="build.properties" />
<echo message="Mode: ${mode}" />
```

Nếu `build.properties` chứa `mode=production`, hãy dự đoán giá trị cuối cùng. Sau đó đổi thứ tự hai khai báo property và giải thích vì sao kết quả thay đổi.

### Đáp án gợi ý

- Bài 1: Với thứ tự `print,set-name`, task echo chạy khi `app.name` chưa tồn tại nên tham chiếu có thể được giữ nguyên. Khi đổi thành `set-name,print`, property đã có giá trị `AntDemo` trước khi echo chạy.
- Bài 2: `empty.value` tồn tại nhưng có giá trị chuỗi rỗng; `missing.value` chưa tồn tại nên tham chiếu thường được giữ nguyên. `if` kiểm tra sự tồn tại của property.
- Bài 3: Dùng `server.url=$${SERVER_URL}` trong nội dung được ghi để Ant giữ nguyên `${SERVER_URL}`.
- Bài 4: Với thứ tự ban đầu, `mode` đã được đặt thành `development`, nên tệp properties không ghi đè. Nếu nạp tệp trước, `mode=production` được đặt trước và khai báo mặc định sau đó không thay thế giá trị.

## Kết luận

Ant mở rộng property reference dựa trên những giá trị đã tồn tại tại thời điểm task hoặc giá trị cấu hình được xử lý. Vì vậy, thứ tự khai báo và quan hệ `depends` quyết định task có nhìn thấy property hay không. Property chưa được đặt thường được giữ nguyên dưới dạng `${name}`, còn property có giá trị rỗng vẫn được xem là đã tồn tại. Khi cần truyền nguyên placeholder cho bước xử lý sau, hãy dùng `$${name}` để escape property expansion của Ant. Đồng thời, hãy phân biệt quy tắc này với escape ký tự của XML và tệp `.properties`.
