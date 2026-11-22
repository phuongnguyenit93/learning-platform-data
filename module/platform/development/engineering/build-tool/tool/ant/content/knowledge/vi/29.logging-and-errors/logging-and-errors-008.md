# Chẩn đoán lỗi biên dịch, classpath và phiên bản bytecode trong Apache Ant

## 1. Mục tiêu và mô hình chẩn đoán

Khi chạy `ant compile`, Ant có thể báo `BUILD FAILED` vì lỗi mã Java, thiếu thư viện, chọn sai JDK hoặc bytecode không tương thích. Dòng `BUILD FAILED` chỉ cho biết kết quả chung; nguyên nhân thường nằm trong các thông báo của `<javac>` ngay phía trên. Muốn xử lý đúng, cần xác định lỗi xuất hiện ở giai đoạn **biên dịch** hay **chạy chương trình**, rồi kiểm tra công cụ và classpath của chính giai đoạn đó.

| Nhóm lỗi | Dấu hiệu | Vị trí cần điều tra |
| --- | --- | --- |
| Mã nguồn | `cannot find symbol`, `';' expected`, `duplicate class` | Tệp `.java`, tên package, import, phiên bản API |
| Compile classpath | `package ... does not exist`, `cannot access ...` | Các JAR và thư mục mà `<javac>` có thể đọc |
| Cấu hình compiler | `invalid source release`, `release version ... not supported` | JDK/compiler thực tế, `source`, `target`, `release` |
| Bytecode của thư viện | `bad class file ... wrong version` | Phiên bản JAR đầu vào và JDK biên dịch |
| Runtime classpath | `ClassNotFoundException`, `NoClassDefFoundError` | Các JAR và thư mục được JVM dùng khi chạy |
| Bytecode lúc chạy | `UnsupportedClassVersionError` | Major version của `.class` và phiên bản JVM |

Sơ đồ luồng thực thi:

```text
build.xml
  |
  +-- Ant chạy target compile
  |      |
  |      +-- <javac> đọc source và compile classpath
  |      +-- Compiler kiểm tra cú pháp, kiểu dữ liệu và API
  |      +-- Sinh file .class vào build/classes
  |
  +-- Ant chạy target run
         |
         +-- <java> dùng runtime classpath
         +-- JVM kiểm tra/nạp bytecode rồi thực thi chương trình
```

**Phân biệt quan trọng:** Ant là công cụ điều phối; `<javac>` gọi trình biên dịch Java. Biên dịch thành công không đồng nghĩa rằng classpath lúc chạy đầy đủ hoặc JVM chạy hiểu được bytecode đã tạo.

## 2. Thu thập thông tin hệ thống và log

Bắt đầu từ các lệnh:

```bash
ant -version
java -version
javac -version
ant -diagnostics
ant -verbose compile
```

Trong đó:

- `ant -version` cho biết phiên bản Ant được gọi.
- `java -version` và `javac -version` cho biết các chương trình mà shell đang tìm được; chúng có thể **khác** JVM hoặc compiler mà Ant đang dùng.
- `ant -diagnostics` hiển thị thông tin về môi trường Ant, Java và các thư viện, hữu ích khi so sánh máy cá nhân với CI.
- `ant -verbose compile` hiển thị nhiều chi tiết hơn về target, tác vụ và đường dẫn. Chỉ dùng `ant -debug compile` khi log verbose chưa đủ.

Để lưu thông báo toàn build:

```bash
ant -logfile ant-build.log -verbose compile
```

Khi gửi log cho người khác, cần xem lại các giá trị property, đường dẫn và thông tin nhạy cảm có thể bị in ra. Không nên đăng nguyên log chứa mật khẩu hoặc token.

### 2.1. Xác định JDK mà Ant thực sự sử dụng

Trong `build.xml`, có thể in:

```xml
<target name="environment">
    <echo level="info"
          message="[environment] ant.java.version=${ant.java.version}; java.home=${java.home}"/>
</target>
```

`ant.java.version` mô tả phiên bản Java chạy Ant, còn `java.home` cho biết vị trí runtime của JVM ấy. Ngoài ra hãy kiểm tra biến môi trường:

Trên Windows PowerShell:

```powershell
$env:JAVA_HOME
Get-Command java
Get-Command javac
```

Trên Linux/macOS:

```bash
echo "$JAVA_HOME"
command -v java
command -v javac
```

