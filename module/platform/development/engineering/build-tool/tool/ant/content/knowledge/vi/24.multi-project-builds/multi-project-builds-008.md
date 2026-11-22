# Tách cấu hình dùng chung với cấu hình riêng của từng dự án trong Apache Ant

Khi một tổ chức có nhiều ứng dụng Java, các dự án thường dùng chung quy trình biên dịch, kiểm thử, đóng gói và kiểm tra mã. Tuy nhiên, mỗi dự án vẫn có những giá trị riêng như thư mục source, tên artifact, thư viện, phiên bản Java hoặc thư mục đầu ra. Nếu sao chép toàn bộ `build.xml` cho từng dự án, các bản build dễ lệch nhau: một dự án được cập nhật quy tắc compile nhưng dự án khác vẫn dùng cấu hình cũ.

Apache Ant cho phép tách phần dùng chung khỏi phần riêng bằng property, file cấu hình `.properties`, target dùng chung và cơ chế `import`/`include`. Cấu trúc tốt giúp nhiều dự án tuân theo một quy trình thống nhất nhưng vẫn giữ quyền khai báo những giá trị riêng của chúng.

`include` có từ Apache Ant 1.8.0. Nếu dự án dùng Ant cũ hơn, hãy kiểm tra khả năng tương thích hoặc dùng `import`/các buildfile con phù hợp với phiên bản đang chạy.

Trong bài này, ta sẽ tổ chức cấu hình thành bốn lớp:

1. **Quy tắc build dùng chung:** các target và task có thể tái sử dụng.
2. **Giá trị mặc định chung:** encoding, debug, quy ước thư mục và các tùy chọn mặc định.
3. **Cấu hình riêng của dự án:** source directory, thư viện, tên artifact và build output.
4. **Cấu hình môi trường khi chạy:** URL triển khai, endpoint, thông tin xác thực và các giá trị thay đổi theo môi trường.

## 1. Nhận diện phần dùng chung và phần riêng

Giả sử tổ chức có hai dự án `catalog` và `billing`. Cả hai đều cần biên dịch Java, copy resource và tạo JAR, nhưng có cấu trúc source và tên sản phẩm khác nhau.

| Thuộc tính | Dùng chung | Riêng từng dự án |
|---|---|---|
| Encoding source | UTF-8 theo quy ước nhóm | Có thể override nếu source legacy |
| Debug compile | Mặc định bật trong development | Có thể tắt cho release |
| Target `init`, `compile`, `package`, `clean` | Dùng chung logic | Dùng chung logic, nhận giá trị qua property |
| Source directory | Quy ước mặc định | `apps/catalog/src/main/java`, `apps/billing/src/main/java` |
| Thư mục output | Cùng quy tắc tổ chức | `build/catalog`, `build/billing` |
| Tên artifact | Quy tắc đặt tên | `catalog.jar`, `billing.jar` |
| Dependency | Cùng cách khai báo path | Mỗi dự án có tập JAR riêng |
| Endpoint triển khai | Có thể dùng chung cơ chế | URL của từng môi trường/dự án |

Nguyên tắc quan trọng là giữ **logic** trong phần dùng chung và truyền **dữ liệu cấu hình** vào logic đó. Một target compile dùng chung không nên biết dự án cụ thể là `catalog` hay `billing`; nó chỉ cần biết `project.src.dir`, `project.classes.dir` và `project.compile.classpath`.

## 2. Tổ chức thư mục cấu hình

Một cấu trúc đơn giản có thể như sau:

```text
workspace/
├── build.xml
├── build/
│   └── common-targets.xml
├── config/
│   ├── common.properties
│   ├── catalog.properties
│   └── billing.properties
├── apps/
│   ├── catalog/
│   │   ├── src/main/java/
│   │   └── lib/
│   └── billing/
│       ├── src/main/java/
│       └── lib/
└── build-output/
    ├── catalog/
    └── billing/
```

Vai trò từng thành phần:

- `build.xml`: điểm vào của workspace, chọn dự án và nạp cấu hình.
- `build/common-targets.xml`: định nghĩa các target dùng chung.
- `config/common.properties`: các giá trị mặc định áp dụng cho mọi dự án.
- `config/catalog.properties`, `config/billing.properties`: giá trị riêng của từng dự án.
- `apps/<project>/`: source và thư viện riêng.
- `build-output/<project>/`: đầu ra được tách theo dự án để tránh ghi đè lẫn nhau.

