# Giới thiệu Apache Ivy như phần mở rộng quản lý dependency cho Ant

Khi một dự án Java bắt đầu sử dụng thư viện bên ngoài, việc tự tải từng tệp JAR rồi chép vào thư mục `lib` nhanh chóng trở nên khó quản lý. Bạn phải nhớ phiên bản của từng thư viện, tìm thêm các thư viện phụ thuộc của chúng, cập nhật classpath và bảo đảm mọi máy phát triển đều có cùng bộ tệp.

**Apache Ivy** là công cụ quản lý dependency có thể tích hợp trực tiếp với Apache Ant. Ivy đọc mô tả dependency của dự án, tìm và tải các module cần thiết từ repository, xử lý dependency bắc cầu, lưu artifact vào cache và cung cấp chúng cho các task build của Ant.

Ivy bổ sung khả năng quản lý thư viện cho Ant. Ant vẫn điều phối các bước như biên dịch, kiểm thử, đóng gói và chạy ứng dụng; Ivy đảm nhận việc xác định, phân giải và lấy các dependency mà những bước đó cần.

Sau bài học, bạn có thể:

- Giải thích vai trò của Ivy trong một dự án Ant.
- Khai báo dependency bằng tệp `ivy.xml`.
- Cấu hình repository bằng `ivysettings.xml`.
- Tích hợp các task Ivy vào `build.xml`.
- Phân biệt `resolve`, `retrieve` và `cachepath`.
- Đưa dependency vào classpath của task `<javac>`.
- Hiểu dependency bắc cầu, phiên bản thư viện và cache.
- Nhận biết các lỗi thường gặp khi Ivy không tìm được dependency.

## 1. Vì sao Ant cần một công cụ quản lý dependency?

Ant là công cụ tự động hóa build. Ant có task để biên dịch Java, sao chép tài nguyên, tạo JAR, chạy chương trình và thực hiện nhiều công việc khác. Tuy nhiên, Ant không tự cung cấp một mô hình quản lý dependency đầy đủ như một dependency manager chuyên dụng.

Giả sử ứng dụng sử dụng thư viện `commons-lang3`. Nếu quản lý thủ công, bạn cần:

1. Tìm đúng phiên bản thư viện.
2. Tải tệp JAR từ một nguồn đáng tin cậy.
3. Chép JAR vào thư mục `lib` của dự án.
4. Thêm JAR vào classpath khi biên dịch và chạy.
5. Cập nhật tệp JAR khi muốn nâng cấp phiên bản.
6. Tìm và bổ sung các thư viện khác mà thư viện này cần.

Khi có nhiều thư viện, quy trình này tạo ra một số vấn đề:

- Mỗi thành viên nhóm có thể đang dùng các phiên bản JAR khác nhau.
- Tệp JAR có thể bị chép thiếu hoặc đặt sai vị trí.
- Các dependency bắc cầu không được quản lý tập trung.
- Buildfile chứa nhiều đường dẫn thủ công và khó cập nhật.
- Việc tái tạo môi trường build trên máy mới mất thời gian.

Ivy giải quyết phần quản lý dependency bằng cách mô tả thư viện theo module và phiên bản, sau đó tự động tìm các artifact cần thiết từ repository.

## 2. Apache Ivy là gì?

Apache Ivy là một dependency manager được thiết kế để hoạt động tốt với Apache Ant. Ivy sử dụng metadata để mô tả module, cấu hình và các dependency của module đó. Từ metadata này, Ivy có thể phân giải cây dependency và cung cấp các artifact cho build.

Một số chức năng chính:

- **Resolve:** tìm các dependency trực tiếp và bắc cầu, xác định phiên bản phù hợp và tải metadata cần thiết.
- **Retrieve:** sao chép artifact đã phân giải từ cache vào thư mục của dự án theo mẫu đường dẫn.
- **Cache:** lưu metadata và artifact đã tải để có thể dùng lại ở những lần build sau.
- **Repository resolution:** tìm module trong một hoặc nhiều repository được cấu hình.
- **Dependency report:** tạo báo cáo để xem cây dependency và kết quả phân giải.
- **Publish:** xuất bản module và metadata của nó lên repository nếu quy trình dự án cần chia sẻ thư viện nội bộ.

Ivy không thay thế Ant. Hai công cụ có nhiệm vụ bổ sung cho nhau:

```text
build.xml
   |
   +-- Ant điều phối các target
   |      |
   |      +-- resolve dependency bằng Ivy
   |      +-- biên dịch bằng javac
   |      +-- chạy kiểm thử
   |      +-- đóng gói JAR
   |
   +-- ivy.xml mô tả dependency của module
   |
   +-- ivysettings.xml mô tả repository và cách tìm module
```

Trong một dự án nhỏ, bạn có thể vẫn dùng Ant để biên dịch và đóng gói như trước, chỉ bổ sung Ivy ở bước lấy thư viện.