Đừng vội kết luận compiler đã đúng chỉ vì `javac -version` ở terminal đúng. `<javac>` có thể dùng compiler trong JVM chạy Ant khi `fork="false"`, hoặc compiler ngoài khi `fork="true"`; thuộc tính `executable` có thể chọn một binary cụ thể.

## 3. Ví dụ Ant tự chứa để tái hiện lỗi

Giả sử dự án Java có cấu trúc:

```text
ant-diagnostic-demo/
├── build.xml
├── src/
│   └── com/example/App.java
├── lib/                 # Chứa JAR nếu có
└── build/               # Ant tạo đầu ra
    └── classes/
```

Tạo `src/com/example/App.java`:

```java
package com.example;

public class App {
    public static void main(String[] args) {
        System.out.println("Hello from Ant");
    }
}
```

Tạo `build.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-diagnostic-demo" default="compile" basedir=".">

    <property name="java.release" value="17"/>
    <property name="src.dir" location="src"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="lib.dir" location="lib"/>

    <!-- Lấy các JAR hiện có; thư mục lib có thể chưa tồn tại. -->
    <path id="compile.classpath">
        <fileset dir="${lib.dir}"
                 includes="**/*.jar"
                 erroronmissingdir="false"/>
    </path>

    <target name="environment">
        <echo level="info"
              message="[environment] Java của Ant: ${ant.java.version}; ${java.home}"/>
        <pathconvert property="compile.cp.text"
                     refid="compile.classpath"
                     pathsep=" | "/>
        <echo level="verbose"
              message="[environment] Compile classpath: ${compile.cp.text}"/>
    </target>

    <target name="compile" depends="environment">
        <available file="${src.dir}" type="dir"
                   property="src.exists"/>
        <fail unless="src.exists"
              message="[compile] Thiếu thư mục ${src.dir}"/>

        <mkdir dir="${classes.dir}"/>
        <echo level="info"
              message="[compile] Biên dịch cho Java ${java.release}"/>

        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               release="${java.release}"
               encoding="UTF-8"
               includeantruntime="false"
               fork="true">
            <classpath refid="compile.classpath"/>
        </javac>

        <echo level="info" message="[compile] Hoàn thành"/>
    </target>

    <target name="run" depends="compile">
        <java classname="com.example.App"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <path refid="compile.classpath"/>
            </classpath>
        </java>
    </target>

    <target name="clean">
        <delete dir="build"/>
    </target>

</project>
```

Ví dụ dùng `release="17"` nên cần compiler JDK 17 hoặc mới hơn có hỗ trợ đích Java 17. Khi chạy trên JDK cũ hơn, lỗi tương thích compiler là điều được dự kiến.

Thử:

```bash
ant compile
ant run
ant -verbose compile
ant clean
ant compile
```

Ở đây `compile.classpath` cung cấp JAR cho trình biên dịch, còn `run` thêm thư mục `build/classes` vào runtime classpath. Các `.class` của dự án chưa nằm trong `lib` và không tự động xuất hiện ở runtime nếu bỏ `build/classes`.

## 4. Đọc lỗi compiler theo dòng chỉ vị trí

Compiler thường cho biết **tên file, số dòng, lỗi và symbol**. Ví dụ:

```text
[javac] src/com/example/App.java:8: error: cannot find symbol
[javac]     UserService service = new UserService();
[javac]     ^
[javac]   symbol:   class UserService
[javac]   location: class App
BUILD FAILED
```

Dòng có ích nhất là `cannot find symbol`, không phải `BUILD FAILED`. Cần kiểm tra:

1. Có file `UserService.java` hoặc class thư viện tương ứng không?
2. Tên class có đúng chữ hoa/chữ thường và đúng package không?
3. Có thiếu `import` không?
4. Package tương ứng có nằm trong một JAR mà compiler được phép đọc không?
5. Dependency hiện tại có còn chứa class hoặc method đó không?

Không phải mọi lỗi `cannot find symbol` đều do thiếu JAR. Lỗi đánh máy, import sai hoặc dùng API của phiên bản thư viện khác cũng gây cùng thông báo.

### 4.1. `package ... does not exist`

Ví dụ:

```text
[javac] src/com/example/App.java:3: error:
[javac] package org.example.client does not exist
[javac] import org.example.client.ApiClient;
```

Kiểm tra nơi khai báo `org.example.client.ApiClient`. Nếu nằm trong JAR, cần xác minh JAR đó thực sự có trong compile classpath. Liệt kê nội dung JAR bằng:

```bash
jar tf lib/example-client.jar
```

Class tương ứng thường xuất hiện dưới dạng:

```text
org/example/client/ApiClient.class
```

Nếu không tồn tại, có thể đang dùng sai artifact, sai phiên bản hoặc nhầm tên package. Nếu có class trong JAR nhưng compiler vẫn báo thiếu, quay lại phần `<classpath>` của target đang lỗi.

### 4.2. Một số thông báo khác

| Lỗi | Nguyên nhân thường gặp | Cần làm |
| --- | --- | --- |
| `';' expected`, `illegal start of expression` | Sai cú pháp Java | Mở đúng file/dòng compiler chỉ ra |
| `class App is public, should be declared in a file named App.java` | Tên file không khớp tên `public class` | Sửa tên file hoặc class |
| `duplicate class: com.example.App` | Có hai định nghĩa cùng tên đầy đủ | Rà nguồn và thư mục sinh mã |
| `unmappable character for encoding ...` | Encoding của source và `<javac>` không khớp | Kiểm tra mã hóa thực tế, dùng `encoding` phù hợp |
| `cannot access SomeClass` | Class phụ thuộc không đọc được, thiếu hoặc khác phiên bản | Đọc chi tiết bên dưới lỗi và kiểm tra JAR |
| `module not found: ...` | Dự án module Java thiếu module được khai báo | Kiểm tra `module-info.java` và module path |

Đối với tệp Java lưu UTF-8, khai báo `encoding="UTF-8"` là thích hợp. Tuy nhiên thuộc tính này không tự chuyển một file mã hóa kiểu khác thành UTF-8.

## 5. Classpath chính xác là gì?

**Classpath** là tập đường dẫn tới thư mục class và các tệp JAR. Java tra cứu class theo **tên đầy đủ**. Ví dụ tên `com.example.util.Formatter` tương ứng với:

```text
build/classes/com/example/util/Formatter.class
```

hoặc entry:

```text
com/example/util/Formatter.class
```

trong JAR. Một class ở sai thư mục tương ứng package có thể không được tìm thấy dù tệp vẫn tồn tại trên đĩa.

Trong Ant, tập hợp đường dẫn có thể được định nghĩa và dùng lại:

```xml
<path id="compile.classpath">
    <pathelement location="build/shared-classes"/>
    <fileset dir="lib" includes="**/*.jar"
             erroronmissingdir="false"/>
</path>

<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src"
           destdir="build/classes"
           release="17"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Đây là đoạn ví dụ độc lập, giả định `src` tồn tại và `build/shared-classes` đã được tạo nếu có lớp phụ thuộc. Ant không tự biên dịch mã nguồn của module khác chỉ nhờ một đường dẫn trong `<path>`.

### 5.1. Có JAR nhưng vẫn thiếu class

Những nguyên nhân cần phân biệt:

- JAR nằm trên máy nhưng **không có trong classpath** thực tế.
- JAR chứa package/class khác với tên source đang import.
- Thư mục `lib` có nhiều phiên bản cùng một thư viện, khiến class được lấy từ phiên bản không mong muốn.
- Class của module khác chưa được biên dịch; target phụ thuộc chưa chạy.
- Class có mặt nhưng compiler không đọc được bytecode do phiên bản quá mới.
- JAR được dùng lúc compile nhưng không có trong **runtime classpath**.

`<fileset dir="lib" includes="**/*.jar"/>` lấy các JAR đang tồn tại, **không tự tải** dependency từ Maven Central. Nếu `api.jar` còn phụ thuộc `model.jar`, Ant cũng không tự động suy ra và tải JAR còn thiếu trừ khi dự án đã cấu hình một cơ chế quản lý dependency riêng.

### 5.2. Biên dịch được nhưng chạy lỗi

Ví dụ `<javac>` thấy `lib/example-api.jar`, nhưng lệnh chạy chỉ dùng:

```bash
java -cp build/classes com.example.App
```

Khi `App` cần class trong `example-api.jar`, JVM có thể báo lỗi nạp class. Thực thi trong Ant cần cung cấp cả thư mục output và thư viện:

```xml
<target name="run" depends="compile">
    <java classname="com.example.App"
          fork="true"
          failonerror="true">
        <classpath>
            <pathelement location="build/classes"/>
            <fileset dir="lib" includes="**/*.jar"
                     erroronmissingdir="false"/>
        </classpath>
    </java>
