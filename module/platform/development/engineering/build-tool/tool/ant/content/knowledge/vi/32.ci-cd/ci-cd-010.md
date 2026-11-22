# Đối chiếu kết quả build cục bộ với môi trường CI trong Apache Ant

## 1. Vì sao cùng một lệnh Ant có thể cho kết quả khác nhau?

Một dự án Java dùng **Apache Ant** thường được build trên máy phát triển và trong hệ thống **Continuous Integration (CI)**. Cả hai nơi đều có thể chạy lệnh `ant verify`, nhưng kết quả vẫn khác nhau:

- Máy cá nhân build thành công; CI báo lỗi biên dịch.
- CI thành công; máy cá nhân báo thiếu JAR hoặc class.
- Hai nơi đều build thành công, nhưng kích thước hoặc mã băm của tệp JAR không giống nhau.
- Máy cá nhân bỏ qua kiểm thử; CI thực thi kiểm thử rồi thất bại.
- Cùng một commit, nhưng khác hệ điều hành, JDK, Ant, biến môi trường hoặc thư viện.

Điều cần so sánh không chỉ là **“PASS hay FAIL”**, mà là **đầu vào, công cụ, chuỗi tác vụ và đầu ra** của hai lần build. Ant là công cụ chạy các target được định nghĩa trong `build.xml`; nó không tự bảo đảm máy phát triển và CI dùng cùng bộ công cụ, cùng dependency hoặc cùng dữ liệu đầu vào.

Mục tiêu của bài này là xây dựng một quy trình có thể lặp lại để:

1. Xác nhận hai môi trường thật sự build cùng mã nguồn và cùng target.
2. Ghi lại những yếu tố khiến kết quả phụ thuộc vào môi trường.
3. Tái hiện lệnh CI trên máy phát triển bằng một lần build sạch.
4. Phân biệt lỗi logic của dự án với sai khác cấu hình, đường dẫn, thư viện và JDK.
5. So sánh nội dung artifact một cách có căn cứ, bao gồm trường hợp mã băm khác nhưng chức năng tương đương.
6. Sửa cấu hình Ant/CI để giảm chênh lệch giữa những lần build tiếp theo.

## 2. Mô hình so sánh: cùng một phép build cần cùng những gì?

Có thể mô tả kết quả một lần build như sau:

```text
                         +------------------+
Commit + working tree -->|                  |
JDK + Ant + toolchain -->|                  |--> Exit code
-D properties ---------->|  Apache Ant      |--> Log
Variables + OS --------->|  build.xml       |--> .class / .jar / reports
Dependencies ----------->|                  |
Cache + files on disk -->|                  |
                         +------------------+
```

Trong đó:

| Thành phần | Máy cục bộ | CI | Tác động có thể gặp |
| --- | --- | --- | --- |
| Commit Git | Nhánh hiện tại và thay đổi chưa commit | Commit/ref được checkout bởi job | Thiếu mã nguồn, tài nguyên, cấu hình |
| Lệnh Ant | `ant`, `ant compile` hoặc lệnh trong IDE | Lệnh trong pipeline | Chạy target hoặc option khác nhau |
| JDK | Chọn từ `JAVA_HOME`, `PATH`, IDE | Toolchain được runner cài/chọn | `invalid source release`, bytecode không phù hợp |
| Ant | Cài qua OS/IDE | Cài qua image/package manager | Khác tính năng, task, logger |
| Property | `-Denv=local`, property file | `-Denv=ci`, env của runner | Đổi nguồn, output, điều kiện skip |
| Thư viện | `lib/*.jar` đã tải từ trước | JAR được checkout/tải lại/cache | `package ... does not exist`, xung đột class |
| OS/đường dẫn | Windows hoặc macOS | Linux runner | Chữ hoa/thường, dấu phân cách, quyền thực thi |
| Cache/output | Có thể còn `build/` và `dist/` cũ | Thường checkout mới, nhưng có thể dùng cache | Kết quả gia tăng khác clean build |
| Locale/timezone/clock | Tùy máy | Tùy runner | Test phụ thuộc ngày giờ, tệp sinh khác nhau |
| Credentials/network | Token hoặc proxy cá nhân | Secrets, quyền và mạng của CI | Không tải được dependency, không truy cập registry |

Không phải mục nào cũng cần **giống tuyệt đối**. Ví dụ, đường dẫn workspace có thể là `C:\dev\app` trên Windows và `/home/runner/work/app` trên Linux. Điều quan trọng là cấu hình Ant dựa vào đường dẫn tương đối theo project khi phù hợp, còn đầu vào mang ý nghĩa nghiệp vụ phải tương đương.

Một kết quả đối chiếu tốt trả lời được ba câu hỏi:

- **Có đang chạy cùng phiên bản mã và cùng tập kiểm tra không?**
- **Những khác biệt môi trường nào ảnh hưởng trực tiếp đến lỗi hoặc artifact?**
- **Có thể tái hiện kết quả đó bằng một lệnh cụ thể không?**

## 3. Bắt đầu bằng việc xác nhận cùng mã nguồn và cùng lệnh

### 3.1. Đối chiếu Git revision

Trên máy phát triển, chạy:

```bash
git rev-parse HEAD
git status --short
git branch --show-current
```

`git rev-parse HEAD` cho mã commit hiện tại; `git status --short` cho biết tệp đã sửa, thêm hoặc chưa được theo dõi. CI thường checkout từ repository, nên **thay đổi chưa commit chỉ có trên máy cá nhân** sẽ không có trong workspace CI.