## 3. Các khái niệm cơ bản của Ivy

### 3.1. Module

Trong Ivy, một đơn vị phần mềm có thể được mô tả như một module. Module có thông tin định danh, thường gồm:

- `organisation`: tổ chức hoặc nhóm sở hữu module.
- `module`: tên module.
- `revision`: phiên bản của module.

Ví dụ, một dependency có thể được nhận diện bằng bộ thông tin:

```text
organisation: org.apache.commons
module:       commons-lang3
revision:     3.14.0
```

Các giá trị này giúp Ivy xác định chính xác thư viện cần tìm trong repository.

### 3.2. Artifact

Artifact là tệp thực tế được cung cấp bởi một module, thường là JAR, ZIP hoặc một tệp phân phối khác. Metadata cho Ivy biết artifact nào thuộc module và vị trí cần lấy.

Ví dụ:

```text
commons-lang3-3.14.0.jar
```

Module và artifact có liên quan nhưng không đồng nghĩa. Module là đơn vị được mô tả và quản lý; artifact là tệp mà build có thể tải về và sử dụng.

### 3.3. Dependency trực tiếp và bắc cầu

Dependency trực tiếp là thư viện được dự án khai báo sử dụng. Dependency bắc cầu là thư viện mà một dependency khác lại cần.

Ví dụ:

```text
Ứng dụng
   |
   +-- Thư viện A
          |
          +-- Thư viện B
          |
          +-- Thư viện C
```

Ứng dụng chỉ khai báo thư viện A, nhưng để sử dụng A, Ivy có thể cần lấy thêm B và C. Quá trình resolve sẽ xem xét cả các dependency bắc cầu theo metadata và cấu hình của module.

Đây là lợi ích quan trọng của dependency manager: dự án không cần tự liệt kê thủ công mọi JAR nằm sâu trong cây dependency.

### 3.4. Repository

Repository là nơi lưu metadata và artifact của module. Repository có thể là kho công khai, kho nội bộ của tổ chức hoặc một vị trí lưu trữ trên máy.

Ivy có thể làm việc với nhiều loại resolver để tìm module trong repository. Cấu hình resolver xác định nơi tìm, thứ tự tìm và cách ánh xạ tên module thành đường dẫn hoặc URL.

## 4. Cài đặt Ivy và tích hợp với Ant

Để Ant nhận biết các task Ivy như `ivy:resolve`, `ivy:retrieve` và `ivy:cachepath`, JAR của Ivy phải nằm trên classpath mà Ant sử dụng.

Một cách cài đặt thường gặp:

1. Tải bản phân phối Apache Ivy phù hợp với môi trường dự án.
2. Lấy tệp `ivy-<version>.jar` từ bản phân phối.
3. Đặt JAR vào thư mục `lib` của Ant (thường là `${ANT_HOME}/lib`) hoặc cấu hình classpath để Ant nạp được JAR đó.
4. Mở terminal mới nếu vừa thay đổi môi trường.
5. Kiểm tra Ant và JDK đã được cấu hình.

Kiểm tra phiên bản Ant:

```bash
ant -version
```

Có thể kiểm tra JDK:

```bash
java -version
javac -version
```

Khi Ivy đã nằm trên classpath của Ant, có thể khai báo namespace Antlib trong `build.xml`:

```xml
<project name="hello-ant" default="resolve"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <target name="resolve">
        <ivy:resolve />
    </target>
</project>
```

Namespace `ivy` cho phép gọi các task của Ivy bằng cú pháp `ivy:<tên-task>`. Nếu Ant báo không tìm thấy task hoặc namespace, hãy kiểm tra JAR Ivy có được Ant nạp hay không, phiên bản Ivy có tương thích với Ant/JDK hay không và namespace có được khai báo đúng không.

## 5. Khai báo dependency trong `ivy.xml`

Tệp `ivy.xml` là module descriptor của dự án. Nó mô tả module hiện tại, các configuration và những dependency mà module cần.

Ví dụ tối giản:

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="hello-ant" />

    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0" />
    </dependencies>