</target>
```

Phân biệt một số lỗi lúc chạy:

| Lỗi | Cách đọc |
| --- | --- |
| `ClassNotFoundException` | Trình nạp class không tìm được class được yêu cầu |
| `NoClassDefFoundError` | Không nạp/khởi tạo được class cần dùng; có thể thiếu class phụ thuộc, nhưng phải đọc nguyên nhân sâu hơn |
| `NoSuchMethodError` | Thường là sai lệch nhị phân giữa phiên bản thư viện khi biên dịch và khi chạy |
| `UnsupportedClassVersionError` | JVM không hiểu phiên bản bytecode của class |

`NoSuchMethodError` không được xử lý bằng cách thêm bừa mọi phiên bản JAR vào classpath. Nên tìm bản được compiler dùng và so sánh với bản hiện diện khi chạy.

## 6. Phiên bản bytecode và lỗi không tương thích JVM

File `.class` chứa một **major version**. Những mốc phổ biến:

| Java release | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Java 21 thường tạo classfile major 65. JVM Java 17 chỉ hỗ trợ đến major 61, nên không chạy trực tiếp class được biên dịch cho Java 21.

Kiểm tra class đang có:

```bash
javap -verbose build/classes/com/example/App.class
```

Trong kết quả, tìm:

```text
major version: 61
```

Với một class nằm trong JAR:

```bash
jar tf lib/example-api.jar
javap -verbose -classpath lib/example-api.jar org.example.api.Client
```

Tên class phải tồn tại thật trong JAR. Nếu phiên bản `javap` đang dùng quá cũ, có thể cần `javap` từ một JDK mới hơn để đọc classfile.

### 6.1. `UnsupportedClassVersionError`

Ví dụ:

```text
java.lang.UnsupportedClassVersionError:
com/example/App has been compiled by a more recent version
of the Java Runtime (class file version 65.0),
this version of the Java Runtime only recognizes
class file versions up to 61.0
```

Đây là **lỗi ở lúc chạy**: file `App.class` nhắm Java 21 nhưng JVM thực thi là Java 17.

Giải pháp đúng tùy hợp đồng triển khai:

1. Chạy bằng JVM đủ mới nếu ứng dụng và hệ thống cho phép.
2. Nếu phải chạy Java 17, biên dịch mã nguồn cho Java 17 và kiểm tra những API đang được sử dụng.
3. Nếu bytecode quá mới nằm trong JAR bên thứ ba, chọn phiên bản JAR hỗ trợ Java 17 hoặc nâng JVM. Việc biên dịch lại source của ứng dụng không thay đổi JAR bên thứ ba.

Không thể giảm major version bằng cách sửa vài byte đầu file: nội dung bytecode và API vẫn có thể không tương thích.

### 6.2. `bad class file ... wrong version`

Ví dụ:

```text
bad class file: lib/example-api.jar(.../Client.class)
class file has wrong version 65.0, should be 61.0
```

Lỗi này phát sinh **trong lúc compiler đọc thư viện**, trước khi chạy chương trình. Compiler Java 17 không đọc được classfile Java 21. Hãy xác định JAR trong thông báo, sau đó chọn JDK compiler mới hơn hoặc một bản thư viện được biên dịch cho Java 17.

Hai thông báo đều liên quan bytecode, nhưng khác vị trí:

- `bad class file` khi compile → so sánh **compiler với dependency**.
- `UnsupportedClassVersionError` khi run → so sánh **JVM với class phải thực thi**.

## 7. `source`, `target` và `release`

Đây là ba cấu hình khác nhau của `<javac>`:

| Thuộc tính | Ý nghĩa | Giới hạn |
| --- | --- | --- |
| `source` | Cấp độ cú pháp ngôn ngữ Java | Không tự đặt bytecode đầu ra |
| `target` | Phiên bản bytecode muốn sinh | Không ngăn dùng API JDK mới |
| `release` | Ràng buộc cú pháp, bytecode và API nền tảng của Java release đích | Compiler phải hỗ trợ release ấy |

Ưu tiên `release` với compiler/JDK và Ant hỗ trợ:

```xml
<javac srcdir="src"
       destdir="build/classes"
       release="17"
       includeantruntime="false"/>
```

Với compiler hiện đại, `release="17"` không chỉ sinh bytecode có thể chạy trên Java 17 mà còn hạn chế việc tham chiếu API nền tảng mới hơn Java 17. `release` **không đảm bảo** các dependency bên thứ ba tương thích nếu chúng chứa classfile quá mới hoặc API riêng không phù hợp.

Cấu hình truyền thống:

```xml
<javac srcdir="src"
       destdir="build/classes"
       source="17"
       target="17"
       includeantruntime="false"/>