Không bắt buộc phải dùng đúng cấu trúc này. Với monorepo lớn, có thể đặt buildfile dùng chung trong `build-logic/`, cấu hình trong `config/` hoặc thư mục con của từng module. Điều quan trọng là đường dẫn được tính nhất quán và đầu ra của các dự án không va chạm.

## 3. Dùng property file để tách cấu hình

Ant có task `<property>` để đọc file `.properties`. Ví dụ file `config/common.properties`:

```properties
# Các mặc định dùng chung
build.encoding=UTF-8
build.debug=true
build.optimize=false
project.src.dir=src/main/java
project.lib.dir=lib
project.artifact.name=application.jar
```

File `config/catalog.properties` chỉ ghi những giá trị khác mặc định:

```properties
project.src.dir=apps/catalog/src/main/java
project.lib.dir=apps/catalog/lib
project.build.dir=build-output/catalog
project.artifact.name=catalog-service.jar
```

File `config/billing.properties` có thể là:

```properties
project.src.dir=apps/billing/src/main/java
project.lib.dir=apps/billing/lib
project.build.dir=build-output/billing
project.artifact.name=billing-service.jar
build.debug=false
```

Nhờ vậy, `catalog.properties` chỉ cần khai báo các giá trị khác mặc định; những giá trị chưa có sẽ lấy từ `common.properties` hoặc default trong buildfile.

## 4. Hiểu quy tắc bất biến của Ant property

Ant property thông thường được thiết lập theo nguyên tắc **set một lần**. Khi một tên property đã có giá trị, lần khai báo sau cùng tên thường không thay đổi giá trị đó. Đây là điểm quyết định thứ tự nạp cấu hình.

Ví dụ sau không cho phép `catalog.properties` ghi đè `project.src.dir` đã được nạp từ `common.properties`:

```xml
<property file="config/common.properties"/>
<property file="config/catalog.properties"/>
```

Nếu cả hai file cùng khai báo `project.src.dir`, giá trị trong `common.properties` được giữ lại vì nó được nạp trước.

Để giá trị riêng của dự án ưu tiên hơn mặc định chung, hãy nạp file riêng trước, file mặc định sau:

```xml
<property name="project.key" value="catalog"/>
<property name="config.dir" location="config"/>

<property file="${config.dir}/${project.key}.properties"/>
<property file="${config.dir}/common.properties"/>
```

Vì property được thiết lập một lần, các giá trị đã có trong file riêng được giữ nguyên; file chung chỉ bổ sung những property còn thiếu. Thứ tự ưu tiên khi đó là:

1. Property truyền từ dòng lệnh `-Dname=value`.
2. Property trong file riêng của dự án, nếu được nạp trước.
3. Property trong file mặc định chung, nếu tên chưa có giá trị.
4. Giá trị fallback được khai báo bằng `<property name="..." value="..."/>` sau đó.

Các user property truyền từ dòng lệnh có độ ưu tiên cao vì Ant thiết lập chúng trước khi thực thi buildfile và không cho property trong file ghi đè.

### Một lưu ý về tham chiếu giữa các property file

Vì file riêng được nạp trước file chung, không nên để giá trị trong file riêng phụ thuộc vào một property chỉ được khai báo trong file chung sau đó. Ví dụ, tránh viết trong `catalog.properties`:

```properties
project.classes.dir=${project.build.dir}/classes
```

nếu `project.build.dir` chỉ được định nghĩa trong `common.properties` sẽ nạp sau. Thay vào đó, hãy khai báo các giá trị đầu vào trong property file rồi tạo các giá trị dẫn xuất trong buildfile sau khi cả hai file đã được nạp:

```xml
<property name="project.classes.dir"
          location="${project.build.dir}/classes"/>
```

Cách này cũng giúp nhìn thấy rõ đâu là cấu hình do dự án cung cấp và đâu là đường dẫn được suy ra từ cấu hình.

## 5. Chọn dự án bằng property dòng lệnh

Có thể dùng một buildfile chung cho nhiều dự án và chọn dự án bằng `-Dproject.key=...`:

```bash
ant -Dproject.key=catalog build
ant -Dproject.key=billing build
```

Trong buildfile, khai báo giá trị mặc định cho `project.key`, sau đó nạp file tương ứng:

```xml
<project name="multi-project" default="build" basedir=".">
    <property name="project.key" value="catalog"/>
    <property name="config.dir" location="${basedir}/config"/>

    <property file="${config.dir}/${project.key}.properties"/>
    <property file="${config.dir}/common.properties"/>

    <!-- Các property dẫn xuất được khai báo sau khi nạp file. -->
</project>
```