</ivy-module>
```

Trong ví dụ:

- `<ivy-module>` là phần tử gốc của descriptor Ivy.
- `<info>` mô tả module của chính dự án.
- `organisation` xác định tổ chức sở hữu module.
- `module` là tên module.
- `<dependencies>` chứa các dependency trực tiếp.
- `<dependency>` chỉ định tổ chức, tên module và revision cần dùng.

Dependency `commons-lang3` có revision được chỉ định là `3.14.0`. Khi resolve, Ivy tìm module tương ứng trong các repository đã cấu hình và xử lý các dependency mà module đó khai báo.

### 5.1. Vị trí của `ivy.xml`

Theo quy ước đơn giản, đặt `ivy.xml` ở thư mục gốc dự án, cạnh `build.xml`:

```text
hello-ant/
├── build.xml
├── ivy.xml
├── ivysettings.xml
├── src/
└── build/
```

Task `ivy:resolve` mặc định tìm descriptor theo quy ước của Ivy, nhưng nên chỉ rõ `file="ivy.xml"` trong ví dụ và dự án cần sự rõ ràng:

```xml
<ivy:resolve file="ivy.xml" />
```

### 5.2. Khai báo nhiều dependency

Một dự án có thể khai báo nhiều module:

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="hello-ant" />

    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0" />
        <dependency org="com.google.guava"
                    name="guava"
                    rev="33.0.0-jre" />
    </dependencies>
</ivy-module>
```

Mỗi dependency có một bộ định danh riêng. Ivy resolve cả hai module và các dependency bắc cầu của chúng theo metadata.

### 5.3. Revision và cách chọn phiên bản

Thuộc tính `rev` chỉ định revision cần dùng. Ví dụ:

```xml
<dependency org="org.apache.commons"
            name="commons-lang3"
            rev="3.14.0" />
```

Với dự án cần build ổn định, nên chọn revision cụ thể đã được kiểm thử. Các revision động như `latest.integration` hoặc dải phiên bản có thể khiến kết quả resolve thay đổi theo thời điểm hoặc trạng thái repository.

Nếu sử dụng revision động, hãy hiểu rằng hai lần build ở hai thời điểm khác nhau có thể nhận phiên bản khác nhau nếu repository đã có bản mới phù hợp. Khi cần tái lập build, hãy cố định phiên bản và quản lý thay đổi dependency có chủ đích.

## 6. Configuration trong Ivy

Configuration mô tả một nhóm dependency phục vụ một mục đích nhất định trong module. Một dự án Java thường cần thư viện khác nhau cho biên dịch, chạy ứng dụng và kiểm thử.

Ví dụ khai báo:

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="hello-ant" />

    <configurations>
        <conf name="compile" description="Dependencies needed to compile" />
        <conf name="runtime" extends="compile"
              description="Dependencies needed at runtime" />
        <conf name="test" extends="runtime"
              description="Dependencies needed for tests" />
    </configurations>

    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0"
                    conf="compile->default" />
    </dependencies>
</ivy-module>
```

Trong đó:

- `compile` là configuration cho dependency cần khi biên dịch.
- `runtime` kế thừa `compile`, đồng thời có thể chứa dependency chỉ cần khi chạy.
- `test` kế thừa `runtime`, đồng thời có thể bổ sung dependency dành cho kiểm thử.
- `conf` trên dependency ánh xạ configuration của module hiện tại sang configuration của module được phụ thuộc.

Trong ví dụ, `compile->default` có nghĩa dependency được đưa vào configuration `compile` của dự án bằng configuration `default` của module được tham chiếu. Cấu hình mapping thực tế cần phù hợp với metadata của module ở repository.

### 6.1. Vì sao nên tách compile, runtime và test?

Không phải thư viện nào cũng cần ở mọi giai đoạn. Ví dụ:

| Configuration | Mục đích | Ví dụ |
|---|---|---|
| `compile` | Cung cấp lớp và kiểu dữ liệu cần thiết để biên dịch. | Thư viện tiện ích được mã nguồn import. |
| `runtime` | Cung cấp lớp cần thiết khi chạy ứng dụng. | Driver hoặc thư viện được nạp trong thời gian chạy. |
| `test` | Cung cấp thư viện cho mã kiểm thử. | Framework test và thư viện hỗ trợ test. |

Tách configuration giúp classpath của mỗi bước chỉ chứa những dependency cần thiết. Điều này làm rõ sự phụ thuộc thật sự của ứng dụng và giảm nguy cơ một thư viện chỉ có trong môi trường phát triển nhưng lại bị thiếu khi chạy.

## 7. Cấu hình repository trong `ivysettings.xml`

Ivy cần biết nơi tìm module và artifact. Tệp `ivysettings.xml` mô tả resolver và resolver mặc định.

Ví dụ dùng repository tương thích Maven 2:

```xml
<ivysettings>
    <settings defaultResolver="central" />

    <resolvers>
        <ibiblio name="central" m2compatible="true" />
    </resolvers>
</ivysettings>
```

Trong đó:

- `<settings>` chọn resolver mặc định có tên `central`.
- `<resolvers>` chứa danh sách resolver.
- `<ibiblio>` khai báo resolver kiểu Maven repository.
- `m2compatible="true"` bật cách ánh xạ đường dẫn tương thích Maven 2.

Khi chạy Ivy, resolver này được dùng để tìm module trong repository đã cấu hình. Với dự án doanh nghiệp, bạn có thể cần cấu hình repository nội bộ thay cho hoặc bên cạnh repository công khai.

### 7.1. Repository nội bộ dạng URL

Một resolver URL có thể khai báo mẫu vị trí metadata và artifact. Ví dụ khái quát:

```xml
<ivysettings>
    <settings defaultResolver="company" />

    <resolvers>
        <url name="company">
            <ivy pattern="https://repo.example.com/ivy/[organisation]/[module]/[revision]/ivy.xml" />
            <artifact pattern="https://repo.example.com/artifacts/[organisation]/[module]/[revision]/[artifact]-[revision].[ext]" />
        </url>
    </resolvers>