```

`source="17" target="17"` giới hạn cú pháp và bytecode, nhưng nếu compiler là JDK 21 thì mã vẫn có nguy cơ biên dịch với một API nền tảng chỉ có trong JDK 21. Bởi vậy, khi đặt mục tiêu tương thích runtime cũ, `release` thường rõ ràng và an toàn hơn.

### 7.1. `invalid source release` / `release version ... not supported`

Ví dụ:

```text
error: invalid source release: 21
```

hoặc:

```text
error: release version 21 not supported
```

Thông báo chỉ ra rằng compiler được chọn không hiểu mức Java mà build yêu cầu. Kiểm tra `source`, `target`, `release` và JDK thực tế của `<javac>`. Nếu mã thật sự dùng cú pháp Java 21, phải chọn compiler hỗ trợ Java 21; đổi `source="21"` xuống `17` đơn thuần sẽ không làm cú pháp mới trở nên hợp lệ.

Có thể ép `<javac>` dùng một compiler ngoài cụ thể:

```xml
<!-- Ví dụ đường dẫn trên Linux; điều chỉnh theo máy thật. -->
<property name="jdk.javac" location="/opt/jdk-21/bin/javac"/>

<javac srcdir="src"
       destdir="build/classes"
       release="17"
       fork="true"
       executable="${jdk.javac}"
       includeantruntime="false"/>
```

Đường dẫn này là ví dụ cho Linux; trên Windows hãy dùng đường dẫn thực tế đến `javac.exe`. Với CI đa nền tảng, có thể truyền đường dẫn qua property hoặc cấu hình môi trường. Lưu ý `fork="true"` chạy compiler ngoài, còn `fork="false"` dùng compiler theo cơ chế trong tiến trình Ant.

## 8. Thứ tự target và đầu ra cũ

### 8.1. Class phụ thuộc chưa được build

Giả sử ứng dụng cần class nằm trong `build/shared-classes`. Khai báo classpath tới thư mục đó không làm Ant tự biên dịch module dùng chung. Cần thể hiện thứ tự:

```xml
<target name="compile-shared">
    <mkdir dir="build/shared-classes"/>
    <javac srcdir="shared-src"
           destdir="build/shared-classes"
           release="17"
           includeantruntime="false"/>
</target>

<target name="compile-app" depends="compile-shared">
    <mkdir dir="build/app-classes"/>
    <javac srcdir="app-src"
           destdir="build/app-classes"
           release="17"
           includeantruntime="false">
        <classpath>
            <pathelement location="build/shared-classes"/>
        </classpath>
    </javac>