Khi người dùng chạy `ant -Dproject.key=billing build`, giá trị dòng lệnh đã tồn tại trước khi buildfile được đọc. Dòng `<property name="project.key" value="catalog"/>` không thay đổi nó, nên Ant nạp `billing.properties`.

Đừng dùng một property có thể thay đổi trong target để chọn file cấu hình cho cùng một lần chạy. Property thông thường không thể đổi sau khi được thiết lập. Nếu muốn build hai dự án trong cùng một lệnh, hãy gọi từng sub-build với property riêng hoặc dùng `subant` để điều phối các project độc lập.

## 6. Hoàn thiện buildfile chính

Ví dụ `build.xml` sau chọn một dự án, nạp cấu hình riêng trước cấu hình chung, tạo các đường dẫn dẫn xuất và include target dùng chung:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="multi-project" default="build" basedir=".">

    <!-- Có thể override bằng -Dproject.key=billing. -->
    <property name="project.key" value="catalog"/>
    <property name="config.dir" location="${basedir}/config"/>

    <!-- Specific trước, shared defaults sau. -->
    <property file="${config.dir}/${project.key}.properties"/>
    <property file="${config.dir}/common.properties"/>

    <!-- Fallback nếu cả hai file không khai báo property. -->
    <property name="project.src.dir"
              location="${basedir}/apps/${project.key}/src/main/java"/>
    <property name="project.lib.dir"
              location="${basedir}/apps/${project.key}/lib"/>
    <property name="project.build.dir"
              location="${basedir}/build-output/${project.key}"/>
    <property name="project.artifact.name"
              value="${project.key}.jar"/>
    <property name="build.encoding" value="UTF-8"/>
    <property name="build.debug" value="true"/>

    <!-- Các thư mục được suy ra từ build directory của dự án. -->
    <property name="project.classes.dir"
              location="${project.build.dir}/classes"/>
    <property name="project.dist.dir"
              location="${project.build.dir}/dist"/>

    <path id="project.compile.classpath">
        <fileset dir="${project.lib.dir}" includes="**/*.jar"/>
    </path>

    <include file="${basedir}/build/common-targets.xml" as="shared"/>

    <target name="build" depends="shared.package"
            description="Build dự án đang được chọn"/>

    <target name="clean" depends="shared.clean"
            description="Xóa output của dự án đang được chọn"/>

</project>
```

Buildfile này chỉ chứa cấu hình đầu vào và target điều phối. Các thao tác thực tế được định nghĩa trong `common-targets.xml`.

## 7. Viết target dùng chung trong một file riêng

File `build/common-targets.xml` chỉ chứa logic build và tham chiếu đến property do buildfile gọi cung cấp:

```xml
<project name="shared-build">

    <target name="init">
        <mkdir dir="${project.classes.dir}"/>
        <mkdir dir="${project.dist.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${project.src.dir}"
               destdir="${project.classes.dir}"
               encoding="${build.encoding}"
               debug="${build.debug}"
               includeantruntime="false">
            <classpath refid="project.compile.classpath"/>
        </javac>
    </target>

    <target name="package" depends="compile">
        <jar destfile="${project.dist.dir}/${project.artifact.name}"
             basedir="${project.classes.dir}"/>
    </target>

    <target name="clean">
        <delete dir="${project.build.dir}"/>
    </target>

</project>
```

Vì file được nạp bằng `<include ... as="shared"/>`, các target được công bố dưới tên `shared.init`, `shared.compile`, `shared.package` và `shared.clean`. Dependency bên trong file cũng được prefix hóa: `shared.compile` phụ thuộc `shared.init`, `shared.package` phụ thuộc `shared.compile`.

Các target dùng chung không chứa đường dẫn cố định như `build/catalog` hoặc `apps/billing`. Chúng chỉ dùng property `project.*`, vì vậy cùng một logic có thể chạy cho nhiều dự án.

## 8. Chạy hai dự án với cùng một buildfile

Với cấu trúc trên, có thể build từng dự án trong các lần gọi Ant riêng:

```bash
ant -Dproject.key=catalog build
ant -Dproject.key=billing build
```

Kết quả đầu ra được tách:

```text
build-output/
├── catalog/
│   ├── classes/
│   └── dist/catalog-service.jar
└── billing/
    ├── classes/
    └── dist/billing-service.jar
