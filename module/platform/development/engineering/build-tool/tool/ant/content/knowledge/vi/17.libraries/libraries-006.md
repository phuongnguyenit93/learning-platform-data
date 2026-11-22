# Khai báo module và dependency trong `ivy.xml` với Apache Ivy

Apache Ivy là công cụ quản lý dependency có thể tích hợp với Apache Ant. Thay vì tự tải từng JAR và tự viết classpath, ta mô tả module của dự án cùng các thư viện nó cần trong file `ivy.xml`. Ivy đọc mô tả này, giải quyết các dependency trực tiếp và bắc cầu, rồi cung cấp artifact cho các task Ant như `javac`, `java`, `jar` hoặc các bước kiểm thử.

`ivy.xml` là module descriptor: nó mô tả module hiện tại, các configuration, artifact được công bố và dependency mà module yêu cầu. File này không tự định nghĩa máy chủ tải thư viện; repository và resolver thường được cấu hình riêng trong `ivysettings.xml` hoặc qua cấu hình Ivy tương ứng.

## 1. Module, artifact và dependency

Trong Ivy, một module là một đơn vị phần mềm có định danh. Định danh phổ biến gồm:

- **organisation:** tổ chức hoặc nhóm sở hữu module, ví dụ `com.example`.
- **module:** tên module, ví dụ `inventory-app`.
- **revision:** phiên bản của module, ví dụ `1.0.0`.
- **status:** trạng thái phát triển/phát hành, ví dụ `integration`, `milestone` hoặc `release`.

Artifact là file được tạo hoặc phân phối bởi module, thường là JAR, ZIP hoặc tài liệu. Dependency mô tả một module khác mà module hiện tại cần dùng. Một dependency được nhận diện bằng organisation, module và revision; Ivy có thể tiếp tục giải quyết các dependency bắc cầu của nó.

Ví dụ, ứng dụng `inventory-app` có thể phụ thuộc vào `commons-io` để thao tác file và JUnit để chạy test. JUnit chỉ cần trong configuration test, còn `commons-io` cần khi biên dịch và chạy ứng dụng.

## 2. Cấu trúc cơ bản của `ivy.xml`

Một module descriptor theo định dạng Ivy thường có phần tử gốc `ivy-module` và các phần chính sau:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info
        organisation="com.example"
        module="inventory-app"
        revision="1.0.0"
        status="integration"/>

    <configurations>
        <!-- Các configuration của module -->
    </configurations>

    <publications>
        <!-- Artifact do module công bố -->
    </publications>

    <dependencies>
        <!-- Các module mà dự án phụ thuộc -->
    </dependencies>
</ivy-module>
```

| Phần tử | Vai trò |
|---|---|
| `<info>` | Định danh module hiện tại và metadata của nó |
| `<configurations>` | Khai báo các nhóm dependency/biến thể sử dụng |
| `<publications>` | Khai báo artifact mà module cung cấp |
| `<dependencies>` | Khai báo các module mà dự án cần |

Các phần tử có thể có thêm thuộc tính hoặc phần tử con. Hãy khai báo đúng thứ tự và cấu trúc theo định dạng Ivy 2.x mà dự án sử dụng.

## 3. Khai báo metadata trong `<info>`

Ví dụ:

```xml
<info
    organisation="com.example.platform"
    module="inventory-app"
    revision="1.2.0"
    status="release"
    publication="20261112120000"/>