Nếu CI chạy trên pull request, commit mà job checkout có thể là một **merge commit tạm do nền tảng tạo**. Khi đó, không thể mặc định so sánh với HEAD của nhánh tính năng; phải lấy đúng SHA/ref mà job thực sự dùng.

Cần so sánh:

- Commit SHA thực tế tại bước checkout trên CI với SHA ở máy đang tái hiện.
- Sự tồn tại của các file source, resource, `build.xml`, `properties` và JAR được quản lý trong repository.
- Các file có trên máy cá nhân nhưng đang bị `.gitignore` bỏ qua, ví dụ `local.properties`, `lib/private.jar`.
- Thư mục làm việc tại thời điểm gọi Ant.

Nếu có thể, hãy tái hiện bằng checkout riêng đúng revision của CI và **không có thay đổi chưa commit**. Không nên vội chỉnh `build.xml` để “khắc phục CI” khi nguyên nhân chỉ là file chưa được đưa lên repository.

### 3.2. Đối chiếu lệnh Ant và target

Ba lệnh sau có thể có kết quả khác nhau:

```bash
ant
ant compile
ant clean verify
```

Lệnh `ant` chạy default target trong `build.xml`. `ant compile` chỉ yêu cầu target `compile` và các dependency của nó. `ant clean verify` yêu cầu Ant thực thi `clean` trước rồi đi qua chuỗi dependency của `verify`. Nếu kiểm thử được gắn vào `verify` nhưng không vào `compile`, hai lệnh sau không kiểm tra cùng phạm vi.

Một số tùy chọn cần giữ giống giữa local và CI:

| Tùy chọn | Ý nghĩa |
| --- | --- |
| `-f build.xml` / `-buildfile build.xml` | Chọn file build cụ thể |
| `-Dname=value` | Khai báo property từ dòng lệnh |
| `-propertyfile ci.properties` | Nạp property từ tệp được chỉ định |
| `-lib ...` | Bổ sung JAR cho classpath của Ant, thường phục vụ custom task |
| `-quiet`, `-verbose`, `-debug` | Điều chỉnh mức chi tiết của logger |
| `-logfile build.log` | Ghi log Ant vào file |
| Danh sách target cuối lệnh | Quyết định các tác vụ và dependency sẽ chạy |

Ví dụ, nếu CI dùng:

```bash
ant -f build.xml -Dbuild.profile=ci clean verify
```

thì việc chạy `ant compile` trên máy cá nhân **không phải** một lần đối chiếu tương đương. Hãy bắt đầu từ cùng lệnh và chỉ khác những thông tin thực sự phải riêng cho môi trường, chẳng hạn credentials.

## 4. Ví dụ build Ant dùng chung cho local và CI

Phần này minh họa một dự án Java tối giản, không cần thư viện ngoài. Mục tiêu là làm rõ điều gì xảy ra khi chạy cùng target `verify` ở hai nơi, chứ không phụ thuộc vào một nền tảng CI cụ thể.

Cấu trúc:

```text
ant-ci-compare/
├── build.xml
├── src/
│   └── com/
│       └── example/
│           └── Main.java
├── build/           # Sinh khi biên dịch
│   └── classes/
└── dist/            # Sinh khi đóng gói
    └── demo.jar
```

Tạo `src/com/example/Main.java`:

```java
package com.example;

public class Main {
    public static void main(String[] args) {
        System.out.println("Ant build OK");
    }
}
```

Tạo `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-ci-compare" default="verify" basedir=".">

    <!-- -D trên dòng lệnh có thể đặt property trước các giá trị mặc định. -->
    <property name="build.profile" value="local"/>
    <property name="java.release" value="17"/>
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="artifact.file" location="dist/demo.jar"/>

    <target name="environment">
        <echo level="info"
              message="[environment][${build.profile}] Ant: ${ant.version}"/>
        <echo level="info"
              message="[environment] JVM của Ant: Java ${ant.java.version}; ${java.home}"/>
        <echo level="info"
              message="[environment] Release đầu ra yêu cầu: ${java.release}"/>

        <available file="${src.dir}" type="dir"
                   property="source.exists"/>
        <fail unless="source.exists"
              message="[environment] Thiếu thư mục source ${src.dir}"/>
    </target>

    <target name="clean">
        <delete dir="build"/>
        <delete dir="dist"/>
    </target>

    <target name="compile" depends="environment">
        <mkdir dir="${classes.dir}"/>
        <echo level="info"
              message="[compile] Biên dịch mã nguồn UTF-8"/>

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               release="${java.release}"
               includeantruntime="false"
               debug="true"/>

        <echo level="info"
              message="[compile] Hoàn thành biên dịch"/>
    </target>

    <target name="package" depends="compile">
        <mkdir dir="${dist.dir}"/>

        <jar destfile="${artifact.file}"
             basedir="${classes.dir}"/>

        <echo level="info"
              message="[package] Đã tạo ${artifact.file}"/>
    </target>

    <target name="smoke" depends="package">
        <echo level="info"
              message="[smoke] Chạy class chính từ JAR"/>
        <java classname="com.example.Main"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${artifact.file}"/>
            </classpath>
        </java>
    </target>

    <target name="verify" depends="smoke">
        <echo level="info"
              message="[verify][${build.profile}] Tất cả bước được yêu cầu đã hoàn thành"/>
    </target>

</project>
```