```

Việc tách thư mục output là thiết yếu. Nếu cả hai dự án cùng ghi vào `build/classes` hoặc cùng tạo `build/application.jar`, lần build sau có thể ghi đè hoặc trộn file từ dự án trước.

Khi muốn chạy cả hai, có thể gọi Ant hai lần từ script bên ngoài hoặc tạo một target điều phối bằng `<ant>` để mỗi dự án chạy trong một project con với property riêng.

### Điều phối nhiều subproject bằng `<ant>`

Khi cần build nhiều dự án trong cùng một invocation, hãy tách buildfile cấu hình một dự án (ví dụ lưu nội dung ở phần 6 thành `build-project.xml`) khỏi buildfile điều phối ở gốc workspace. Buildfile điều phối có thể gọi buildfile cấu hình đó nhiều lần với property khác nhau:

```xml
<project name="workspace" default="build-all" basedir=".">

    <target name="build-catalog">
            <ant antfile="build-project.xml" dir="." target="build"
             inheritAll="false">
            <property name="project.key" value="catalog"/>
        </ant>
    </target>

    <target name="build-billing">
            <ant antfile="build-project.xml" dir="." target="build"
             inheritAll="false">
            <property name="project.key" value="billing"/>
        </ant>
    </target>

    <target name="build-all" depends="build-catalog,build-billing"/>

</project>
```

Ở đây, `build-project.xml` là buildfile cấu hình một dự án đã trình bày ở phần 6; `build.xml` là buildfile điều phối. Mỗi task `<ant>` tạo một project con và truyền một `project.key` riêng. Khi dùng `inheritAll="false"`, các property thông thường từ project cha không được kế thừa toàn bộ; hãy truyền rõ các giá trị mà project con cần. Các user property có quy tắc kế thừa riêng của Ant, vì vậy nếu cần bảo đảm mỗi sub-build nhận đúng project key, hãy truyền property tường minh như ví dụ và tránh chạy coordinator với một `-Dproject.key` toàn cục không phù hợp.

Với một tập lớn thư mục module có cùng cấu trúc, task `subant` có thể lặp qua nhiều subproject. Mỗi subproject nên có buildfile riêng hoặc dùng một generic buildfile nhận property được truyền vào. Không nên giả định việc gọi nhiều target trong cùng một project sẽ tạo ra property riêng cho từng dự án.

## 9. Phân tách cấu hình theo môi trường

Cấu hình riêng của dự án và cấu hình môi trường là hai chiều khác nhau. `catalog` và `billing` là hai dự án; `dev`, `staging` và `prod` là các môi trường triển khai. Không nên trộn tất cả thành một file lớn với tên khó kiểm soát.

Có thể tổ chức:

```text
config/
├── common.properties
├── projects/
│   ├── catalog.properties
│   └── billing.properties
└── environments/
    ├── dev.properties
    ├── staging.properties
    └── prod.properties
```

Một lựa chọn đơn giản là chọn cả project và environment bằng property dòng lệnh, rồi nạp file riêng trước các file mặc định:

```xml
<property name="project.key" value="catalog"/>
<property name="environment" value="dev"/>
<property name="config.dir" location="config"/>

<property file="${config.dir}/environments/${environment}.properties"/>
<property file="${config.dir}/projects/${project.key}.properties"/>
<property file="${config.dir}/common.properties"/>
```

Thứ tự trên có nghĩa cấu hình project có thể ghi đè cấu hình môi trường, còn common chỉ bổ sung giá trị chưa có. Nếu chính sách của nhóm muốn môi trường có quyền ưu tiên cao hơn project, hãy đảo thứ tự hai file đầu. Điều quan trọng là định nghĩa và ghi lại thứ tự ưu tiên một cách nhất quán.

Chạy ví dụ:

```bash
ant -Dproject.key=catalog -Denvironment=staging build
```

Các giá trị như URL triển khai, tên context hoặc cờ bật/tắt tính năng có thể nằm trong file môi trường. Password, token và private key không nên commit vào repository. Hãy lấy bí mật từ biến môi trường, secret store hoặc cơ chế credentials của CI.

## 10. Đọc biến môi trường và truyền cấu hình nhạy cảm

Ant có thể đưa biến môi trường vào property bằng thuộc tính `environment`:

```xml
<property environment="env"/>

<target name="show-deployment-endpoint">
    <echo message="Endpoint: ${env.DEPLOYMENT_URL}"/>