```

- `organisation` xác định nhóm/tổ chức sở hữu module. Nên dùng namespace ổn định, thường theo dạng tên miền đảo ngược.
- `module` là tên module; tránh đổi tên tùy tiện vì consumer dùng tên này để tìm dependency.
- `revision` là phiên bản của module hiện tại, không phải revision của dependency.
- `status` mô tả trạng thái như `integration`, `milestone` hoặc `release`. Trạng thái cụ thể có thể được tùy chỉnh trong settings.
- `publication` có thể ghi thời điểm công bố theo định dạng Ivy sử dụng.

Ví dụ trên nói rằng module hiện tại là `com.example.platform:inventory-app:1.2.0`. Khi module được publish lên repository, định danh này giúp các module khác khai báo dependency đến nó.

Không nhầm `revision` trong `<info>` với thuộc tính `rev` của `<dependency>`. Một cái là phiên bản của module đang mô tả; cái còn lại là phiên bản module mà nó phụ thuộc.

## 4. Khai báo configurations

Configuration mô tả một nhóm dependency và artifact có thể được dùng trong một ngữ cảnh. Các tên thường gặp trong dự án Java:

- `compile`: dependency cần để biên dịch mã chính.
- `runtime`: dependency cần khi chạy ứng dụng; thường kế thừa dependency compile.
- `test`: dependency dành cho biên dịch và chạy kiểm thử.
- `default`: configuration tiêu chuẩn để consumer khác dùng module.

Có thể khai báo chúng trong `ivy.xml`:

```xml
<configurations>
    <conf name="compile" visibility="public"/>
    <conf name="runtime" visibility="public" extends="compile"/>
    <conf name="test" visibility="private" extends="runtime"/>
    <conf name="default" visibility="public" extends="runtime"/>
</configurations>
```

`extends` cho phép một configuration kế thừa các dependency từ configuration khác. Trong ví dụ, `runtime` kế thừa `compile`, `test` kế thừa `runtime`, còn `default` kế thừa `runtime`. Vì vậy, dependency compile có thể xuất hiện trong runtime/test theo quan hệ kế thừa.

`visibility="public"` cho phép consumer nhìn thấy configuration khi module được sử dụng. Configuration `private` chỉ phục vụ nội bộ module và thường phù hợp với nhóm dependency test. Việc đặt visibility cần phù hợp với cách module được publish và consumer sử dụng.

Configuration là khái niệm của Ivy, không phải một thư mục trên filesystem. Tên `compile`, `runtime` hay `test` là quy ước do descriptor khai báo; chúng chỉ có ý nghĩa khi dependency mapping và các task Ivy sử dụng đúng tên đó.

## 5. Khai báo dependency trong `<dependencies>`

Mỗi dependency trực tiếp thường dùng phần tử `dependency` với các thuộc tính `org`, `name`, `rev` và `conf`:

```xml
<dependencies>
    <dependency org="commons-io"
                name="commons-io"
                rev="2.16.1"
                conf="compile->default"/>

    <dependency org="junit"
                name="junit"
                rev="4.13.2"
                conf="test->default"/>
</dependencies>
```

Ý nghĩa:

- `org`: organisation của module được yêu cầu.
- `name`: tên module được yêu cầu.
- `rev`: revision cần dùng.
- `conf`: ánh xạ configuration của module hiện tại sang configuration của dependency.

Trong `compile->default`, vế trái `compile` là configuration của module hiện tại; vế phải `default` là configuration được yêu cầu từ module dependency. Như vậy `commons-io` được đưa vào compile configuration. JUnit chỉ được đưa vào test configuration.

Có thể khai báo nhiều mapping bằng dấu chấm phẩy, ví dụ `conf="compile->default;runtime->default"`. Nếu dependency cần cho nhiều configuration, hãy mô tả rõ mapping thay vì dựa vào cấu hình mặc định không dễ đoán.

### Dependency trực tiếp và dependency bắc cầu

Dependency trực tiếp là dependency được khai báo trong `ivy.xml`. Dependency bắc cầu là dependency mà một dependency trực tiếp lại khai báo. Ivy có thể tiếp tục giải quyết các dependency bắc cầu để tạo classpath hoàn chỉnh.

Ví dụ, ứng dụng khai báo `library-a`, còn `library-a` phụ thuộc `library-b`. Nếu dependency được cấu hình transitive (mặc định thường là có), Ivy sẽ giải quyết cả `library-b` theo descriptor của `library-a`. Nếu tắt transitive, chỉ dependency trực tiếp được lấy; ứng dụng phải tự khai báo các thư viện cần thiết khác.

## 6. Dependency mapping và configuration của module được phụ thuộc

Configuration mapping cho phép chọn đúng nhóm dependency từ module khác. Một vài dạng thường gặp:

| Mapping | Ý nghĩa |
|---|---|
| `compile->default` | Configuration compile của module hiện tại dùng default của dependency |
| `runtime->default` | Runtime dùng default của dependency |
| `test->default` | Test dùng default của dependency |
| `compile->compile;runtime->runtime` | Ánh xạ các configuration tương ứng ở hai module |
| `compile->default,runtime->default` | Một configuration cục bộ có thể ánh xạ đến nhiều configuration dependency |

Ví dụ một dependency cung cấp configuration riêng:

```xml
<dependency org="com.example"
            name="data-model"
            rev="3.1.0"
            conf="compile->api;runtime->runtime"/>