</ivysettings>
```

Các mẫu trong ví dụ minh họa cách ánh xạ tổ chức, module, revision và tên artifact vào đường dẫn. Cấu trúc URL thực tế phải khớp với cách repository nội bộ lưu metadata và tệp.

### 7.2. Kết hợp nhiều resolver

Có thể dùng resolver chain để thử nhiều repository theo thứ tự:

```xml
<ivysettings>
    <settings defaultResolver="main-chain" />

    <resolvers>
        <chain name="main-chain">
            <ibiblio name="central" m2compatible="true" />
            <url name="company">
                <ivy pattern="https://repo.example.com/ivy/[organisation]/[module]/[revision]/ivy.xml" />
                <artifact pattern="https://repo.example.com/artifacts/[organisation]/[module]/[revision]/[artifact]-[revision].[ext]" />
            </url>
        </chain>
    </resolvers>
</ivysettings>
```

Trong cấu hình này, Ivy thử resolver theo thứ tự trong chain. Hãy đặt các repository theo chính sách của tổ chức, đặc biệt nếu thư viện nội bộ có cùng định danh với một module ở repository công khai.

### 7.3. Không đưa thông tin xác thực vào buildfile công khai

Repository nội bộ có thể yêu cầu tài khoản hoặc token. Không nên ghi mật khẩu trực tiếp vào `build.xml`, `ivy.xml` hoặc tệp được commit công khai. Hãy sử dụng cơ chế bảo mật của môi trường build, tệp cấu hình được bảo vệ hoặc secret store mà hệ thống CI cung cấp.

## 8. Tích hợp task Ivy vào `build.xml`

Khi Ivy đã được Ant nạp và descriptor/settings đã có, bạn có thể gọi task Ivy trong target.

Ví dụ:

```xml
<project name="hello-ant" default="compile"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />

    <target name="resolve-dependencies">
        <ivy:settings file="ivysettings.xml" />
        <ivy:resolve file="ivy.xml" />
    </target>

    <target name="compile" depends="resolve-dependencies">
        <mkdir dir="${classes.dir}" />
        <ivy:cachepath pathid="compile.classpath" conf="compile" />

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath" />
        </javac>
    </target>
</project>
```

Luồng thực hiện:

1. Target `resolve-dependencies` nạp cấu hình repository từ `ivysettings.xml`.
2. `ivy:resolve` đọc `ivy.xml` và phân giải các dependency.
3. Target `compile` chỉ chạy sau khi resolve hoàn tất.
4. `ivy:cachepath` tạo một Ant path có tên `compile.classpath` từ các artifact đã resolve cho configuration `compile`.
5. Task `javac` tham chiếu path đó để tìm các lớp thư viện khi biên dịch.

`pathid` là tên định danh của path trong Ant; `refid` của phần tử `<classpath>` trỏ đến path đó. Ivy không tự thay thế task `javac`: Ivy cung cấp classpath, còn `javac` vẫn thực hiện biên dịch.

## 9. Phân biệt `resolve`, `retrieve` và `cachepath`

Ba task này thường xuất hiện cùng nhau nhưng có mục đích khác nhau.

### 9.1. `ivy:resolve`

`resolve` đọc descriptor, tìm các dependency trực tiếp và bắc cầu, chọn revision phù hợp, lấy metadata cần thiết và lưu kết quả phân giải trong cache của Ivy.

```xml
<ivy:settings file="ivysettings.xml" />
<ivy:resolve file="ivy.xml" />
```

Resolve không có nghĩa là mọi JAR đã được chép vào thư mục `lib` của dự án. Kết quả phân giải và artifact được quản lý trong cache của Ivy.

### 9.2. `ivy:retrieve`

`retrieve` sao chép các artifact đã resolve từ cache vào một thư mục của dự án theo mẫu `pattern`:

```xml
<target name="retrieve-dependencies" depends="resolve-dependencies">
    <ivy:retrieve pattern="lib/[artifact]-[revision].[ext]"
                  conf="compile" />
