# Kiểm tra tệp, lớp và tài nguyên bằng available

## 1. Vai trò của available trong Ant

Trong một build, không phải bước nào cũng có thể chạy trong mọi môi trường. Một cấu hình có thể tồn tại ở máy lập trình nhưng không có trên CI; một thư viện tùy chọn có thể chỉ được cài ở một số module; một file cấu hình có thể được tạo bởi bước trước hoặc được cung cấp riêng cho bản phát hành.

Apache Ant cung cấp task `available` để kiểm tra một tài nguyên có sẵn trước khi thực hiện bước phụ thuộc vào nó. Task có thể kiểm tra ba nhóm phổ biến:

- **Tệp hoặc thư mục trên filesystem**: kiểm tra đường dẫn có tồn tại, và có thể yêu cầu đúng loại là file hoặc directory.
- **Java class**: kiểm tra một class có thể được tìm thấy qua classpath được chỉ định.
- **Java resource**: kiểm tra một resource có thể được tìm thấy qua classpath, ví dụ một file cấu hình nằm trong thư mục tài nguyên hoặc JAR.

Khi điều kiện đúng, task đặt một Ant property. Các target phía sau có thể dùng property đó với thuộc tính `if` hoặc `unless` để quyết định có thực thi hay không.

`available` là cơ chế phát hiện điều kiện ở thời điểm build. Nó không tự cài thư viện, tạo file còn thiếu hay sửa classpath. Nó chỉ giúp build nhận biết đầu vào hiện có và chọn nhánh xử lý phù hợp.

## 2. Kiểm tra tệp và thư mục

Để kiểm tra một đường dẫn trên filesystem, dùng thuộc tính `file`:

```xml
<available file="config/app.properties"
           property="app.config.available"/>
```

Nếu đường dẫn tồn tại, Ant đặt property `app.config.available`. Mặc định, giá trị property là chuỗi `true`.

Đường dẫn tương đối được giải quyết theo `basedir` của Ant project, thường là thư mục chứa build file hoặc giá trị được khai báo trong thuộc tính `basedir` của project. Nếu build được gọi từ nhiều thư mục khác nhau, dùng `${basedir}` để biểu diễn rõ gốc dự án:

```xml
<available file="${basedir}/config/app.properties"
           property="app.config.available"/>
```

Có thể giới hạn loại đường dẫn bằng thuộc tính `type`:

- `type="file"`: chỉ chấp nhận đường dẫn trỏ tới một tệp.
- `type="dir"`: chỉ chấp nhận đường dẫn trỏ tới một thư mục.

Ví dụ kiểm tra cả thư mục đầu ra và file cấu hình:

```xml
<target name="detect-local-inputs">
    <available file="${basedir}/build/classes"
               type="dir"
               property="classes.dir.available"/>

    <available file="${basedir}/config/release.properties"
               type="file"
               property="release.config.available"/>
</target>
```

Nếu chỉ cần biết đường dẫn có tồn tại mà không cần phân biệt file và directory, có thể bỏ `type`. Khi loại đường dẫn có ý nghĩa với bước tiếp theo, nên khai báo `type` để tránh một thư mục được coi là file đầu vào hoặc ngược lại.

`available` không tạo thư mục hoặc tệp. Nếu kiểm tra không thành công, property tương ứng không được đặt.

## 3. Kiểm tra Java class

Một dự án có thể có task tùy chọn phụ thuộc vào thư viện bên ngoài. Trước khi chạy task đó, có thể kiểm tra class đại diện của thư viện bằng thuộc tính `classname`.

Ví dụ:

```xml
<path id="optional.library.classpath">
    <pathelement location="${basedir}/lib/optional-api.jar"/>
</path>

<target name="detect-optional-library">
    <available classname="com.example.optional.Feature"
               classpathref="optional.library.classpath"
               property="optional.feature.available"/>
</target>
```

Trong ví dụ này:

- `classname` là tên đầy đủ của class, gồm cả package.
- `classpathref` tham chiếu một Ant Path đã khai báo.
- `property` là tên property được đặt nếu class có thể được tìm thấy.

Có thể khai báo classpath trực tiếp bằng thuộc tính `classpath` hoặc phần tử lồng nhau nếu cần. Ví dụ dùng tham chiếu giúp tránh lặp lại cùng danh sách thư viện ở nhiều nơi.

Một classpath khác nhau có thể cho kết quả khác nhau. Class có thể tồn tại trong JDK hoặc trong thư viện của một module nhưng không có trong classpath của task cần kiểm tra. Vì vậy, hãy truyền đúng classpath mà bước build thực tế sẽ dùng.