```

Ở đây module hiện tại dùng configuration `api` của dependency khi biên dịch, và configuration `runtime` khi chạy. Cách viết chỉ hợp lệ nếu module `data-model` thực sự công bố các configuration đó.

Không đoán tên configuration của thư viện. Hãy xem module descriptor hoặc metadata mà repository cung cấp. Nếu module chỉ có `default`, dùng mapping `->default` thường là lựa chọn rõ ràng.

## 7. Exclude và kiểm soát dependency bắc cầu

Đôi khi một thư viện kéo theo dependency không cần thiết hoặc xung đột với phiên bản mà dự án đã chọn. Có thể đặt exclude bên trong một dependency để loại module bắc cầu cụ thể:

```xml
<dependency org="com.example"
            name="legacy-reporting"
            rev="2.4.0"
            conf="runtime->default">
    <exclude org="commons-logging"
             module="commons-logging"/>
</dependency>
```

Exclude trong ví dụ chỉ áp dụng cho nhánh dependency của `legacy-reporting`. Nó không nhất thiết loại module đó khỏi mọi nhánh khác trong toàn bộ đồ thị dependency.

Có thể dùng `transitive="false"` khi không muốn Ivy theo dependency bắc cầu của một module:

```xml
<dependency org="com.example"
            name="isolated-tool"
            rev="1.0.0"
            transitive="false"
            conf="test->default"/>
```

Khi tắt transitive, cần tự khai báo các dependency mà code thực sự sử dụng. Nếu không, compile có thể thất bại với lỗi thiếu class hoặc runtime có thể gặp `ClassNotFoundException`/`NoClassDefFoundError`.

## 8. Kiểm soát revision và xung đột phiên bản

Để build có thể tái lập, nên dùng revision cụ thể đã được kiểm tra:

```xml
<dependency org="org.apache.commons"
            name="commons-lang3"
            rev="3.14.0"
            conf="compile->default"/>
```

Các revision động như `latest.integration`, `latest.release` hoặc khoảng revision có thể khiến hai lần resolve ở hai thời điểm khác nhau chọn các artifact khác nhau. Chúng hữu ích khi cần theo dõi phiên bản mới trong quá trình phát triển, nhưng cần được kiểm soát khi build release.

Khi nhiều nhánh dependency yêu cầu các revision khác nhau của cùng một module, Ivy phải áp dụng conflict manager theo cấu hình. Có thể điều chỉnh bằng Ivy settings hoặc các chỉ thị trong descriptor, nhưng không nên thêm `force="true"` một cách tùy tiện vì nó có thể che giấu dependency không tương thích.

Ví dụ `force` chỉ nên dùng khi dự án có quyết định rõ ràng buộc toàn đồ thị vào một revision:

```xml
<dependency org="org.slf4j"
            name="slf4j-api"
            rev="2.0.13"
            force="true"
            conf="compile->default"/>
```

Hãy kiểm tra báo cáo resolve để biết revision nào đã được chọn và vì sao. Nếu có thể, ưu tiên căn chỉnh dependency trong các module thay vì ép phiên bản tại nhiều nơi.

## 9. Khai báo artifact mà module công bố

Phần tử `<publications>` mô tả artifact do module hiện tại tạo ra. Với thư viện Java, artifact thường là JAR:

```xml
<publications>
    <artifact name="inventory-app"
              type="jar"
              ext="jar"
              conf="default"/>