</target>
```

Ví dụ này tạo property có prefix `env.`. Nếu biến môi trường `DEPLOYMENT_URL` tồn tại, buildfile có thể tham chiếu `${env.DEPLOYMENT_URL}`.

Không nên in password hoặc token ra log bằng `<echo>`. Nếu task cần credentials, hãy truyền chúng qua cơ chế hỗ trợ secret của CI hoặc file ngoài workspace có quyền truy cập hạn chế. Buildfile nên chỉ tham chiếu tên biến hoặc property cần thiết, không chứa giá trị bí mật.

Đối với cấu hình không nhạy cảm, command line cũng là cách override tiện lợi:

```bash
ant -Dproject.key=catalog -Dbuild.debug=false build
```

Property dòng lệnh hữu ích cho một lần chạy, nhưng không nên nhồi quá nhiều tham số vào script gọi Ant. Các giá trị ổn định nên nằm trong file cấu hình được version control; các giá trị môi trường hoặc bí mật nên được cấp từ CI.

## 11. Tách property dùng chung khỏi property dự án

Đặt tên property theo namespace để giảm nguy cơ va chạm:

| Prefix | Ví dụ | Phạm vi gợi ý |
|---|---|---|
| `build.*` | `build.encoding`, `build.debug` | Quy tắc build dùng chung |
| `project.*` | `project.src.dir`, `project.artifact.name` | Cấu hình dự án đang được build |
| `test.*` | `test.classes.dir`, `test.reports.dir` | Cấu hình kiểm thử |
| `env.*` | `env.DEPLOYMENT_URL` | Giá trị lấy từ môi trường |
| `publish.*` | `publish.repository`, `publish.channel` | Cấu hình phát hành |

Ant không tự tạo namespace cho property khi dùng `import` hoặc `include`. Prefix trong tên target chỉ áp dụng cho target. Vì vậy, nếu hai file con cùng khai báo `output.dir`, chúng vẫn có thể xung đột trong cùng project. Tự đặt prefix trong tên property là cách đơn giản và dễ kiểm soát.

## 12. Khi nào dùng property file, `import`, `include` hoặc `<ant>`?

Các cơ chế này giải quyết những vấn đề khác nhau:

| Cơ chế | Dùng để |
|---|---|
| `<property file="..."/>` | Đọc giá trị cấu hình từ file `.properties` |
| `<import file="..."/>` | Nạp target dùng chung và cho phép buildfile chính ghi đè target |
| `<include file="..." as="..."/>` | Nạp nhóm target dưới namespace riêng, prefix hóa dependency |
| `<ant>` | Chạy buildfile khác trong project con và truyền property |
| `<subant>` | Điều phối nhiều subproject theo thư mục hoặc danh sách buildfile |

Không dùng property file để chứa logic target; không dùng import/include để thay thế cấu hình dữ liệu; và không dùng một property toàn cục có thể thay đổi để mô phỏng nhiều project độc lập trong cùng project Ant.

## 13. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Giá trị riêng bị giá trị chung ghi đè hoặc không có hiệu lực | Nạp common trước project-specific; property đã được thiết lập nên không đổi | Nạp project-specific trước, common sau để common chỉ làm fallback |
| Dự án thứ hai ghi đè output của dự án thứ nhất | Hai dự án dùng cùng build directory hoặc artifact name | Đưa project key vào build path và tên artifact |
| Target dùng chung không tìm thấy property | Buildfile gọi include target trước khi khai báo property hoặc thiếu property bắt buộc | Khai báo cấu hình ở project chính trước khi nạp target dùng chung |
| Property dẫn xuất có giá trị rỗng | Tham chiếu đến property chỉ được nạp ở bước sau | Tạo property dẫn xuất sau khi đã nạp tất cả file cấu hình |
| Một dự án dùng nhầm thư viện dự án khác | Dùng chung `lib.dir` hoặc classpath không có phạm vi | Dùng `project.lib.dir` và path riêng cho từng dự án |
| Build chạy local nhưng CI thiếu cấu hình | Dựa vào file cá nhân không có trong repository hoặc biến môi trường chưa được cấp | Đưa cấu hình không nhạy cảm vào repo và khai báo biến CI rõ ràng |
| Hai file include xung đột property | Prefix chỉ áp dụng cho target, không áp dụng property | Đặt tên property có namespace riêng |
| Không thể đổi property trong target clean/build | Ant property thông thường bất biến sau khi đặt | Dùng invocation riêng với `-D`, hoặc truyền tham số vào sub-build |
| Build phát hành dùng endpoint dev | Nạp sai environment file hoặc thứ tự ưu tiên chưa rõ | Kiểm tra `-Denvironment`, file được nạp và thứ tự override |
| Secret xuất hiện trong log hoặc Git | Ghi trực tiếp secret vào buildfile/property file hoặc echo ra console | Dùng secret store/CI variable và không in giá trị nhạy cảm |

Khi debug cấu hình, hãy in những property không nhạy cảm như project key, source directory, build directory và artifact name. Tránh in token, password hoặc URL có chứa thông tin xác thực.

## 14. Quy tắc thiết kế cho nhiều dự án

- Giữ một nguồn định nghĩa target dùng chung thay vì sao chép cùng logic vào nhiều buildfile.
- Dùng property file riêng cho mỗi dự án để khai báo những giá trị khác biệt.
- Nạp cấu hình riêng trước cấu hình mặc định chung nếu muốn giá trị riêng được ưu tiên.
- Khai báo các property dẫn xuất sau khi đã nạp các file cấu hình.
- Dùng `-Dproject.key=...` để chọn dự án cho một invocation; không cố thay đổi property trong lúc target đang chạy.
- Tách build output theo project key để tránh class, resource và artifact ghi đè lẫn nhau.
- Tách dependency theo dự án hoặc theo nhóm chức năng; không dùng một classpath quá rộng cho mọi module.
- Prefix tên property như `project.*`, `build.*`, `env.*` vì import/include không namespace property.
- Dùng import/include cho target và dùng property file cho dữ liệu cấu hình.
- Dùng `<ant>` hoặc `<subant>` khi cần thực thi nhiều project độc lập với tham số riêng.
- Giữ secret ngoài source control và không in giá trị bí mật vào log.
- Ghi rõ thứ tự ưu tiên cấu hình trong tài liệu nhóm để mọi người hiểu giá trị nào thắng khi trùng tên.

## 15. Bài tập tự kiểm tra

**Bài 1.** `common.properties` và `catalog.properties` cùng khai báo `project.src.dir`. Muốn giá trị của catalog được ưu tiên, nên nạp file nào trước?

**Đáp án:** Nạp `catalog.properties` trước, rồi nạp `common.properties`. Ant property thông thường không bị ghi đè, nên file chung chỉ bổ sung các giá trị còn thiếu.

**Bài 2.** Vì sao không nên để cả `catalog` và `billing` ghi output vào `build/classes`?

**Đáp án:** Vì file class có thể bị trộn hoặc ghi đè. Mỗi dự án cần build directory riêng, ví dụ `build-output/catalog/classes` và `build-output/billing/classes`.

**Bài 3.** `-Dproject.key=billing` có thể bị `<property name="project.key" value="catalog"/>` ghi đè không?

**Đáp án:** Không. User property từ dòng lệnh đã được thiết lập trước và có độ ưu tiên cao hơn property thông thường trong buildfile.

**Bài 4.** Khi nào cần khai báo property dẫn xuất như `project.classes.dir`?

**Đáp án:** Sau khi đã nạp file riêng và file chung, để các property dẫn xuất có thể tham chiếu đầy đủ các giá trị đầu vào như `project.build.dir`.

**Bài 5.** `include as="java"` có tự đổi property `output.dir` trong file được include thành `java.output.dir` không?

**Đáp án:** Không. Prefix chỉ áp dụng cho target. Property cần được đặt tên có namespace thủ công.

**Bài 6.** Có nên lưu password production trong `config/prod.properties` đã commit vào Git không?

**Đáp án:** Không. Secret nên được cấp qua secret store, biến môi trường hoặc cơ chế credentials của CI; file cấu hình trong repository chỉ nên chứa giá trị không nhạy cảm.

## Kết luận

Tách cấu hình dùng chung và cấu hình riêng giúp nhiều dự án Ant dùng cùng quy trình mà vẫn có source, dependency, output và artifact độc lập. Property file chứa dữ liệu cấu hình; target dùng chung chứa logic build; import/include nạp logic vào project; còn `<ant>` hoặc `<subant>` điều phối các project độc lập. Vì Ant property thông thường bất biến sau khi thiết lập, thứ tự nạp file quyết định giá trị nào được giữ. Khi nạp cấu hình dự án trước, dùng common properties làm fallback, tạo property dẫn xuất sau cùng và tách output theo dự án, build nhiều ứng dụng sẽ nhất quán và dễ kiểm soát hơn.