</target>
```

Ví dụ, artifact có thể được đặt thành:

```text
lib/
└── commons-lang3-3.14.0.jar
```

`pattern` sử dụng token như `[artifact]`, `[revision]` và `[ext]` để tạo đường dẫn đích. Có thể thêm `[organisation]`, `[module]` hoặc `[conf]` để tránh trùng tên khi có nhiều module hoặc configuration.

Ví dụ pattern chi tiết hơn:

```xml
<ivy:retrieve pattern="lib/[organisation]/[module]/[revision]/[artifact].[ext]" />
```

Retrieve hữu ích khi dự án hoặc công cụ khác cần JAR nằm trong thư mục dự án. Tuy nhiên, nó tạo bản sao từ cache sang thư mục retrieve; nếu chỉ cần classpath cho task Ant, có thể không cần bước này.

### 9.3. `ivy:cachepath`

`cachepath` tạo một path Ant tham chiếu trực tiếp đến artifact trong cache:

```xml
<ivy:cachepath pathid="compile.classpath" conf="compile" />
```

Sau đó dùng path trong task:

```xml
<javac srcdir="src" destdir="build/classes">
    <classpath refid="compile.classpath" />
</javac>
```

Cachepath tiện khi các task Ant cần classpath nhưng bạn không muốn chép dependency vào thư mục `lib` của dự án.

### 9.4. Bảng so sánh

| Task | Mục đích | Kết quả chính |
|---|---|---|
| `ivy:resolve` | Phân giải cây dependency và xác định artifact/revision. | Kết quả resolve và dữ liệu trong cache Ivy. |
| `ivy:retrieve` | Sao chép artifact đã resolve vào thư mục dự án. | Các JAR hoặc artifact trong thư mục retrieve. |
| `ivy:cachepath` | Tạo Ant path tham chiếu artifact trong cache. | Một path có thể gắn vào classpath của task. |

Không bắt buộc phải chạy cả retrieve lẫn cachepath. Chọn theo cách dự án cần cung cấp dependency cho các task sau.

## 10. Sử dụng dependency khi chạy ứng dụng

Classpath dùng khi biên dịch và classpath dùng khi chạy có thể khác nhau. Nếu ứng dụng cần một thư viện ở runtime, dependency đó phải được đưa vào classpath lúc chạy hoặc được đóng gói theo chiến lược phân phối phù hợp.

Ví dụ tạo runtime path:

```xml
<target name="run" depends="resolve-dependencies">
    <ivy:cachepath pathid="runtime.classpath" conf="runtime" />

    <java classname="com.example.Main" fork="true">
        <classpath>
            <pathelement location="${classes.dir}" />
            <path refid="runtime.classpath" />
        </classpath>
    </java>
</target>
```

Ở đây:

- `runtime.classpath` chứa các dependency thuộc configuration `runtime`.
- `classes.dir` chứa lớp của ứng dụng đã biên dịch.
- Task `<java>` khởi chạy lớp `com.example.Main` với cả lớp ứng dụng và thư viện runtime trên classpath.

Nếu dependency chỉ được đưa vào classpath của `javac` mà không có ở runtime, chương trình có thể biên dịch thành công nhưng thất bại khi chạy với lỗi thiếu lớp hoặc thiếu phương thức.

## 11. Dependency bắc cầu và xung đột phiên bản

Khi một module phụ thuộc vào module khác, module được tham chiếu có thể khai báo thêm dependency. Ivy tiếp tục phân giải các module đó để xây dựng cây dependency.

Ví dụ:

```text
hello-ant
   |
   +-- library-a 1.0
          |
          +-- common-utils 2.0

   +-- library-b 2.0
          |
          +-- common-utils 3.0
```

Hai nhánh yêu cầu hai revision khác nhau của `common-utils`. Đây là tình huống xung đột phiên bản. Ivy có các conflict manager và quy tắc giải quyết xung đột để xác định revision cần dùng theo cấu hình.

Khi gặp xung đột, đừng chỉ nhìn thấy build resolve thành công rồi mặc định mọi thứ đều ổn. Hãy xem dependency report để biết revision nào được chọn và kiểm tra thư viện đó có tương thích với các module phụ thuộc hay không.

### 11.1. Xem dependency report

Ivy có task tạo báo cáo dependency:

```xml
<target name="dependency-report" depends="resolve-dependencies">
    <ivy:report todir="build/ivy-report" />