</publications>
```

- `name`: tên artifact, thường tương ứng tên file không có phần mở rộng.
- `type`: loại artifact, ví dụ `jar`.
- `ext`: phần mở rộng file, ví dụ `jar`.
- `conf`: configuration mà artifact được gắn vào.

Khai báo publication giúp Ivy biết module sẽ publish hoặc cung cấp artifact nào. Nó không tự biên dịch Java hay tạo JAR; Ant vẫn cần task `javac` và `jar` để tạo file vật lý trước khi publish.

Với module chỉ là ứng dụng nội bộ không được publish như dependency, phần `<publications>` có thể đơn giản hoặc không cần khai báo artifact tùy workflow. Nếu muốn module khác phụ thuộc vào nó, hãy khai báo artifact và cấu hình publication phù hợp.

## 10. `ivy.xml` hoàn chỉnh cho một ứng dụng Java

Ví dụ dưới đây mô tả ứng dụng `inventory-app`, dùng `commons-io` trong mã chính và JUnit trong test:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivy-module version="2.0">
    <info
        organisation="com.example"
        module="inventory-app"
        revision="1.0.0"
        status="integration"/>

    <configurations>
        <conf name="compile" visibility="public"/>
        <conf name="runtime" visibility="public" extends="compile"/>
        <conf name="test" visibility="private" extends="runtime"/>
        <conf name="default" visibility="public" extends="runtime"/>
    </configurations>

    <publications>
        <artifact name="inventory-app"
                  type="jar"
                  ext="jar"
                  conf="default"/>
    </publications>

    <dependencies>
        <dependency org="commons-io"
                    name="commons-io"
                    rev="2.16.1"
                    conf="compile->default"/>
        <dependency org="junit"
                    name="junit"
                    rev="4.13.2"
                    conf="test->default"/>
    </dependencies>
</ivy-module>
```

Trong descriptor này:

1. Module hiện tại có định danh `com.example:inventory-app:1.0.0`.
2. `runtime` kế thừa `compile`, nên dependency compile cũng có mặt trong runtime.
3. `test` kế thừa runtime và bổ sung JUnit chỉ dành cho test.
4. Artifact JAR được công bố trong configuration `default`.
5. Dependency được khóa vào revision cụ thể để kết quả resolve dễ tái lập.

`ivy.xml` mô tả dependency và artifact, còn `ivysettings.xml` quyết định nơi Ivy tìm chúng. Hai file có trách nhiệm khác nhau.

## 11. Cấu hình repository bằng `ivysettings.xml`

Ivy cần biết resolver nào sẽ tìm module. Có thể khai báo một resolver tương thích Maven repository trong `ivysettings.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ivysettings>
    <settings defaultResolver="central"/>
    <resolvers>
        <ibiblio name="central" m2compatible="true"/>
    </resolvers>
</ivysettings>
```

Resolver `ibiblio` với `m2compatible="true"` cho phép Ivy tìm artifact theo cấu trúc repository tương thích Maven. Với dự án doanh nghiệp, có thể thay hoặc bổ sung resolver trỏ đến repository nội bộ, proxy hoặc repository manager.

Không nên đặt thông tin xác thực nhạy cảm trực tiếp trong `ivy.xml` hoặc đưa mật khẩu vào Git. Hãy dùng cơ chế credentials và secret management phù hợp với môi trường build.

## 12. Tích hợp Ivy với Ant