Dự án này dùng Java 17 làm **release đầu ra** và cần JDK/compiler hỗ trợ `release="17"`. `includeantruntime="false"` tránh tự động thêm thư viện runtime của Ant vào compile classpath, một nguyên nhân khiến project vô tình phụ thuộc vào môi trường phát triển. Ví dụ chỉ có một bước **smoke test** kiểm tra chạy class chính; trong dự án thật, target `verify` cần bao gồm cả bộ kiểm thử được yêu cầu.

Chạy build sạch trên máy cá nhân:

```bash
ant -f build.xml -Dbuild.profile=ci clean verify
```

Lệnh này cố ý dùng `build.profile=ci` để đối chiếu đường đi cấu hình giống pipeline. Property `build.profile` ở ví dụ chỉ dùng để ghi ngữ cảnh; nó không làm thay đổi bytecode. Trong ứng dụng thực tế, profile có thể ảnh hưởng đến resource, endpoint, cơ chế dependency hoặc điều kiện chạy target, và các ảnh hưởng đó phải được liệt kê.

### 4.1. Pipeline CI minh họa

Ví dụ GitHub Actions cho Linux runner và JDK 17:

```yaml
name: Ant verification

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - name: Checkout source
        uses: actions/checkout@v4

      - name: Set up Java
        uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Install Apache Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant

      - name: Record build environment
        run: |
          git rev-parse HEAD
          git status --short
          ant -version
          java -version
          javac -version

      - name: Clean and verify with Ant
        run: ant -f build.xml -Dbuild.profile=ci clean verify

      - name: Save JAR for inspection
        uses: actions/upload-artifact@v4
        with:
          name: ant-demo-jar
          path: dist/demo.jar
```

Đây là **pipeline ví dụ**, cần lưu ở `.github/workflows/ant.yml` nếu dự án chọn GitHub Actions. Với Jenkins, GitLab CI hoặc hệ thống khác, mục tiêu tương đương là checkout đúng revision, thiết lập cùng JDK/Ant, chạy đúng lệnh Ant, rồi lưu log và artifact.

Có một hạn chế: `apt-get install ant` lấy phiên bản theo kho gói của image runner, có thể thay đổi theo thời gian. Nếu yêu cầu tái lập nghiêm ngặt, cần **cố định phiên bản Ant và cách cấp phát toolchain**, hoặc sử dụng một image đã được kiểm soát phiên bản. Đổi tên `runs-on` thành một image cụ thể giúp giảm biến động nhưng không tự làm mọi gói apt trở nên bất biến.

### 4.2. Đối chiếu kết quả của ví dụ

Khi cả hai nơi chạy thành công, đầu ra mong đợi gồm:

```text
[compile] Hoàn thành biên dịch
[package] Đã tạo .../dist/demo.jar
[smoke] Chạy class chính từ JAR
     [java] Ant build OK
[verify][ci] Tất cả bước được yêu cầu đã hoàn thành
BUILD SUCCESSFUL
```

Cách hiển thị tiền tố, dấu cách và đường dẫn tuyệt đối có thể khác giữa Ant version, logger và OS. Điều cần quan sát là cùng target đã chạy, không có lỗi, smoke test thực sự in `Ant build OK` và có `dist/demo.jar`.

Dù dòng `BUILD SUCCESSFUL` xuất hiện, nó mới xác nhận các target **được yêu cầu** hoàn thành; nếu pipeline quên đưa bước test vào chuỗi `depends`, không thể coi việc thiếu log test là bằng chứng rằng test đã chạy.

## 5. So sánh JDK, Ant và compiler

### 5.1. JDK chạy Ant có thể khác JDK dùng để biên dịch

Trên cả local và CI, ghi nhận:

```bash
ant -version
java -version
javac -version
ant -diagnostics
```

Trong `build.xml`, property `ant.java.version` và `java.home` cho biết JVM đang chạy Ant. Nhưng:

- `java -version` ở terminal cho biết lệnh `java` mà shell tìm được.
- `javac -version` cho biết lệnh `javac` mà shell tìm được.
- `<javac>` có thể dùng compiler của JVM chạy Ant hoặc compiler khác nếu có `fork` và `executable`.
- IDE có thể đặt JDK cho quá trình build khác với phiên terminal.
- Biến `JAVA_HOME`, `PATH`, `ANT_HOME` và chính launcher Ant đều có thể ảnh hưởng kết quả.

Vì vậy, nếu local dùng JDK 21 và CI dùng JDK 17, không nên mặc định rằng `release="17"` giải quyết được mọi khác biệt. Cần xác định compiler thực tế, bộ API được tham chiếu, các JAR phụ thuộc và JVM của bước chạy/kiểm thử.

### 5.2. Lỗi dễ nhận biết khi JDK không khớp

| Thông báo | Cách hiểu ban đầu |
| --- | --- |
| `invalid source release: 21` | Compiler hiện tại không hỗ trợ cấu hình source Java 21 |
| `release version 21 not supported` | Compiler không hỗ trợ release đầu ra 21 |
| `bad class file ... wrong version 65.0 ... 61.0` | Compiler không đọc được classfile dependency tạo cho Java mới hơn |
| `UnsupportedClassVersionError` | JVM chạy chương trình cũ hơn bytecode cần nạp |
| `NoSuchMethodError` | Có thể đang dùng khác phiên bản thư viện lúc compile và runtime |
| `cannot find symbol` | Có thể lỗi source, import, dependency hoặc khác phiên bản API |

Major version phổ biến: Java 8 = 52, Java 11 = 55, Java 17 = 61 và Java 21 = 65. Nếu cần biết file `.class` đã được biên dịch cho release nào:

```bash
javap -verbose build/classes/com/example/Main.class
```