</target>
```

Báo cáo giúp xem module nào được resolve, dependency bắc cầu và các revision liên quan. Khi dự án có nhiều thư viện, report là công cụ hữu ích để điều tra vì sao một JAR xuất hiện hoặc vì sao một revision được chọn.

### 11.2. Cố định phiên bản và kiểm soát thay đổi

Với build cần tái lập, nên:

- Khai báo revision cụ thể cho dependency quan trọng.
- Xem report khi nâng cấp hoặc thêm dependency.
- Kiểm thử ứng dụng sau khi thay revision.
- Tránh dùng revision động trong build phát hành nếu không có cơ chế kiểm soát kết quả resolve.
- Giữ cấu hình resolver nhất quán giữa máy phát triển và CI.

Ivy quản lý quá trình phân giải; chất lượng lựa chọn phiên bản và khả năng tương thích vẫn cần được dự án xác nhận.

## 12. Cache của Ivy

Ivy lưu metadata và artifact đã tải trong cache. Khi một dependency đã có trong cache và vẫn đáp ứng chính sách resolve, Ivy có thể tái sử dụng dữ liệu thay vì tải lại từ repository.

Lợi ích:

- Giảm thời gian build khi dependency không thay đổi.
- Giảm lượng dữ liệu tải qua mạng.
- Hỗ trợ build trong môi trường mạng không ổn định nếu các artifact cần thiết đã có sẵn trong cache.

Cache thường nằm trong thư mục người dùng hoặc vị trí được cấu hình. Có thể xem vị trí cache trong log hoặc cấu hình Ivy. Không nên giả định cache nằm cùng thư mục dự án.

### 12.1. Cache không phải thư mục output của dự án

Phân biệt ba vị trí:

| Vị trí | Vai trò |
|---|---|
| Repository | Nguồn chính thức chứa module và artifact. |
| Ivy cache | Bản metadata/artifact Ivy đã lấy về và quản lý. |
| Retrieve directory | Bản artifact được sao chép vào thư mục dự án theo pattern. |

Nếu dùng `cachepath`, classpath tham chiếu artifact trong cache. Nếu dùng `retrieve`, JAR được sao chép sang thư mục dự án. Xóa thư mục retrieve không nhất thiết xóa cache Ivy; xóa cache có thể khiến lần resolve tiếp theo phải tải lại artifact.

### 12.2. Khi nào cần làm mới cache?

Nếu repository đã cập nhật metadata hoặc dependency có revision động, Ivy có các cơ chế kiểm tra và làm mới cache. Việc làm mới quá thường xuyên có thể làm build chậm và tăng tải repository.

Khi nghi ngờ cache không còn phản ánh repository, hãy kiểm tra log resolve, chính sách cache và cấu hình resolver. Chỉ xóa cache khi đã xác định đây là nguyên nhân hoặc khi cần làm mới có chủ đích; không nên xóa cache như bước mặc định của mọi lần build.

## 13. Xuất bản module bằng Ivy

Ngoài việc lấy dependency, Ivy còn có thể xuất bản module của dự án lên repository. Quy trình này thường gồm:

1. Chuẩn bị artifact cần phát hành, ví dụ JAR.
2. Chuẩn bị descriptor Ivy mô tả module và dependency của nó.
3. Cấu hình resolver có quyền ghi vào repository đích.
4. Gọi task `ivy:publish` với revision và resolver phù hợp.

Ví dụ minh họa cấu trúc task:

```xml
<target name="publish-module" depends="jar">
    <ivy:publish resolver="company-release"
                 pubrevision="1.0.0"
                 status="release">
        <artifacts pattern="${dist.dir}/[artifact].[ext]" />
    </ivy:publish>
</target>
```

Đây là khung minh họa; resolver `company-release` phải được khai báo trong `ivysettings.xml`, artifact pattern phải khớp với tệp thực tế và descriptor cần có metadata phù hợp. Việc publish thường là thao tác ghi lên repository dùng chung, nên chỉ đưa vào quy trình phát hành đã được kiểm soát.

## 14. Ví dụ dự án Ant hoàn chỉnh sử dụng Ivy

Một dự án mẫu có cấu trúc:

```text
hello-ant/
├── build.xml
├── ivy.xml
├── ivysettings.xml
└── src/
    └── com/
        └── example/
            └── Main.java
```

### 14.1. Tệp `ivy.xml`

```xml
<ivy-module version="2.0">
    <info organisation="com.example"
          module="hello-ant" />

    <configurations>
        <conf name="compile" description="Compile dependencies" />
        <conf name="runtime" extends="compile"
              description="Runtime dependencies" />
    </configurations>

    <dependencies>
        <dependency org="org.apache.commons"
                    name="commons-lang3"
                    rev="3.14.0"
                    conf="compile->default" />
    </dependencies>
</ivy-module>
```

### 14.2. Tệp `ivysettings.xml`

```xml
<ivysettings>
    <settings defaultResolver="central" />
    <resolvers>
        <ibiblio name="central" m2compatible="true" />
    </resolvers>