Ví dụ kiểm tra JUnit trước khi chạy nhóm test tùy chọn:

```xml
<path id="test.classpath">
    <pathelement location="${basedir}/lib/junit-platform-console.jar"/>
    <pathelement location="${basedir}/build/classes"/>
</path>

<target name="detect-junit-console">
    <available classname="org.junit.platform.console.ConsoleLauncher"
               classpathref="test.classpath"
               property="junit.console.available"/>
</target>
```

Tên class cần kiểm tra phải thực sự có trong thư viện và phiên bản được đưa vào classpath. Nếu chỉ có một JAR khác phiên bản hoặc một artifact không chứa class đó, điều kiện sẽ không đạt.

Kiểm tra class không tương đương với xác minh toàn bộ thư viện hoạt động đúng. Class có thể được tìm thấy nhưng khi chạy vẫn gặp lỗi do thiếu class phụ thuộc, phiên bản không tương thích, cấu hình sai hoặc lỗi khởi tạo. `available` chỉ xác nhận khả năng tìm thấy class theo cơ chế kiểm tra của Ant.

## 4. Kiểm tra Java resource trên classpath

Một số thư viện và ứng dụng nạp tài nguyên bằng classloader thay vì truy cập một đường dẫn filesystem cụ thể. Ví dụ:

- File cấu hình được đóng gói bên trong JAR.
- File metadata nằm trong thư mục resources.
- Tệp template được nạp qua `ClassLoader.getResource`.
- Resource mặc định của một thư viện.

Có thể dùng thuộc tính `resource` để kiểm tra tên resource trên classpath:

```xml
<path id="application.classpath">
    <pathelement location="${basedir}/build/classes"/>
    <pathelement location="${basedir}/lib/application-support.jar"/>
</path>

<target name="detect-default-config">
    <available resource="com/example/config/defaults.properties"
               classpathref="application.classpath"
               property="default.config.available"/>
</target>
```

Tên resource thường được viết theo dạng đường dẫn dùng dấu `/`, bắt đầu từ gốc classpath. Không thêm đường dẫn filesystem của JAR vào tên resource; JAR phải được đưa vào classpath, còn `resource` là tên mục bên trong classpath đó.

Ví dụ, nếu resource nằm ở:

```text
src/main/resources/
└── com/
    └── example/
        └── config/
            └── defaults.properties
```

sau khi resource được copy vào thư mục output hoặc đóng gói trong JAR, tên cần tìm là:

```text
com/example/config/defaults.properties
```

Không dùng `file="..."` để kiểm tra một resource chỉ nằm bên trong JAR. Trên filesystem, đường dẫn `lib/application-support.jar/com/example/config/defaults.properties` không phải một file thông thường. Hãy kiểm tra bằng `resource` với classpath chứa JAR.

## 5. Đặt property khi điều kiện đúng

Cấu trúc tổng quát của task:

```xml
<target name="detect-input">
    <available
        file="path/to/input"
        property="input.available"
        value="present"/>
</target>
```

Các thuộc tính thường dùng:

| Thuộc tính | Ý nghĩa |
|---|---|
| `file` | Đường dẫn filesystem cần kiểm tra |
| `type` | Giới hạn loại đường dẫn là `file` hoặc `dir` |
| `classname` | Tên đầy đủ của Java class cần tìm |
| `resource` | Tên Java resource cần tìm trên classpath |
| `classpath` | Classpath dùng khi kiểm tra class hoặc resource |
| `classpathref` | Tham chiếu một Path đã khai báo |
| `property` | Tên Ant property được đặt khi điều kiện đúng |
| `value` | Giá trị đặt cho property; mặc định là `true` |

Trong một lần gọi, chọn loại đầu vào phù hợp với điều cần kiểm tra: `file`, `classname` hoặc `resource`. Không dùng nhiều loại đầu vào như thể chúng là các điều kiện độc lập được tự động kết hợp.

Nếu điều kiện sai, `available` không đặt property. Task không tự đặt property thành chuỗi `false`. Đây là đặc điểm quan trọng khi dùng `if` và `unless`.

Ví dụ dùng giá trị tùy chỉnh:

```xml
<available file="${basedir}/config/local.properties"
           property="config.state"
           value="found"/>
```

Khi file tồn tại, `config.state` có giá trị `found`. Khi file không tồn tại, property này không được tạo bởi task đó.

## 6. Kết hợp available với điều kiện của target

Ant cho phép target dùng thuộc tính `if` và `unless` để kiểm soát việc thực thi:

- `if="property"`: target chạy khi property đã được đặt.
- `unless="property"`: target chạy khi property chưa được đặt.

Các thuộc tính này kiểm tra **sự tồn tại của property**, không diễn giải chuỗi giá trị của nó như boolean. Nếu property có giá trị `false`, nó vẫn là property đã tồn tại và target có `if="property"` vẫn chạy.

Để dùng kết quả kiểm tra, cần đặt task `available` trong một target chạy trước. Ví dụ:

```xml
<project name="optional-config" default="build">
    <target name="detect-config">
        <available file="${basedir}/config/release.properties"
                   type="file"
                   property="release.config.available"/>
    </target>

    <target name="build-with-release-config"
            depends="detect-config"
            if="release.config.available">
        <echo message="Using release configuration."/>
        <!-- Các bước build cần release.properties -->
    </target>

    <target name="build-with-default-config"
            depends="detect-config"
            unless="release.config.available">
        <echo message="Release configuration not found; using defaults."/>
        <!-- Các bước build dùng cấu hình mặc định -->
    </target>

    <target name="build"
            depends="build-with-release-config,build-with-default-config"/>
</project>
```

Luồng thực hiện:

1. Target `detect-config` kiểm tra file.
2. Nếu file tồn tại, property được đặt và target `build-with-release-config` được thực thi.
3. Nếu file không tồn tại, property không tồn tại và target `build-with-default-config` được thực thi.
4. Target `build` phụ thuộc vào hai nhánh để gom quy trình.

Cách này giúp build hoạt động được ở cả môi trường có và không có cấu hình tùy chọn.

Không nên định nghĩa sẵn property kiểm tra với cùng tên trước khi gọi `available`. Property của Ant thông thường là bất biến; nếu tên đó đã có giá trị, task không thể thay nó bằng kết quả mới. Ngoài ra, nếu tự đặt property thành chuỗi `false`, `unless` vẫn coi property đó là đã tồn tại.

## 7. Kiểm tra class hoặc resource trước khi chạy task tùy chọn

Một ví dụ hoàn chỉnh hơn là chỉ chạy một bước tích hợp khi thư viện tùy chọn có mặt:

```xml
<project name="optional-integration" default="build">
    <path id="integration.classpath">
        <pathelement location="${basedir}/lib/integration-client.jar"/>
        <pathelement location="${basedir}/build/classes"/>
    </path>

    <target name="detect-integration">
        <available classname="com.example.integration.Client"
                   classpathref="integration.classpath"
                   property="integration.client.available"/>

        <available resource="com/example/integration/defaults.xml"
                   classpathref="integration.classpath"
                   property="integration.defaults.available"/>
    </target>

    <target name="run-integration"
            depends="detect-integration"
            if="integration.client.available">
        <echo message="Integration client is available."/>
        <!-- Gọi task tích hợp tương ứng -->
    </target>

    <target name="skip-integration"
            depends="detect-integration"
            unless="integration.client.available">
        <echo message="Integration client is not installed; skipping."/>
    </target>

    <target name="build"
            depends="run-integration,skip-integration"/>
</project>
```

Ở ví dụ này, class và resource được kiểm tra riêng vì chúng là hai điều kiện khác nhau. Target `run-integration` chỉ kiểm tra sự tồn tại của class. Nếu task thực tế còn cần file cấu hình resource, nên bổ sung điều kiện tương ứng trước khi chạy và đưa ra thông báo rõ ràng khi thiếu.

Có thể kiểm tra nhiều điều kiện bằng task `condition` và các điều kiện lồng nhau như `and`, `or`, `not`. Ví dụ, nếu chỉ chạy một bước khi cả class lẫn resource đều có sẵn:

```xml
<target name="detect-integration">
    <condition property="integration.ready">
        <and>
            <available classname="com.example.integration.Client"
                       classpathref="integration.classpath"/>
            <available resource="com/example/integration/defaults.xml"
                       classpathref="integration.classpath"/>
        </and>
    </condition>
</target>
```

Property `integration.ready` chỉ được đặt khi cả hai điều kiện con đều đúng. Có thể dùng property này với `if` hoặc `unless` của target như ví dụ trước.

## 8. Phân biệt available với điều kiện khác

`available` tập trung vào khả năng tìm thấy đầu vào. Nó không thay thế các điều kiện kiểm tra nội dung hoặc trạng thái của hệ thống.