Tìm `major version` trong kết quả. Việc kiểm tra này giúp trả lời câu hỏi **bytecode đang có**, nhưng không chứng minh tự động rằng mọi thư viện và API dùng khi chạy cũng tương thích.

### 5.3. `release` và hợp đồng tương thích

Ví dụ:

```xml
<javac srcdir="src"
       destdir="build/classes"
       release="17"
       includeantruntime="false"/>
```

Với compiler hỗ trợ, `release="17"` giới hạn cú pháp, bytecode và API nền tảng của Java 17. Cấu hình truyền thống `source="17" target="17"` chỉ giới hạn cú pháp và bytecode; khi dùng JDK mới hơn, mã vẫn có thể tham chiếu API JDK xuất hiện sau Java 17.

Tuy nhiên `release` **không thay đổi bytecode bên trong dependency bên thứ ba**. Một JAR build cho Java 21 vẫn có thể gây lỗi khi project phải chạy Java 17. Khi so sánh hai môi trường, cần kiểm tra cả source, compiler lẫn dependency đầu vào.

## 6. So sánh property và biến môi trường Ant

### 6.1. Property khác nhau khiến target đi nhánh khác

Ant có thể nhận property từ `-D`, tệp property và các khai báo `<property>` trong build. Trong trường hợp thông thường, **property đã được đặt thì không bị ghi đè bằng `<property>` về sau**. Vì vậy lệnh:

```bash
ant -Dbuild.profile=ci verify
```

có thể tạo luồng khác với:

```bash
ant -Dbuild.profile=local verify
```

nếu build dựa vào `build.profile` để chọn file cấu hình, bộ test hay thư mục output.

Ví dụ:

```xml
<property name="build.profile" value="local"/>

<target name="show-profile">
    <echo level="info"
          message="[show-profile] Profile đang dùng: ${build.profile}"/>
</target>
```

Nhưng đừng hiểu một property có giá trị chữ `false` là “chưa được đặt”. Với `<target if="...">` hoặc `unless="..."` ở cú pháp truyền thống, điều kiện thường kiểm tra **sự tồn tại** của property. Chẳng hạn `-Dskip.tests=false` vẫn tạo property `skip.tests`, và một target `unless="skip.tests"` có thể bị bỏ qua. Trường hợp này thường giải thích được vì sao test chạy ở nơi này nhưng bị bỏ qua ở nơi khác.

### 6.2. Đừng in toàn bộ environment để so sánh

Các biến thường ảnh hưởng build:

| Biến hoặc nhóm biến | Khả năng tác động |
| --- | --- |
| `JAVA_HOME`, `PATH` | Lựa chọn Java, Ant và lệnh con |
| `ANT_HOME`, `ANT_OPTS` | Ant launcher, tùy chọn JVM chạy Ant |
| `JAVA_TOOL_OPTIONS`, `JDK_JAVA_OPTIONS` | Tùy chọn JVM có thể được chèn vào tiến trình Java |
| `LANG`, `LC_ALL`, `TZ` | Locale, encoding, timezone, test định dạng/ngày giờ |
| `HTTP_PROXY`, `HTTPS_PROXY`, `NO_PROXY` | Truy cập repository hoặc dịch vụ ngoài |
| Biến riêng của pipeline | Profile, tên artifact, điều kiện skip, đường dẫn cache |
| Secrets | Quyền lấy artifact, gọi dịch vụ, ký gói hoặc deploy |

Chỉ log những giá trị **không nhạy cảm và cần để chẩn đoán**. Không nên chạy lệnh dump mọi biến rồi upload nguyên file lên hệ thống CI công khai; chúng có thể chứa token, mật khẩu hoặc dữ liệu nội bộ. Đối với biến bí mật, chỉ nên báo trạng thái có/không theo cơ chế an toàn của dự án khi thật cần thiết.

### 6.3. Property file có thể chỉ tồn tại trên local

Ví dụ build nạp:

```xml
<property file="local.properties"/>
```

Nếu tệp không được commit hoặc không được CI tạo ra, máy phát triển và CI có thể nhận các giá trị khác nhau. Giải pháp là xác định:

- Property nào cần thiết cho build thường.
- Property nào nên có giá trị mặc định hợp lý.
- Property nào bắt buộc lấy từ secret store ở CI.
- Target nào cần fail rõ ràng nếu thiếu một property bắt buộc.

Tránh để build “thành công” bằng cách âm thầm dùng một file hoặc credential cũ trên máy cá nhân.

## 7. Dependency và cache: nguồn sai khác rất thường gặp

### 7.1. Có file JAR trên local nhưng CI không có

Ví dụ cấu hình:

```xml
<path id="compile.classpath">
    <fileset dir="lib"
             includes="**/*.jar"
             erroronmissingdir="false"/>
</path>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Nếu local có `lib/some-api.jar` nhưng file này không có trong Git và CI không có bước tải, compiler trên CI có thể báo `package ... does not exist`. Ant `<fileset>` chỉ chọn file đang tồn tại, **không tự tải dependency** từ Maven Central hay một registry khác.

Khi dùng Ivy hoặc custom task để lấy dependency, cần đối chiếu thêm repository URL, tọa độ phiên bản, khả năng kết nối, credential và cache. Một bản thư viện được giữ trong cache local có thể khác phiên bản mà CI vừa tải nếu dependency không được cố định.

### 7.2. Đường dẫn `-lib` khác compile classpath

Trong Ant, tùy chọn `-lib` bổ sung JAR vào **classpath của chính Ant**, thường cho custom task, Antlib hoặc thư viện phục vụ task. Còn phần `<classpath>` của `<javac>` chỉ rõ nơi compiler tìm dependency của source Java.

Nếu custom task không được nhận diện, hãy kiểm tra cách cấp phát task/JAR của Ant. Nếu mã Java báo thiếu `org.example.Client`, hãy kiểm tra compile classpath. Thêm JAR vào `-lib` để che lỗi thiếu dependency của ứng dụng có thể khiến build phụ thuộc ngầm vào môi trường và khó tái hiện trên CI.

### 7.3. Cache và build gia tăng

Ant `<javac>` có cơ chế biên dịch gia tăng dựa trên thông tin source/output, nhưng không theo dõi đầy đủ mọi thay đổi sâu của dependency. Trên máy cá nhân, `build/classes` có thể giữ class cũ; trong CI, workspace mới không có file đó.

Hãy dùng **clean build** cho lần đối chiếu đầu tiên:

```bash
ant clean verify
```

Nếu build thực tế xóa `build/` và `dist/`, cần kiểm tra target `clean` chỉ thao tác trên thư mục output do build quản lý. Không nên tùy tiện xóa cache dùng chung hoặc thư mục dữ liệu ngoài dự án.

Có thể so sánh hai chế độ:

1. Local incremental build từ workspace đang sử dụng.
2. Local clean build từ cùng commit.
3. CI clean build cùng commit.

Nếu chỉ chế độ incremental cho kết quả khác, hãy kiểm tra class cũ, tài nguyên chưa tái tạo hoặc dependency đã đổi mà output chưa được biên dịch lại.

## 8. Các khác biệt hệ điều hành và đường dẫn

### 8.1. Chữ hoa/chữ thường

Windows thường dùng filesystem không phân biệt chữ hoa/chữ thường, còn Linux runner thường phân biệt. Ví dụ source khai báo:

```java
package com.example;

public class UserService { }
```

nhưng đường dẫn hoặc khai báo bên khác tham chiếu sai `userservice`, local có thể che giấu một số lỗi file path mà Linux không bỏ qua. Tên Java class vẫn phải đúng quy tắc ngôn ngữ trên mọi OS; vấn đề thường xuất hiện tại **đường dẫn file, tên tài nguyên, file copy và file tham chiếu**.

Hãy thống nhất chính xác chữ hoa/chữ thường của tên file và cấu trúc package trong repository.

### 8.2. Dấu phân cách, đường dẫn tuyệt đối và khoảng trắng

Không nên viết cứng trong `build.xml`:

```xml
<property name="classes.dir" value="C:\Users\someone\project\build\classes"/>
```

Thay bằng:

```xml
<property name="classes.dir" location="build/classes"/>
```

Ant có các task xử lý đường dẫn theo nền tảng. Với classpath, dùng `<path>`, `<pathelement>` và `<fileset>` thay vì tự nối chuỗi bằng dấu `;` hoặc `:`.

Ví dụ:

```xml
<path id="app.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib" includes="**/*.jar"
             erroronmissingdir="false"/>
</path>
```

Đặc biệt cần kiểm tra script ngoài do `<exec>` gọi: tập tin `.sh`, `.bat` và các lệnh `cp`, `rm`, `grep` có thể không tồn tại hoặc hành xử khác trên Windows và Linux.

### 8.3. Quyền thực thi, kết thúc dòng và encoding

Một script có thể chạy trên macOS nhưng CI Linux báo `Permission denied` nếu bit executable không được commit. Script shell lưu CRLF có thể gặp lỗi khi chạy dưới Linux. Đọc file không đúng encoding có thể làm Java compiler báo `unmappable character` hoặc khiến file resource sinh khác nhau.

Khi lỗi liên quan script, kiểm tra:

- File có ở đúng đường dẫn và được commit không?
- Bit executable có được lưu trong Git không?
- Dòng cuối có CRLF hay LF như công cụ mong đợi?
- File source/resource được đọc với encoding nào?
- Build có phụ thuộc vào locale mặc định của runner không?

Với `<javac>`, nên đặt `encoding="UTF-8"` nếu dự án lưu source UTF-8. Với task ghi file, nên chọn encoding rõ ràng khi task hỗ trợ.

## 9. So sánh log có hệ thống

### 9.1. Chọn mốc log ổn định

Trong `build.xml`, các `echo` có ngữ cảnh giúp đối chiếu các giai đoạn:

```xml
<target name="diagnostic">
    <echo level="info"
          message="[diagnostic] Ant=${ant.version}"/>
    <echo level="info"
          message="[diagnostic] Java=${ant.java.version}; java.home=${java.home}"/>
    <echo level="info"
          message="[diagnostic] release=${java.release}"/>