</ivysettings>
```

### 14.3. Tệp `build.xml`

```xml
<project name="hello-ant" default="jar"
         xmlns:ivy="antlib:org.apache.ivy.ant">

    <property name="src.dir" location="src" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="dist.dir" location="${build.dir}/dist" />

    <target name="resolve-dependencies">
        <ivy:settings file="ivysettings.xml" />
        <ivy:resolve file="ivy.xml" />
    </target>

    <target name="init">
        <mkdir dir="${classes.dir}" />
        <mkdir dir="${dist.dir}" />
    </target>

    <target name="compile" depends="resolve-dependencies,init">
        <ivy:cachepath pathid="compile.classpath" conf="compile" />

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="compile.classpath" />
        </javac>
    </target>

    <target name="jar" depends="compile">
        <jar destfile="${dist.dir}/hello-ant.jar"
             basedir="${classes.dir}" />
    </target>

    <target name="report" depends="resolve-dependencies">
        <ivy:report todir="${build.dir}/ivy-report" />
    </target>

    <target name="clean">
        <delete dir="${build.dir}" />
    </target>
</project>
```

### 14.4. Mã nguồn `Main.java`

```java
package com.example;

import org.apache.commons.lang3.StringUtils;

public class Main {
    public static void main(String[] args) {
        String message = "  Hello from Ant and Ivy  ";
        System.out.println(StringUtils.trim(message));
    }
}
```

Mã nguồn sử dụng `StringUtils` từ thư viện Commons Lang. Ivy resolve dependency và tạo classpath; Ant truyền classpath đó cho `javac`.

### 14.5. Chạy build

Kiểm tra công cụ:

```bash
ant -version
java -version
javac -version
```

Biên dịch và đóng gói:

```bash
ant jar
```

Tạo báo cáo dependency:

```bash
ant report
```

Lấy các JAR về thư mục dự án thay vì chỉ dùng cachepath có thể được thực hiện bằng target riêng:

```xml
<target name="retrieve-dependencies" depends="resolve-dependencies">
    <ivy:retrieve pattern="lib/[artifact]-[revision].[ext]"
                  conf="compile" />
</target>
```

Sau khi retrieve, có thể tạo Ant path từ các JAR trong `lib` nếu một bước build hoặc công cụ khác cần đọc trực tiếp thư mục đó.

## 15. Các lỗi thường gặp khi dùng Ivy

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant báo không tìm thấy task `ivy:resolve` | Ivy JAR chưa có trên classpath của Ant hoặc namespace chưa khai báo đúng. | Đặt Ivy JAR vào Ant lib/classpath và kiểm tra `xmlns:ivy`. |
| Không tìm thấy module hoặc revision | Sai `organisation`, `module`, `rev` hoặc repository không chứa module đó. | Kiểm tra tọa độ dependency và metadata trong repository. |
| Không truy cập được repository | Mất mạng, proxy, DNS, chứng chỉ TLS hoặc quyền truy cập. | Kiểm tra kết nối và cấu hình mạng của môi trường chạy Ant. |
| Resolve thành công nhưng `javac` không tìm thấy lớp | Classpath chưa được gắn vào task `javac` hoặc chọn sai configuration. | Tạo `ivy:cachepath` với configuration đúng và tham chiếu bằng `refid`. |
| Build chạy được nhưng ứng dụng lỗi khi chạy | Dependency runtime không có trong classpath lúc chạy. | Resolve configuration `runtime` và thêm path vào task `<java>` hoặc cách đóng gói phù hợp. |
| Thiếu dependency bắc cầu | Module metadata thiếu thông tin hoặc dependency bị loại trừ/cấu hình sai. | Xem Ivy report và kiểm tra descriptor của module liên quan. |
| Phiên bản được resolve không như mong đợi | Có nhiều revision hoặc quy tắc conflict manager/mapping ảnh hưởng. | Xem report, cố định revision và kiểm tra cấu hình resolve. |
| Tải lại thư viện liên tục | Cache không được giữ, bị xóa hoặc chính sách kiểm tra thay đổi metadata quá thường xuyên. | Kiểm tra vị trí cache và chính sách cache của Ivy. |
| Retrieve không tạo JAR ở vị trí dự kiến | Pattern hoặc configuration của retrieve không phù hợp. | Kiểm tra `pattern`, `conf` và kết quả resolve. |
| Build khác nhau giữa máy phát triển và CI | Resolver, cache, cấu hình hoặc revision động khác nhau. | Dùng cùng settings, revision cụ thể và repository nhất quán. |

### 15.1. Đọc log để tìm nguyên nhân

Khi resolve thất bại, hãy tìm trong log:

- Module và revision mà Ivy đang tìm.
- Resolver được thử và URL/đường dẫn tương ứng.
- Lỗi truy cập repository hay lỗi không tìm thấy metadata/artifact.
- Dependency nào yêu cầu revision gây xung đột.

Đừng vội sửa classpath nếu lỗi xảy ra ngay ở bước resolve. Ngược lại, nếu resolve đã thành công mà compiler báo thiếu package, hãy kiểm tra path được tạo và configuration mà task `javac` sử dụng.

## 16. Khi nào nên dùng Ivy?

Ivy phù hợp khi dự án đã dùng Ant và cần quản lý thư viện có hệ thống mà không muốn tự xử lý từng JAR. Ivy đặc biệt hữu ích khi:

- Dự án có nhiều dependency trực tiếp và bắc cầu.
- Cần lấy thư viện từ repository công khai hoặc nội bộ.
- Cần tách dependency compile, runtime và test.
- Nhiều máy phát triển hoặc máy CI cần dùng cùng bộ dependency.
- Muốn xem báo cáo và kiểm soát quá trình resolve.
- Muốn xuất bản module nội bộ lên repository dùng chung.

Với dự án chỉ có một hoặc hai JAR ổn định, quản lý thủ công có thể vẫn đủ. Khi dependency tăng lên, Ivy giảm công việc tải, lưu, cập nhật và nối classpath bằng tay.

Ivy được thiết kế để tích hợp với Ant. Nếu một dự án mới đang chọn hệ thống build từ đầu, cũng nên xem xét yêu cầu của nhóm và các công cụ build hiện đại khác. Mục tiêu của bài học này là hiểu cách Ivy bổ sung dependency management cho quy trình Ant hiện có.

## 17. Bài thực hành

Tạo dự án:

```text
ivy-lab/
├── build.xml
├── ivy.xml
├── ivysettings.xml
└── src/
    └── com/
        └── example/
            └── Main.java