Để gọi Ivy task từ buildfile, cần đưa Ivy JAR vào classpath Ant và nạp antlib. Ví dụ giả sử file Ivy đã được lưu ở `tools/ivy.jar`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory-app"
         default="resolve-dependencies"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="ivy.jar" location="tools/ivy.jar"/>
    <property name="build.dir" location="build"/>

    <path id="ivy.lib.path">
        <pathelement location="${ivy.jar}"/>
    </path>

    <taskdef resource="org/apache/ivy/ant/antlib.xml"
             uri="antlib:org.apache.ivy.ant">
        <classpath refid="ivy.lib.path"/>
    </taskdef>

    <target name="resolve-dependencies">
        <ivy:settings file="ivysettings.xml"/>
        <ivy:resolve file="ivy.xml" conf="compile"/>
        <ivy:retrieve
            pattern="${build.dir}/lib/[conf]/[artifact]-[revision].[ext]"
            conf="compile"/>
    </target>

</project>
```

Khi chạy `ant resolve-dependencies`, Ant nạp Ivy task, đọc resolver settings, giải quyết configuration `compile`, sau đó retrieve artifact vào `build/lib/compile`. Pattern sử dụng token Ivy như `[artifact]`, `[revision]` và `[ext]` để tạo tên file.

Nếu cần nhiều configuration, có thể retrieve riêng `compile`, `runtime` và `test` vào các thư mục tương ứng. Cần chọn pattern sao cho JAR không ghi đè nhau khi hai module khác organisation có cùng tên artifact.

### Dùng cachepath để tạo classpath

Thay vì copy dependency ra thư mục `build/lib`, có thể yêu cầu Ivy tạo một Ant path trỏ trực tiếp đến artifact trong cache:

```xml
<target name="compile" depends="resolve-dependencies">
    <ivy:cachepath pathid="compile.classpath" conf="compile"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

`ivy:cachepath` tạo path có thể dùng với nested `classpath` của `javac`. Đây là cách tiện lợi khi không cần quản lý bản copy dependency trong thư mục build.

## 13. Các task Ivy thường dùng

| Task | Mục đích |
|---|---|
| `ivy:settings` | Nạp cấu hình resolver/settings |
| `ivy:resolve` | Giải quyết dependency và tạo báo cáo resolve |
| `ivy:retrieve` | Copy artifact đã resolve vào thư mục theo pattern |
| `ivy:cachepath` | Tạo Ant path trỏ đến artifact trong Ivy cache |
| `ivy:report` | Tạo báo cáo dependency đã resolve |
| `ivy:publish` | Publish artifact và module descriptor lên resolver hỗ trợ publish |
| `ivy:deliver` | Tạo descriptor đã được làm đầy đủ/đóng băng thông tin revision theo workflow release |

Thông thường, `resolve` là bước đầu để xác định dependency. `retrieve` phù hợp khi muốn có JAR trong workspace; `cachepath` phù hợp khi task chỉ cần classpath. `publish` là thao tác phát hành ra repository và cần resolver có quyền ghi.

## 14. Kiểm tra kết quả resolve và xử lý lỗi

Khi Ivy không tìm được dependency, hãy kiểm tra theo thứ tự:

1. Organisation, module và revision trong `<dependency>` có đúng không?
2. Mapping `conf` có trỏ đến configuration thực sự được dependency công bố không?
3. `ivysettings.xml` có resolver phù hợp và resolver đó có được nạp trong build không?
4. Repository có chứa revision/artifact được yêu cầu không?
5. Máy build có truy cập được repository và có thông tin xác thực phù hợp không?
6. Dependency bắc cầu hoặc conflict manager có chọn revision khác dự kiến không?