</target>
```

Ví dụ riêng này giả định đã có `shared-src` và `app-src`. `depends` bảo đảm target tạo class dùng chung chạy trước target cần chúng. Nếu thứ tự bị thiếu, một số lỗi có thể trông giống thiếu dependency ngoài.

### 8.2. Vì sao clean build hữu ích?

`<javac>` thực hiện biên dịch gia tăng dựa chủ yếu vào source và file class đầu ra; nó không phải công cụ phân tích đầy đủ mọi thay đổi API trong tất cả dependency. Khi thay JDK, đổi phiên bản JAR hoặc nghi có `.class` cũ, thử:

```bash
ant clean
ant compile
```

Nếu dùng build mẫu ở mục 3, `clean` chỉ xóa thư mục `build` do dự án quản lý. Không cần xóa rộng hơn. Clean build giúp tránh trộn classfile được tạo bằng các cấu hình khác nhau, nhưng không sửa được lỗi thiếu class hay version không tương thích còn tồn tại ở input.

## 9. Quy trình chẩn đoán cụ thể

Giả sử log CI kết thúc bằng:

```text
[javac] error: invalid source release: 21
BUILD FAILED
```

Thực hiện tuần tự:

1. **Xác định nơi lỗi:** thông báo từ `<javac>`, tức là compiler không chấp nhận `source` đang yêu cầu; chưa liên quan tới runtime classpath.
2. **Tìm cấu hình:** kiểm tra `source`, `target`, `release` và property truyền vào target; xác nhận dự án thật sự cần Java 21.
3. **Kiểm tra công cụ:** so sánh Java chạy Ant, `javac` bên ngoài và `fork/executable` trong build; CI có thể đang dùng JDK 17.
4. **Sửa theo yêu cầu:** nếu project cần Java 21 thì dùng compiler hỗ trợ Java 21; nếu hợp đồng chạy Java 17 thì chỉnh source và dependency để tương thích thật sự rồi chọn `release="17"`.
5. **Kiểm tra đầu ra:** biên dịch lại, dùng `javap -verbose` kiểm tra major version, rồi chạy ứng dụng với JVM đích.

Nếu log thay bằng `package ... does not exist`, thứ tự điều tra chuyển sang xác định package/class và compile classpath. Nếu `compile` thành công nhưng `run` báo `NoClassDefFoundError`, ưu tiên kiểm tra runtime classpath và nguyên nhân sâu hơn trong stack trace. Nếu thư viện có major version quá mới, cần đổi compiler hoặc thư viện; chỉ tăng log level không giải quyết được lỗi bytecode.

## 10. Bảng thao tác nhanh

| Tình huống | Cách kiểm tra ngay | Hướng sửa |
| --- | --- | --- |
| Không biết Ant gọi Java nào | `ant -diagnostics`, `${java.home}`, cấu hình `fork/executable` | Chuẩn hóa JDK/launcher giữa các máy |
| `cannot find symbol` | Đọc tên symbol, dòng Java, import và API | Sửa source hoặc dependency tương ứng |
| `package ... does not exist` | `jar tf` và `<classpath>` | Bổ sung đúng JAR/đường dẫn hoặc sửa package |
| `bad class file ... 65.0 ... 61.0` | Xác định class/JAR lỗi và compiler | Chọn compiler hoặc JAR có bytecode tương thích |
| `UnsupportedClassVersionError` | `java -version` tại môi trường chạy, `javap -verbose` | Nâng runtime hoặc biên dịch lại cho release hỗ trợ |
| `ClassNotFoundException` | Kiểm tra runtime classpath | Thêm đúng thư mục/JAR và kiểm tra tên class |
| `NoSuchMethodError` | Đối chiếu JAR lúc compile và run | Đồng bộ phiên bản thư viện tương thích |
| Chỉ CI thất bại | So sánh JDK, Ant, property và đường dẫn giữa CI/local | Cố định công cụ và cấu hình đầu vào |
| Thay JAR mà lỗi vẫn cũ | `ant clean` rồi `ant compile` | Loại bỏ output cũ, sau đó kiểm tra dependency thực |

Không dùng `failonerror="false"` trên `<javac>` chỉ để bỏ qua lỗi. Tùy chọn đó có thể khiến pipeline tiếp tục với các file class thiếu hoặc lỗi thời. Nếu compiler thực sự thất bại, build thông thường nên thất bại rõ ràng để tránh tạo artifact sai.

## 11. Bài thực hành

**Bài 1 — Tạo lỗi symbol.** Dùng dự án ở mục 3, thêm dòng `MissingService service = new MissingService();` vào `main` khi chưa khai báo class. Chạy `ant clean` và `ant compile`; xác định tên file, số dòng, symbol được compiler báo. Xóa dòng lỗi và chạy lại.

**Bài 2 — Quan sát classpath.** Tạo một class phụ thuộc ở dự án riêng, đóng gói thành JAR và đặt trong `lib`. Import class đó từ `App.java` rồi biên dịch. Di chuyển JAR ra khỏi `lib`, chạy clean build và đọc `package ... does not exist` hoặc `cannot find symbol`. Khôi phục JAR, dùng `jar tf` xác nhận đường dẫn class và `ant -verbose compile` kiểm tra đường dẫn build thấy.

**Bài 3 — Kiểm tra bytecode.** Biên dịch với `-Djava.release=17` rồi dùng `javap -verbose` xác nhận major 61. Nếu có JDK 21 để compile và JDK 17 để chạy, thử `-Djava.release=21`, quan sát major 65 và lỗi `UnsupportedClassVersionError` khi chạy file class bằng Java 17. Khôi phục release 17 cho dự án học tập.

**Bài 4 — Đối chiếu hai môi trường.** Ghi `ant -version`, `java -version`, `javac -version` và `ant.java.version` ở máy phát triển và CI. Nếu có khác biệt, xác định thành phần ảnh hưởng trực tiếp đến `<javac>`. Bài này hữu ích ngay cả khi cả hai build đều đang thành công.

Khi chẩn đoán Ant, cần giữ ranh giới rõ giữa **lỗi source**, **thiếu dependency**, **compiler không tương thích** và **JVM không đọc được bytecode**. Một tên class, đường dẫn JAR, major version hoặc dòng lỗi compiler cụ thể thường có giá trị hơn nhiều lần thử sửa cấu hình không có căn cứ.