| Nhu cầu | Cách tiếp cận |
|---|---|
| Kiểm tra một file hoặc directory tồn tại | `available file="..."` |
| Kiểm tra class có trong classpath | `available classname="..."` |
| Kiểm tra resource có trong classpath | `available resource="..."` |
| Kiểm tra nhiều điều kiện cùng lúc | `condition` kết hợp `and`, `or`, `not` |
| Kiểm tra một giá trị số, chuỗi hoặc so sánh logic | Các condition phù hợp như `equals`, `isset`, `available` hoặc điều kiện chuyên biệt |
| Kiểm tra nội dung file có hợp lệ | Dùng task đọc/phân tích nội dung hoặc công cụ kiểm tra chuyên biệt |

Ví dụ, file tồn tại không có nghĩa file có nội dung đúng định dạng. Class tồn tại không có nghĩa mọi dependency của class đều tương thích. Resource được tìm thấy không có nghĩa nội dung resource hợp lệ với ứng dụng.

Nếu cần kiểm tra nội dung, hãy thực hiện thêm bước xác thực phù hợp. Tránh dùng sự tồn tại của file như bằng chứng rằng cấu hình đã hợp lệ.

## 9. Lỗi thường gặp

### Property không được đặt dù file có tồn tại

Kiểm tra đường dẫn được tính từ `basedir`, tên file, chữ hoa/chữ thường trên filesystem phân biệt hoa thường và thuộc tính `type`. Nếu dùng đường dẫn tương đối, hãy xác định thư mục gốc mà Ant project đang dùng.

### Class có trong máy nhưng available không tìm thấy

`available classname` cần kiểm tra classpath phù hợp. Việc JAR có trong thư mục `lib` không có nghĩa nó tự động thuộc classpath. Hãy thêm JAR vào `classpath` hoặc `classpathref` mà task sử dụng.

### Resource nằm trong JAR nhưng kiểm tra file thất bại

Đây là nhầm lẫn giữa đường dẫn filesystem và tên resource trong classpath. Dùng `resource` với tên resource bên trong JAR, đồng thời đưa JAR vào classpath.

### Target chạy sai nhánh

`if` và `unless` kiểm tra property có tồn tại. Một property mang giá trị chuỗi `false` vẫn được xem là đã đặt. Hãy để `available` chỉ tạo property khi điều kiện đúng và không định nghĩa trước cùng tên property.

### Property cũ làm kết quả kiểm tra không thay đổi

Ant property thông thường bất biến. Nếu một target hoặc file property đã đặt tên đó trước khi chạy `available`, task không thể ghi đè. Dùng tên property riêng cho từng lần kiểm tra hoặc tổ chức thứ tự khởi tạo để property chưa tồn tại trước khi kiểm tra.

### Kiểm tra thành công nhưng task phía sau vẫn lỗi

Khả năng tìm thấy class hoặc resource chỉ xác nhận một điều kiện tối thiểu. Task có thể cần thêm dependency, quyền truy cập, phiên bản tương thích hoặc cấu hình hợp lệ. Hãy xác định contract đầy đủ của task và kiểm tra tất cả đầu vào bắt buộc.

## 10. Nguyên tắc sử dụng

- Dùng `file` và `type` để phân biệt file với directory trên filesystem.
- Dùng `classname` khi cần xác nhận một class có thể tìm thấy trên classpath cụ thể.
- Dùng `resource` cho tài nguyên được nạp qua classloader, kể cả khi tài nguyên nằm bên trong JAR.
- Đặt property có tên mô tả rõ điều kiện, chẳng hạn `release.config.available` hoặc `optional.client.available`.
- Đặt các bước phát hiện trong target chạy trước những target sử dụng kết quả.
- Dùng `if` và `unless` dựa trên sự tồn tại của property; không coi chúng là phép kiểm tra chuỗi `true`/`false`.
- Không khai báo trước cùng property mà `available` cần đặt, vì property thông thường của Ant không thể bị ghi đè.
- Khi có nhiều điều kiện, dùng `condition` với `and`, `or` hoặc `not` để thể hiện logic rõ ràng.
- Kiểm tra nội dung và khả năng sử dụng thực tế riêng biệt với việc kiểm tra sự tồn tại.

`available` giúp build phát hiện trước các file, directory, class và resource cần thiết. Kết quả được biểu diễn bằng Ant property, từ đó target có thể chọn nhánh thực thi bằng `if` hoặc `unless`. Hiểu đúng loại đầu vào, classpath và quy tắc property bất biến sẽ giúp build thích ứng với nhiều môi trường mà vẫn báo lỗi rõ ràng khi thiếu dependency quan trọng.