| Triệu chứng | Nguyên nhân có thể | Hướng xử lý |
|---|---|---|
| Không tìm thấy module | Sai `org`, `name` hoặc `rev`; repository không có module | Kiểm tra tọa độ và nội dung repository |
| Configuration mapping không hợp lệ | Dùng tên configuration không tồn tại ở module dependency | Xem descriptor/metadata của dependency và sửa vế phải của mapping |
| JAR không xuất hiện trong thư mục retrieve | Chưa resolve, retrieve sai configuration hoặc pattern không phù hợp | Kiểm tra resolve report, `conf` và `pattern` |
| Compile thiếu class | Dependency không nằm trong configuration compile hoặc mapping sai | Đưa dependency vào `compile` và tạo classpath từ đúng configuration |
| Runtime thiếu class | Chỉ resolve compile nhưng thiếu dependency runtime hoặc dependency bắc cầu bị tắt | Resolve runtime và kiểm tra transitive dependencies |
| Phiên bản khác mong đợi | Conflict manager chọn revision khác hoặc dùng revision động | Đọc resolve report, khóa revision và cấu hình conflict rõ ràng |
| Local chạy được nhưng CI không resolve | CI thiếu quyền repository, cache hoặc settings | Cấu hình resolver/credentials giống nhau và không dựa vào cache cá nhân |
| Artifact module không publish được | `<publications>` không khớp file tạo ra hoặc resolver không hỗ trợ publish | Kiểm tra tên/type/ext, file vật lý và quyền ghi resolver |

`ivy:report` có thể giúp xem cây dependency và revision được chọn. Hãy giữ báo cáo resolve trong log CI khi cần truy nguyên khác biệt giữa các lần build.

## 15. Quy tắc quản lý dependency dễ bảo trì

- Dùng organisation và module name ổn định để định danh module của dự án.
- Khai báo các configuration phản ánh mục đích thực tế như compile, runtime và test.
- Chỉ đưa dependency vào configuration cần thiết; không để thư viện test xuất hiện trong runtime production nếu không cần.
- Ưu tiên revision cụ thể cho build release để kết quả resolve có thể tái lập.
- Kiểm tra dependency bắc cầu và loại dependency không cần thiết bằng exclude có phạm vi rõ ràng.
- Không tắt transitive nếu chưa khai báo đầy đủ các thư viện mà code cần.
- Tách module descriptor `ivy.xml` khỏi resolver settings `ivysettings.xml`.
- Không đưa credentials vào source control.
- Dùng `ivy:report` khi cần giải thích xung đột hoặc dependency được kéo vào ngoài dự kiến.
- Đảm bảo artifact trong `<publications>` thực sự được tạo bởi target `jar` trước khi publish.

## 16. Bài tập tự kiểm tra

**Bài 1.** Trong `<info>`, `revision="1.0.0"` mô tả phiên bản của module nào?

**Đáp án:** Module hiện tại được mô tả trong file `ivy.xml`. Phiên bản dependency được khai báo riêng bằng thuộc tính `rev` trong phần tử `dependency`.

**Bài 2.** Muốn JUnit chỉ xuất hiện trong quá trình kiểm thử, nên ánh xạ dependency vào configuration nào?

**Đáp án:** Configuration `test`, ví dụ `conf="test->default"`, và bảo đảm configuration này không bị đưa vào artifact production.

**Bài 3.** `conf="compile->default"` có nghĩa gì?

**Đáp án:** Configuration `compile` của module hiện tại dùng configuration `default` được công bố bởi module dependency.

**Bài 4.** File nào xác định repository mà Ivy dùng để tìm dependency?

**Đáp án:** Thông thường là `ivysettings.xml` hoặc cấu hình settings được nạp vào Ivy. `ivy.xml` mô tả module và dependency, không phải nơi định nghĩa resolver mặc định.

**Bài 5.** `ivy:retrieve` và `ivy:cachepath` khác nhau thế nào?

**Đáp án:** `retrieve` copy artifact đã resolve vào workspace theo pattern; `cachepath` tạo một Ant path trỏ đến artifact trong Ivy cache để task như `javac` sử dụng.

## Kết luận

`ivy.xml` mô tả module hiện tại, các configuration, artifact được công bố và dependency mà dự án cần. Configuration mapping quyết định dependency nào được dùng khi compile, runtime hoặc test; Ivy có thể giải quyết cả dependency bắc cầu và tạo classpath hoặc retrieve JAR cho Ant. Khi giữ descriptor tách biệt với resolver settings, dùng revision rõ ràng và kiểm tra resolve report, việc quản lý thư viện Java trở nên có tổ chức và nhất quán giữa máy phát triển và CI.