```

Thực hiện các bước:

1. Cài Ivy và bảo đảm Ant có thể nạp Ivy JAR.
2. Tạo `ivy.xml` với module `com.example:ivy-lab`.
3. Khai báo một dependency có revision cụ thể.
4. Tạo `ivysettings.xml` với resolver phù hợp.
5. Tạo target `resolve-dependencies` để gọi `ivy:settings` và `ivy:resolve`.
6. Tạo `ivy:cachepath` cho configuration `compile`.
7. Gắn path đó vào classpath của task `javac`.
8. Tạo target `jar` để đóng gói lớp đã biên dịch.
9. Tạo target `report` để sinh dependency report.
10. Thêm target `retrieve-dependencies` và quan sát JAR được sao chép vào thư mục `lib`.

Sau khi chạy thành công, hãy thử thay đổi revision của dependency, resolve lại và xem report thay đổi như thế nào. Tiếp theo, thử tách configuration `runtime` và `test` để mỗi target chỉ nhận dependency cần thiết.

### Câu hỏi tự kiểm tra

1. Apache Ivy bổ sung chức năng gì cho Apache Ant?
2. `ivy.xml` khác `ivysettings.xml` ở điểm nào?
3. Bộ định danh module thường gồm những thông tin nào?
4. Dependency bắc cầu là gì?
5. `ivy:resolve` có tự động chép tất cả JAR vào thư mục `lib` của dự án không?
6. Khác biệt giữa `ivy:retrieve` và `ivy:cachepath` là gì?
7. Vì sao cần đưa path do Ivy tạo vào classpath của `javac`?
8. Configuration `compile`, `runtime` và `test` giúp ích gì?
9. Vì sao revision cụ thể thường phù hợp hơn revision động cho build phát hành?
10. Khi resolve thành công nhưng chương trình thiếu lớp lúc chạy, cần kiểm tra configuration nào?

### Đáp án gợi ý

- Ivy quản lý dependency, resolve module và dependency bắc cầu, lấy artifact từ repository và cung cấp classpath cho Ant.
- `ivy.xml` mô tả module và dependency; `ivysettings.xml` cấu hình resolver, repository và chính sách tìm module.
- `organisation`, `module` và `revision`.
- Là dependency mà một dependency khác khai báo cần.
- Không. Resolve tạo kết quả phân giải và quản lý artifact trong cache; retrieve mới sao chép artifact ra thư mục dự án.
- Retrieve tạo bản sao artifact theo pattern; cachepath tạo Ant path tham chiếu trực tiếp artifact trong cache.
- Vì `javac` cần biết vị trí các JAR chứa lớp mà mã nguồn import.
- Chúng tách thư viện cần cho biên dịch, chạy ứng dụng và kiểm thử.
- Revision cụ thể giúp các lần build nhận cùng phiên bản, dễ tái lập và kiểm thử.
- Kiểm tra `runtime` classpath và cách task chạy ứng dụng nhận dependency.

## Kết luận

Apache Ivy bổ sung quản lý dependency cho Apache Ant. Dự án khai báo module và dependency trong `ivy.xml`, cấu hình nơi tìm thư viện trong `ivysettings.xml`, rồi gọi các task Ivy từ `build.xml`. `resolve` phân giải dependency, `retrieve` sao chép artifact vào thư mục dự án và `cachepath` tạo Ant path tham chiếu artifact trong cache. Khi kết hợp configuration phù hợp với classpath của `javac` và runtime, Ivy giúp quy trình build quản lý thư viện nhất quán, dễ tái tạo và dễ bảo trì hơn.