</target>
```

Nên ghi target, Java release, phiên bản tool và đường dẫn đầu ra ở mức `info`; các đường dẫn phụ hoặc tham số chẩn đoán sâu có thể ở mức `verbose`. Không cần in bí mật hoặc toàn bộ environment.

Mẫu log hữu ích:

```text
[environment][ci] Release đầu ra yêu cầu: 17
[compile] Biên dịch mã nguồn UTF-8
[compile] Hoàn thành biên dịch
[package] Đã tạo dist/demo.jar
[smoke] Chạy class chính từ JAR
[verify][ci] Tất cả bước được yêu cầu đã hoàn thành
```

Nội dung trong ví dụ thể hiện các mốc cần theo dõi; đường dẫn tuyệt đối và định dạng logger thực tế có thể khác.

### 9.2. Cách đọc hai log

Khi một bên lỗi, so sánh theo thứ tự:

1. **Target đầu tiên khác nhau:** chẳng hạn CI chạy `test`, local chỉ chạy `compile`.
2. **Giá trị cấu hình đầu tiên khác nhau:** JDK, property, library path, release.
3. **Task đầu tiên thất bại:** `<javac>`, `<jar>`, `<junit>`, `<exec>` hoặc custom task.
4. **Thông báo lỗi cụ thể:** file/dòng Java, thư viện, HTTP status, mã thoát của lệnh ngoài.
5. **Hậu quả:** artifact không được tạo, test report thiếu, bước sau không chạy.

Hãy ưu tiên **lỗi gốc** xuất hiện gần điểm chuyển từ các target thành công sang target thất bại. Dòng `BUILD FAILED` và stack trace tổng hợp chỉ là điểm kết thúc; một số lần build có nhiều lỗi liên tiếp cần đọc toàn bộ quan hệ nguyên nhân.

### 9.3. Ghi log ở mức nào?

| Tình huống | Lựa chọn |
| --- | --- |
| Build hằng ngày | Mặc định `ant ...`, với các `echo level="info"` quan trọng |
| CI lỗi nhưng chưa rõ đường dẫn | `ant -verbose ...` |
| Cần xem chi tiết Ant/task | `ant -debug ...` |
| Cần lưu log để đối chiếu | `ant -logfile build.log ...` |
| Có property nhạy cảm | Chỉ in một tập property an toàn, không dump tất cả |

`-debug` có thể tạo lượng log lớn và hé lộ thông tin môi trường. Sử dụng có mục đích, kiểm tra lại trước khi đưa log ra ngoài hệ thống được kiểm soát.

## 10. So sánh artifact: cùng BUILD SUCCESSFUL chưa chắc cùng JAR

### 10.1. So sánh mức độ đầu tiên

Khi hai build đều thành công, kiểm tra:

- Có đúng file `dist/demo.jar` không?
- Kích thước file bao nhiêu?
- JAR chứa danh sách class/resource gì?
- Bytecode class có cùng major version không?
- Chạy cùng bộ smoke test/test có cùng kết quả không?
- Khi cần so sánh byte tuyệt đối, mã SHA-256 có giống nhau không?

Trên Linux/macOS:

```bash
jar tf dist/demo.jar
sha256sum dist/demo.jar
javap -verbose -classpath dist/demo.jar com.example.Main
```

Trên Windows PowerShell:

```powershell
jar tf dist/demo.jar
Get-FileHash -Algorithm SHA256 -LiteralPath dist/demo.jar
javap -verbose -classpath dist/demo.jar com.example.Main
```

Sau khi xác minh cùng commit, classpath, compiler và target, mã băm giống nhau là bằng chứng mạnh rằng hai file JAR có byte **giống hệt**. Nhưng mã băm khác nhau cần được điều tra thêm, chưa đủ để khẳng định ứng dụng hành xử khác.

### 10.2. Vì sao SHA-256 khác dù chức năng có thể giống?

JAR là một định dạng archive; dữ liệu byte có thể chịu ảnh hưởng bởi:

- Timestamp của các entry.
- Thứ tự entry hoặc cách nén.
- File metadata, manifest hoặc property sinh trong lúc build.
- Đường dẫn, tên người dùng hoặc thời gian bị nhúng vào resource.
- Phiên bản JDK/Ant/task đóng gói.
- Thư viện và class thực sự khác nhau.

Ví dụ, một `<tstamp>` được đưa trực tiếp vào manifest sẽ khiến nội dung artifact đổi theo thời gian build. Nếu cần reproducible build, trước tiên phải loại bỏ dữ liệu không ổn định hoặc chuẩn hóa chúng bằng cơ chế mà phiên bản Ant và task đóng gói đang sử dụng hỗ trợ.

Cách điều tra:

1. So danh sách entry qua `jar tf`.
2. So những file resource và manifest được nhúng vào JAR.
3. So bytecode của class chính hoặc nguồn sinh mã.
4. So timestamp/metadata của archive.
5. Nếu sự khác biệt chỉ đến từ metadata, quyết định có cần chuẩn hóa theo yêu cầu phát hành hay không.

**Không tự đặt mục tiêu byte-identical** nếu dự án chỉ yêu cầu tương đương về chức năng. Ngược lại, khi công việc yêu cầu kiểm tra nguồn gốc artifact hoặc reproducible build, mã băm phải được kiểm tra nghiêm ngặt cùng quy trình tạo artifact.

### 10.3. Test report là artifact để đối chiếu

Với dự án có `<junit>` hoặc task kiểm thử khác, cần giữ lại:

- Số test được phát hiện và chạy.
- Số failure/error/skip.
- Tên testcase thất bại.
- Phiên bản JVM chạy test.
- Report XML/HTML được CI lưu lại.

Việc local không chạy bộ test vì thiếu target hoặc điều kiện `unless` **không tương đương** với CI chạy test và báo lỗi. Cần xác minh nội dung `depends` và điều kiện skip trong `build.xml`.

## 11. Những nguyên nhân lệch kết quả thường gặp

| Dấu hiệu | Nguyên nhân có thể | Cách xác minh | Hướng xử lý |
| --- | --- | --- | --- |
| Local pass, CI thiếu class | JAR không có trong checkout CI | So `lib/` và compile classpath | Cấp dependency chính thức, kiểm soát phiên bản |
| CI lỗi `invalid source release` | JDK compiler quá cũ | So phiên bản compiler thực tế | Chọn JDK hỗ trợ release yêu cầu |
| CI lỗi file not found | Sai chữ hoa/thường hoặc file chưa commit | So tên file và `git status` | Sửa tên/path và đưa file nguồn vào Git |
| Local pass, CI test fail | Local không chạy cùng target; khác dữ liệu/timezone | So lệnh, báo cáo test, cấu hình test | Chạy đúng verify và cô lập dữ liệu test |
| Local fail, CI pass | Máy local có JAR cũ hoặc JDK khác | Clean build, so JAR/JDK | Chuẩn hóa dependency và toolchain |
| Hai bên pass, JAR hash khác | Timestamp, metadata hoặc resource khác | So entry và manifest | Chuẩn hóa build nếu cần byte-identical |
| CI chỉ fail khi tải dependency | Network, proxy, credentials hoặc registry | Xem task tải dependency và HTTP error | Cấu hình repository/credentials an toàn |
| CI không tạo artifact | Target package bị bỏ qua hoặc sai path | Kiểm tra `depends`, `if/unless`, log package | Đồng bộ target và đường dẫn upload |
| CI báo `Permission denied` | Script thiếu executable bit | Kiểm tra file và metadata Git | Commit bit executable hoặc dùng task đa nền tảng |
| Build sau khi đổi dependency vẫn dùng class cũ | Thư mục output/cache gia tăng | So clean với incremental build | Xác định và loại bỏ đầu ra cũ có kiểm soát |
| CI pass nhưng chạy production lỗi | Runtime JVM/dependency khác CI | So Java runtime và artifact phát hành | Kiểm thử bằng runtime mục tiêu, giữ dependency tương thích |
| Task custom chỉ chạy trên local | JAR của task nằm trong Ant user library | So `-lib`, `ANT_HOME`, user lib | Khai báo task dependency một cách tường minh |

## 12. Thiết lập quy trình đối chiếu có thể lặp lại

Khi một job CI thất bại nhưng máy cá nhân thành công, có thể thực hiện chuỗi sau.

### Bước 1 — Ghi lại bằng chứng từ CI

Ghi **SHA/ref thực tế của checkout**, tên job, OS runner, lệnh Ant và các property không nhạy cảm. Lưu log đầy đủ của target thất bại. Không chỉ sao chép dòng cuối `BUILD FAILED`.

### Bước 2 — Tái hiện cùng revision ở local

Dùng một checkout sạch của commit/ref đã xác định. Kiểm tra `git status --short`; nếu repo phụ thuộc Git submodule hoặc asset được sinh trước build thì cũng phải xử lý cùng quy trình CI.

Không cần xóa hoặc sửa những thay đổi cá nhân trong workspace đang làm việc; có thể dùng thư mục checkout riêng để tránh ảnh hưởng công việc khác.

### Bước 3 — Chạy cùng lệnh và tập target

Nếu CI dùng:

```bash
ant -f build.xml -Dbuild.profile=ci clean verify
```

thì local cũng nên dùng lệnh tương đương. Không so CI `verify` với local `compile` vì phạm vi công việc khác nhau.

### Bước 4 — So toolchain và biến ảnh hưởng

So phiên bản Ant, JDK, compiler, locale/timezone, property file và dependency. Nếu toolchain khác, hãy tái hiện bằng đúng JDK/Ant CI dùng trước khi thay mã nguồn hoặc build logic.

### Bước 5 — Tìm sự sai khác đầu tiên có ý nghĩa

Ví dụ CI báo:

```text
[javac] error: invalid source release: 21
BUILD FAILED
```

Từ đây, ưu tiên tìm **compiler thực tế trên CI**. Việc local chạy JDK 21 còn CI chạy compiler JDK 17 là giả thuyết có thể kiểm chứng; không nên sửa classpath khi chưa có bằng chứng liên quan.

Nếu CI báo `package org.example.api does not exist`, ưu tiên kiểm tra JAR và compile classpath. Nếu cả hai biên dịch xong nhưng chỉ CI test fail, ưu tiên dữ liệu test và runtime thay vì source compiler.

### Bước 6 — Xác minh bằng đầu ra

Sau khi tìm và sửa nguyên nhân, chạy lại toàn bộ chuỗi target tương đương rồi đối chiếu log, báo cáo test và artifact. Nếu cần tính nhất quán byte tuyệt đối, thêm bước so SHA-256 trong điều kiện toolchain và metadata đã được kiểm soát.

### Bước 7 — Làm cho lần chạy sau dễ điều tra hơn

Khi nguyên nhân đã rõ, cập nhật đúng nguồn cấu hình: phiên bản JDK/Ant, dependency, đường dẫn, biến environment, target `depends` hoặc bước CI. Ghi thông tin build không nhạy cảm vào log. Việc thêm một chuỗi thử đi thử lại mà không sửa nguồn gốc khiến cùng lỗi tái diễn.

## 13. Cách giảm chênh lệch local và CI trong dự án lâu dài

Một vài thực hành kỹ thuật phù hợp với dự án Ant:

**Cố định toolchain có chủ đích.** Dự án nên xác định JDK tối thiểu và JDK được kiểm thử, phiên bản Ant hỗ trợ, phiên bản các custom Ant task và dependency. Với pipeline cần tái lập chặt, nên kiểm soát cả image/installer và nguồn download, thay vì dựa vào bản mới nhất trên runner.

**Giữ lệnh kiểm chứng dùng chung.** Duy trì một target như `verify` bao gồm các bước bắt buộc. Local và CI cùng gọi target ấy; CI có thể thêm kiểm tra dành riêng cho triển khai nhưng không âm thầm bỏ qua test chính.

**Làm cho build phụ thuộc rõ ràng vào đầu vào.** Source, resource, dependency và property cần ở những vị trí được khai báo. Tránh vô tình đọc từ thư mục người dùng hoặc cài đặt IDE riêng mà CI không có.

**Không cho artifact cũ quyết định kết quả.** Có target `clean` giới hạn các thư mục output và định kỳ đối chiếu clean build, đặc biệt sau khi thay compiler, JAR hoặc nguồn sinh mã.

**Cô lập các yếu tố thời gian và máy chạy.** Test nên kiểm soát locale, timezone, ngày giờ, thứ tự dữ liệu và cổng mạng khi các yếu tố này ảnh hưởng kết quả. Dữ liệu ngẫu nhiên nên có seed hoặc cách kiểm soát tương đương khi cần tái hiện.

**Không đưa bí mật vào log và artifact.** Bản log dùng để điều tra có thể được chia sẻ trong nhóm; chỉ ghi thông tin thật cần. CI nên cấp credential bằng cơ chế secret phù hợp, với quyền tối thiểu.

**Phân biệt xác nhận build với xác nhận triển khai.** CI có thể tạo JAR thành công nhưng môi trường chạy sản phẩm dùng JVM hoặc thư viện khác. Nếu mục tiêu là tính tương thích triển khai, kiểm thử artifact trên runtime mục tiêu là một phần cần thiết.

## 14. Bài thực hành đối chiếu local và CI

### Bài 1 — Tái hiện lệnh

Dùng dự án ở mục 4. Trên máy có JDK 17 hoặc mới hơn hỗ trợ `release="17"`, chạy:

```bash
ant -Dbuild.profile=local clean verify
ant -Dbuild.profile=ci clean verify
```

Đối chiếu thông báo `[environment]`, `[compile]`, `[package]`, `[smoke]` và `[verify]`. Hai lần cùng chạy các target; thông báo profile có thể khác nhưng bytecode không cần đổi vì profile chỉ được in ra.

### Bài 2 — Tạo khác biệt target có chủ ý

Chạy:

```bash
ant clean compile
```

So với `ant clean verify`. Kiểm tra khi nào `dist/demo.jar` được tạo và khi nào `com.example.Main` được chạy. Từ đó xác định vì sao so lệnh `compile` với `verify` chỉ dựa vào dòng `BUILD SUCCESSFUL` là chưa đủ.

### Bài 3 — Tạo khác biệt JDK

Nếu có JDK 17 và JDK 21, thử thay công cụ dùng để build. Trong cùng source, dùng `-Djava.release=17` và đọc major version bằng `javap -verbose`. Sau đó thử `-Djava.release=21` trên compiler phù hợp. Khi compiler không hỗ trợ một release, hãy đọc lỗi `invalid source release`/`release version ... not supported`.

Bài tập này nhằm hiểu nguyên nhân, không yêu cầu thay JDK hệ thống chỉ để tạo lỗi. Khi kiểm tra so sánh thực tế, luôn xác định JDK đang được Ant sử dụng.

### Bài 4 — Đọc artifact thay vì chỉ nhìn file size

Sau hai lần build cùng revision:

```bash
jar tf dist/demo.jar
javap -verbose -classpath dist/demo.jar com.example.Main
```

Ghi danh sách entry và major version. Sau đó so mã băm SHA-256 tương ứng với hệ điều hành đang dùng. Nếu mã băm khác, thử tìm metadata/timestamp khác nhau trước khi kết luận class thực thi đã thay đổi.

### Bài 5 — Lập bảng chứng cứ sự cố

Khi gặp lỗi CI thật, lập bảng:

| Mục kiểm tra | Local | CI | Đã xác nhận? |
| --- | --- | --- | --- |
| Commit/ref | ... | ... | ... |
| Lệnh Ant/target | ... | ... | ... |
| Ant version | ... | ... | ... |
| JVM chạy Ant | ... | ... | ... |
| JDK/compiler của `<javac>` | ... | ... | ... |
| Release đích | ... | ... | ... |
| Library classpath | ... | ... | ... |
| Clean hay incremental | ... | ... | ... |
| Lỗi/task đầu tiên khác nhau | ... | ... | ... |
| Artifact và kết quả test | ... | ... | ... |

Bảng này buộc việc điều tra đi theo dữ liệu thực thay vì suy đoán. Khi xác định một khác biệt có liên quan trực tiếp, hãy xử lý đúng cấu hình hoặc đầu vào gây ra khác biệt đó, rồi đối chiếu lại với cùng lệnh build.

## 15. Kết luận

Với Apache Ant, hai môi trường chỉ có thể được so sánh đúng khi biết **chúng đang build cái gì, bằng công cụ nào, với property/dependency nào và đã chạy những target nào**. Bắt đầu từ commit/ref và lệnh thực tế, sau đó so compiler, classpath, biến môi trường, cache, log và đầu ra.

Đối với lỗi **FAIL/PASS**, tìm task và thông báo lỗi gốc. Đối với **PASS/PASS nhưng artifact khác**, so danh sách entry, bytecode và metadata trước khi đánh giá sự khác biệt có ảnh hưởng chức năng hay yêu cầu reproducible build. Quy trình đối chiếu được ghi lại rõ ràng sẽ giúp một lỗi chỉ xảy ra trên CI trở thành một tình huống có thể tái hiện và sửa được trên máy phát triển.
