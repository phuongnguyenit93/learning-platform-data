# javap, jar và jdeps trong điều tra bytecode, JAR và phụ thuộc

## 1. Ba công cụ phục vụ ba câu hỏi khác nhau

Khi một ứng dụng Java gặp **ClassNotFoundException**, **NoClassDefFoundError**, **NoSuchMethodError**, **UnsupportedClassVersionError**, lỗi JPMS/module path hoặc nghi ngờ JAR chứa bản class không đúng, việc đọc source code thôi chưa đủ. JVM thực thi **class files đã biên dịch** và nạp chúng thông qua classpath, module path, ClassLoader và các quy tắc liên kết runtime.

Ba công cụ đi cùng JDK giúp thu thập bằng chứng từ artifact thật:

- **javap** — *Java class file disassembler*: “Class này đã được biên dịch thành **bytecode, descriptors, constant pool, flags và metadata** nào?”
- **jar** — *Java archive tool*: “**JAR có những entries nào**, manifest/module descriptor gì, có đúng class/resource/provider file cần thiết không?”
- **jdeps** — *Java class dependency analyzer*: “Bytecode của artifact **tham chiếu trực tiếp đến class/package/module nào** và những phụ thuộc nào đang thiếu hoặc thuộc JDK internal APIs?”

Ba công cụ này **không tương đương** và không tự cho biết chính xác runtime đã chọn defining loader nào. Muốn điều tra class-loading thật, phải ghép bằng chứng tĩnh với runtime logs, exception/cause, classpath/module path và **Class.getClassLoader()**.

### Bảng định hướng

| Triệu chứng / câu hỏi | Bắt đầu bằng | Vì sao |
| --- | --- | --- |
| “Class X có nằm trong JAR hay không?” | **jar --list** | Xem đúng đường dẫn entry của class/resource. |
| “JAR có module-info hay chỉ automatic module?” | **jar --describe-module** | Xem descriptor hoặc automatic module được suy ra. |
| “Method được compile có descriptor gì?” | **javap -s -p** | Thấy kiểu JVM, overload, return/parameters. |
| “Bytecode gọi invokevirtual hay invokeinterface?” | **javap -c -p** | Disassemble instructions và symbolic references. |
| “Class file dành cho Java 17 hay Java mới hơn?” | **javap -verbose** | Xem major/minor version. |
| “Ứng dụng thiếu một thư viện nào?” | **jdeps --missing-deps** | Tìm class references không giải quyết được khi thiếu dependency path. |
| “app.jar phụ thuộc vào JAR/module nào?” | **jdeps -summary** | Tổng hợp phụ thuộc tĩnh. |
| “API public đang phơi bày type từ thư viện nào?” | **jdeps -apionly** | Giới hạn vào signatures/API surface. |
| “Có gọi JDK internal API?” | **jdeps -jdkinternals** | Tìm tham chiếu tĩnh đến các JDK internals. |
| “Thứ tự ClassLoader nào thực sự được dùng?” | **Runtime evidence** | javap/jar/jdeps không thay thế quan sát JVM. |

## 2. Điều kiện tiên quyết và nguyên tắc chẩn đoán

Bài dùng **Java 17+**, minh họa kiểm chứng trên **OpenJDK 21**. Cả ba công cụ là **JDK tools**, không phải ứng dụng tự động có trong Java runtime tối giản.

Xác minh toolchain:

~~~bash
java -version
javac -version
javap -version
jar --version
jdeps --version
~~~

Output số phiên bản tùy máy. **Đừng giả định** công cụ JDK đang trỏ cùng Java runtime dùng để chạy production: PATH, JAVA_HOME, container images và build runners có thể chọn bản Java khác.

Khi điều tra lỗi deployment, cần ghi lại tối thiểu:

1. JDK version dùng **javac** để build.
2. JDK/JVM version chạy application.
3. Classpath/module path thật của tiến trình.
4. JAR thực tế được deploy, **không phải JAR trong source/build directory khác**.
5. Full exception message/cause, bao gồm tên class, method descriptor, module và loader nếu có.
6. Source/manifest/module-info/resource entries của chính artifact.
7. Mọi custom ClassLoader, plugin layer, TCCL và chiến lược parent/child delegation.

**Nguyên tắc:** kiểm tra một artifact cụ thể trước, sau đó điều tra đường lựa chọn artifact và loader lúc runtime. File có class hợp lệ **không có nghĩa JVM chắc chắn đã load class ấy**.

## 3. Tạo bộ ví dụ tái hiện để thực hành

Chúng ta sẽ xây **hai JAR riêng**:

- **greeting-lib.jar** chứa interface **lab.api.Greeting** và implementation **lab.impl.GreetingImpl**.
- **app.jar** chứa **lab.app.Main**, được compile chống lại thư viện nhưng **không đóng gói classes của library** vào app.jar.

Nhờ đó ta có thể kiểm tra một lỗi thật: app.jar có entry Main, nhưng nếu chạy mà quên greeting-lib.jar sẽ thiếu phụ thuộc runtime.

Cấu trúc source:

~~~text
project/
└── src/
    ├── lab/
    │   ├── api/Greeting.java
    │   ├── impl/GreetingImpl.java
    │   └── app/Main.java
    ├── classes-lib/           (tạo khi biên dịch)
    ├── classes-app/           (tạo khi biên dịch)
    ├── libs/greeting-lib.jar  (tạo khi đóng gói)
    └── app.jar                (tạo khi đóng gói)
~~~

Các tệp output ở cùng cấp với **src/**; phần cây trên nhóm theo ý nghĩa. Đứng ở thư mục project khi chạy lệnh.

### 3.1 Source của shared API

**src/lab/api/Greeting.java**:

~~~java
package lab.api;

public interface Greeting {
    String hello(String name);
}
~~~

### 3.2 Source của implementation

**src/lab/impl/GreetingImpl.java**:

~~~java
package lab.impl;

import lab.api.Greeting;

public final class GreetingImpl implements Greeting {
    public GreetingImpl() {
    }

    @Override
    public String hello(String name) {
        return "Hello, " + name;
    }
}
~~~

### 3.3 Source của application

**src/lab/app/Main.java**:

~~~java
package lab.app;

import lab.api.Greeting;
import lab.impl.GreetingImpl;

public final class Main {
    public static void main(String[] args) {
        Greeting greeting = new GreetingImpl();
        System.out.println(greeting.hello("Java"));
    }
}
~~~

### 3.4 Biên dịch và đóng gói

Từ thư mục project, tạo những thư mục output cần thiết:

~~~bash
mkdir -p classes-lib classes-app libs
javac --release 17 -g -d classes-lib src/lab/api/Greeting.java src/lab/impl/GreetingImpl.java
javac --release 17 -g -cp classes-lib -d classes-app src/lab/app/Main.java
jar --create --file libs/greeting-lib.jar -C classes-lib .
jar --create --file app.jar --main-class lab.app.Main -C classes-app .
~~~

Dấu **-g** yêu cầu tạo debugging information thích hợp, để **javap -l** có dữ liệu line/local variable tables. **--release 17** bảo đảm class-file target và tập API Java 17 tương thích, ngay cả khi đang dùng javac 21.

Trong **Windows PowerShell 5.x** dùng:

~~~powershell
New-Item -ItemType Directory -Force classes-lib, classes-app, libs | Out-Null
javac --release 17 -g -d classes-lib src/lab/api/Greeting.java src/lab/impl/GreetingImpl.java
javac --release 17 -g -cp classes-lib -d classes-app src/lab/app/Main.java
jar --create --file libs/greeting-lib.jar -C classes-lib .
jar --create --file app.jar --main-class lab.app.Main -C classes-app .
~~~

Nếu tạo các source files trên Windows, đảm bảo mã UTF-8 thích hợp với môi trường compiler; ví dụ này dùng literals ASCII nên không phụ thuộc encoding locale.

### 3.5 Chạy với đầy đủ dependency

Linux/macOS:

~~~bash
java -cp "app.jar:libs/greeting-lib.jar" lab.app.Main
~~~

Windows PowerShell:

~~~powershell
java -cp "app.jar;libs/greeting-lib.jar" lab.app.Main
~~~

**Stdout đã chạy thực tế trên OpenJDK 21:**

~~~text
Hello, Java
~~~

Nếu chỉ chạy:

~~~bash
java -jar app.jar
~~~

trong setup này, lệnh **không đưa greeting-lib.jar vào classpath**. Trên OpenJDK 21, kết quả là:

~~~text
Error: Unable to initialize main class lab.app.Main
Caused by: java.lang.NoClassDefFoundError: lab/api/Greeting
~~~

**Vì sao?** JAR **app.jar** có **Main-Class**, nhưng manifest chưa có **Class-Path** trỏ đến thư viện và lệnh java -jar không lấy -cp bên ngoài tùy tiện làm đường nạp bổ sung. Bản app.jar không chứa lab/api/Greeting.class. Đây là fixture để dùng cả **jar** và **jdeps** tìm nguyên nhân.

## 4. Công cụ jar: kiểm tra đúng contents của archive

### 4.1 Liệt kê entries

Hai cách tương đương:

~~~bash
jar --list --file libs/greeting-lib.jar
jar tf libs/greeting-lib.jar
~~~

Với JAR thư viện của ví dụ, danh sách gồm:

~~~text
META-INF/
META-INF/MANIFEST.MF
lab/
lab/api/
lab/api/Greeting.class
lab/impl/
lab/impl/GreetingImpl.class
~~~

Với app.jar:

~~~bash
jar --list --file app.jar
~~~

Các entries gồm:

~~~text
META-INF/
META-INF/MANIFEST.MF
lab/
lab/app/
lab/app/Main.class
~~~

**Kết luận chẩn đoán:** **Greeting.class không nằm trong app.jar**. Nếu application launcher chỉ dùng app.jar mà không có library JAR, dependency đó có thể bị thiếu.

**Đường entry JAR dùng dấu /, không dùng dấu chấm:** Class **lab.api.Greeting** ứng với **lab/api/Greeting.class**. Tên **Greeting.class** ở sai đường package có thể khiến class loader không tìm đúng binary name.

### 4.2 Kiểm tra tên package và duplicate entries

Nếu nghi trùng version của một class:

~~~bash
jar --list --file libs/greeting-lib.jar
jar --list --file app.jar
~~~

So sánh **đầy đủ đường entry**, không chỉ filename cuối. JAR có thể chứa nhiều classes tên **Helper.class** ở package khác nhau mà không có lỗi.

**JAR A và JAR B cùng có lab/api/Greeting.class chưa chứng minh có LinkageError.** Runtime có thể chọn một bản dựa trên classpath order hoặc delegation, hoặc hai loaders có thể định nghĩa các bản riêng hợp lệ. Phải xem Class identity và liên kết type tại runtime.

### 4.3 Xem manifest

Manifest nằm ở **META-INF/MANIFEST.MF**. Để đọc bằng JDK tools, giải nén riêng vào thư mục trống rồi mở file:

~~~bash
mkdir -p inspect-app
cd inspect-app
jar --extract --file ../app.jar META-INF/MANIFEST.MF
cat META-INF/MANIFEST.MF
cd ..
~~~

Trên Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force inspect-app | Out-Null
Set-Location inspect-app
jar --extract --file ../app.jar META-INF/MANIFEST.MF
Get-Content META-INF/MANIFEST.MF
Set-Location ..
~~~

Manifest trong fixture có **Main-Class: lab.app.Main** do **--main-class**, nhưng không có **Class-Path: libs/greeting-lib.jar**. Đừng tự suy rằng **--main-class** đóng gói dependency.

**Lưu ý an toàn:** Giải nén một JAR không tin cậy vào thư mục riêng có kiểm soát; tránh extract tất cả entries tùy tiện vào thư mục chứa project/sensitive files. Việc xem qua **jar --list** trước khi extract là bước kiểm tra thận trọng.

### 4.4 --verbose và --validate

~~~bash
jar --list --verbose --file app.jar
jar --validate --file app.jar
~~~

**--list --verbose** bổ sung kích thước, timestamp và metadata về entries; output có thể khác theo cách đóng gói. **--validate** kiểm tra tính hợp lệ archive theo các quy tắc công cụ, ví dụ các trường hợp multi-release hoặc module-related entries.

**Quan trọng:** **jar --validate** thành công **không chứng minh** application đã có toàn bộ dependencies, class-loader policy đúng, hoặc có thể chạy không lỗi. Trong fixture, app.jar hợp lệ về mặt archive nhưng **java -jar app.jar** vẫn lỗi thiếu Greeting.

### 4.5 --describe-module và automatic modules

~~~bash
jar --describe-module --file libs/greeting-lib.jar
~~~

Vì fixture không biên dịch **module-info.java**, công cụ nói đây **không có module descriptor** và suy ra automatic module name từ file JAR:

~~~text
No module descriptor found. Derived automatic module.

greeting.lib automatic
requires java.base mandated
contains lab.api
contains lab.impl
~~~

Đó là output đã quan sát với tên file **greeting-lib.jar** trên JDK 21. Một explicit modular JAR có **module-info.class** sẽ có descriptor thực tế, không chỉ tên automatic được suy ra.

**Đừng nhầm:**

- **Có JAR file** chưa có nghĩa đó là **explicit named module**.
- **Automatic-Module-Name** trong manifest có thể điều khiển tên automatic module, nhưng không tạo **module-info.class**.
- Khi đặt JAR trên classpath, classes thường thuộc **unnamed module**, không tự thành named module chỉ vì jar --describe-module suy ra tên automatic.
- Khi đặt JAR trên module path, module resolution và module graph quyết định module nào thực sự được dùng.

### 4.6 Những entries đặc biệt nên tìm

Khi chẩn đoán plugin/module/SPI:

| Entry | Ý nghĩa |
| --- | --- |
| **META-INF/MANIFEST.MF** | Main-Class, Class-Path, Implementation-Version, Multi-Release... |
| **module-info.class** ở root | Explicit module descriptor. |
| **META-INF/services/com.example.Service** | Provider-configuration file cho SPI classpath/automatic modules theo mô hình liên quan. |
| **META-INF/versions/17/...** | Class/resource version-specific trong multi-release JAR. |
| **package/name/Type.class** | Bytecode class ở package tương ứng. |
| **META-INF/*.SF / *.RSA / *.DSA** | Có thể liên quan JAR signing. |
| **application.properties, config/...** | Resources có thể cần cho runtime, jdeps không nhất thiết theo dõi. |

**Lưu ý Multi-Release:** Có entry ở **META-INF/versions/17** không tự bảo đảm JVM dùng nó; cần manifest **Multi-Release: true**, version runtime và quy tắc lookup phù hợp. Với một JAR chưa chắc chắn, hãy xem cả base entry và versioned entries.

## 5. Công cụ javap: nhìn thẳng class-file thay vì source

**javap** không chạy application và không tạo instances của class được phân tích. Nó đọc class files/JARs/modules và in signatures, bytecode, constant pool, flags hoặc debug metadata tùy option.

### 5.1 Lệnh nền tảng

~~~bash
javap -classpath libs/greeting-lib.jar lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -p lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -s lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -c lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -v lab.impl.GreetingImpl
~~~

Dùng **-classpath** (hoặc **-cp**) cho nơi chứa class files cần inspect. Đây là đường để **javap tìm class**, không chứng minh runtime application cũng chọn đường đó.

Bảng các options hữu ích:

| Option | Thông tin |
| --- | --- |
| **-p / -private** | Hiện cả private members, kể cả synthetic members tùy class. |
| **-c** | Disassemble bytecode instructions từng method. |
| **-s** | In JVM internal type descriptors. |
| **-l** | In line number table và local variable table nếu class file chứa. |
| **-v / -verbose** | Class-file version, constant pool, access flags, attributes, bootstrap methods... |
| **-sysinfo** | Path, size, timestamp, hash theo công cụ/JDK. |
| **--module moduleName** | Inspect class trong named module thích hợp. |
| **--module-path path** | Chỉ định module path cho named modules. |

### 5.2 Quan sát bytecode thực tế

~~~bash
javap -classpath libs/greeting-lib.jar -c -p -s lab.impl.GreetingImpl
~~~

Đoạn output liên quan method **hello** đã kiểm chứng trên OpenJDK 21 khi javac --release 17:

~~~text
public java.lang.String hello(java.lang.String);
  descriptor: (Ljava/lang/String;)Ljava/lang/String;
  Code:
     0: aload_1
     1: invokedynamic #7,  0
     6: areturn
~~~

Constant pool numbering như **#7** có thể đổi nếu source/compiler/options khác. Nhưng đối với **đúng fixture và toolchain** đã dùng, đây là cách method string concatenation được biên dịch qua **invokedynamic**.

**Giải mã:**

- **aload_1**: đưa local variable #1 (tham số name) lên operand stack.
- **invokedynamic**: gọi site động do JVM liên kết với bootstrap method thích hợp, ở đây phục vụ string concatenation.
- **areturn**: trả về reference, trong trường hợp này là String.

Không đọc output -c như Java source; nó là **JVM bytecode disassembly**. Java compiler có thể tối ưu hoặc chọn bytecode khác với cách lập trình viên hình dung từ source.

### 5.3 JVM descriptors là chìa khóa để chẩn đoán NoSuchMethodError

Descriptor:

~~~text
(Ljava/lang/String;)Ljava/lang/String;
~~~

có nghĩa method nhận một **java.lang.String** và trả một **java.lang.String**.

Một số ví dụ:

| Java signature | JVM descriptor |
| --- | --- |
| void run() | **()V** |
| int sum(int a, int b) | **(II)I** |
| String hello(String x) | **(Ljava/lang/String;)Ljava/lang/String;** |
| void main(String[] args) | **([Ljava/lang/String;)V** |
| long[] values() | **()[J** |
| boolean test(Object o) | **(Ljava/lang/Object;)Z** |

Khi gặp:

~~~text
java.lang.NoSuchMethodError:
  'java.lang.String lib.Type.lookup(java.lang.String)'
~~~

hãy inspect **chính bản lib.Type.class được deploy** với **javap -s -p**. Có thể source hiện tại có method, nhưng runtime JAR cũ không có descriptor đó. Return type, parameters và method name là phần quan trọng của liên kết bytecode; overload/erasure/bridge methods có thể khiến hình thức source và descriptor thực khác.

**Không chữa bằng cách đổi tên class tùy tiện.** Kiểm tra compile-time vs runtime artifact và ClassLoader nào đã chọn.

### 5.4 invokevirtual, invokestatic, invokeinterface

Với app.jar:

~~~bash
javap -classpath app.jar -c -p -s lab.app.Main
~~~

Các bytecode quan trọng trong fixture:

~~~text
0: new           #7     // class lab/impl/GreetingImpl
3: dup
4: invokespecial #9     // constructor
7: astore_1
8: getstatic     #10    // Field java/lang/System.out
11: aload_1
12: ldc          #16     // String Java
14: invokeinterface #18,  2
19: invokevirtual #24    // PrintStream.println
22: return
~~~

Chỉ số constant pool cụ thể phụ thuộc build, nên đoạn này là output đại diện từ fixture đã chạy. Ý nghĩa:

- **new** tham chiếu class implementation **lab.impl.GreetingImpl**.
- **invokespecial** gọi constructor.
- **invokeinterface** gọi interface method **lab.api.Greeting.hello**.
- **invokevirtual** gọi method instance của PrintStream.

Nếu dependency bị thiếu hoặc class identity không phù hợp, lỗi có thể lộ ra khi JVM phải **resolve** những symbolic references này. javap cho biết bytecode đang **tham chiếu tên gì**, chứ không quyết định nguồn loader trả Class nào.

### 5.5 Đọc constant pool, class-file major version và attributes

~~~bash
javap -classpath libs/greeting-lib.jar -verbose lab.impl.GreetingImpl
~~~

Các dòng đã quan sát:

~~~text
major version: 61
flags: (0x0031) ACC_PUBLIC, ACC_FINAL, ACC_SUPER
this_class: #11     // lab/impl/GreetingImpl
...
Constant pool:
...
#7 = InvokeDynamic ...
~~~

**Major version 61 là class-file target Java 17.** Một số phiên bản thường gặp:

| Java target | Major version |
| --- | ---: |
| Java 8 | 52 |
| Java 11 | 55 |
| Java 17 | 61 |
| Java 21 | 65 |

Nếu runtime Java 17 nhận một class file có major version 65, có thể ném **UnsupportedClassVersionError**; xác nhận bằng javap -v trên artifact được deploy.

### 5.6 -l chỉ giúp khi có debug information

~~~bash
javap -classpath libs/greeting-lib.jar -l lab.impl.GreetingImpl
~~~

Vì đã compile **-g**, class file có thể chứa **LineNumberTable** và **LocalVariableTable**. Nếu bản production được build với **-g:none** hoặc bị shrink/obfuscate, những bảng này có thể thiếu.

**Sự thiếu debug tables không làm class file mặc nhiên sai.** Nó chỉ giới hạn khả năng map bytecode ↔ source line/local variable name.

### 5.7 Compile-time artifacts không nói mọi điều về runtime

Một classfile có interface **lab.api.Greeting** trong constant pool, nhưng điều đó **không chứng minh** JVM đã dùng bản interface ở libs/greeting-lib.jar. Nếu classpath/module path có bản khác hoặc loader custom, có thể xảy ra type mismatch.

Dùng:

~~~java
System.out.println(lab.api.Greeting.class.getClassLoader());
System.out.println(lab.api.Greeting.class.getProtectionDomain()
        .getCodeSource());
~~~

Đây là snippet cần đặt trong method hợp lệ; **getCodeSource() có thể null**, nên production code phải null-check. Log runtime kết hợp javap mới giúp khẳng định nguồn bytecode đã được chọn.

## 6. jdeps: phân tích dependency graph từ bytecode

**jdeps** phân tích các **static class-file dependencies**, không chạy application. Nó đọc class files/JARs/directories và báo class/package/module dependencies theo options.

### 6.1 Chạy summary với đầy đủ library path

~~~bash
jdeps -summary -cp libs/greeting-lib.jar app.jar
~~~

**Output đã kiểm chứng trên OpenJDK 21:**

~~~text
app.jar -> libs/greeting-lib.jar
app.jar -> java.base
~~~

Điều này cho thấy bytecode trong app.jar tham chiếu lớp ở library JAR và JDK java.base.

**Cú pháp quan trọng:** Ở JDK 21, tùy chọn summary là **-summary** hoặc **-s**, **không phải --summary**. Sai thành --summary sẽ bị jdeps báo unknown option. Kiểm tra **jdeps --help** của JDK đang dùng để lấy chính tả options chính xác.

### 6.2 Bỏ library path để thấy dependency thiếu

~~~bash
jdeps -summary app.jar
~~~

Output trong fixture:

~~~text
app.jar -> java.base
app.jar -> not found
~~~

Nhìn sâu các class thiếu:

~~~bash
jdeps --missing-deps app.jar
~~~

Output đã kiểm chứng:

~~~text
app.jar -> not found
   lab.app.Main -> lab.api.Greeting         not found
   lab.app.Main -> lab.impl.GreetingImpl    not found
~~~

Định dạng khoảng trắng giữa các cột do tool render; tên classes và **not found** là thông tin cần thiết.

**Đọc đúng ý nghĩa:** jdeps không tìm thấy **các classes được bytecode tham chiếu trong đường phân tích hiện tại**. Nó không chứng minh file class không tồn tại ở bất kỳ nơi nào trên ổ đĩa. Có thể bạn chưa truyền **-cp**, dùng sai relative path, thiếu JAR transitive hoặc chưa cấu hình module path.

So sánh với runtime:

~~~text
java -jar app.jar
  -> NoClassDefFoundError: lab/api/Greeting

jdeps --missing-deps app.jar
  -> lab.api.Greeting not found
~~~

Hai quan sát độc lập cùng chỉ vào một vấn đề: application artifact **không đủ dependencies theo đường chạy/đường phân tích**.

### 6.3 Xem dependency ở mức class

~~~bash
jdeps -verbose:class -cp libs/greeting-lib.jar app.jar
~~~

Một phần output đã kiểm chứng:

~~~text
app.jar -> libs/greeting-lib.jar
app.jar -> java.base
   lab.app.Main -> java.io.PrintStream           java.base
   lab.app.Main -> java.lang.Object              java.base
   lab.app.Main -> java.lang.String              java.base
   lab.app.Main -> java.lang.System              java.base
   lab.app.Main -> lab.api.Greeting              greeting-lib.jar
   lab.app.Main -> lab.impl.GreetingImpl         greeting-lib.jar
~~~

Đây là cách xác định **class nào trong app.jar phụ thuộc vào class nào**. Nếu bạn có vài chục library JARs, -verbose:class giúp chỉ ra nguồn dependency trong bộ artifact đưa vào phân tích.

Một số tùy chọn liên quan:

| Option jdeps | Tác dụng |
| --- | --- |
| **-s / -summary** | Summary archive/module dependencies. |
| **-verbose:class** | Hiện dependencies ở mức class. |
| **-verbose:package** | Hiện dependencies ở mức package. |
| **-v / -verbose** | Nhiều class-level dependencies hơn theo hợp đồng, tương đương -verbose:class -filter:none. |
| **-cp / --class-path** | Chỉ định classpath để tìm classes referenced. |
| **--module-path** | Chỉ định path cho named modules. |
| **--missing-deps** | Tập trung các dependencies không tìm được. |
| **-apionly** | Chỉ phân tích dependencies hiện ra trong API public/protected thích hợp. |
| **-jdkinternals** | Tìm references tới JDK internal APIs. |
| **--multi-release 17** | Chọn view class files cho multi-release JAR theo target version. |
| **--list-deps** | Liệt kê module dependencies và các JDK internals có liên quan. |
| **--print-module-deps** | Module list dạng dấu phẩy, hữu ích làm input cho jlink. |
| **--dot-output dir** | Xuất Graphviz DOT files để vẽ graph. |

### 6.4 API-only không có nghĩa là tất cả runtime dependencies

~~~bash
jdeps -apionly -verbose:class -cp libs/greeting-lib.jar app.jar
~~~

Với fixture, Main chỉ có public **main(String[])** và constructor; nhiều phụ thuộc implementation nội bộ sẽ không xuất hiện trong API-only output. Nếu dùng kết quả này để tạo danh sách runtime dependencies đầy đủ, bạn có thể bỏ sót thư viện.

**-apionly** giúp hiểu dependencies lộ qua public/protected contracts, không thay thế phân tích toàn bộ bytecode.

### 6.5 --list-deps và --print-module-deps

~~~bash
jdeps --list-deps -cp libs/greeting-lib.jar app.jar
jdeps --print-module-deps -cp libs/greeting-lib.jar app.jar
~~~

Với fixture, các lệnh đã kiểm chứng trả về JDK module dependencies:

~~~text
java.base
~~~

**Đừng hiểu chỉ cần java.base để chạy ứng dụng.** Kết quả là **module names**, không phải danh sách toàn bộ third-party JAR classpath cần có. Demo vẫn cần greeting-lib.jar để chạy.

**--print-module-deps** có thể được dùng khi xây **jlink custom runtime image** cho một tập modules; ứng dụng classpath vẫn cần được đóng gói/triển khai cùng third-party libraries tương ứng.

## 7. jdeps có những điểm mù gì?

### 7.1 Reflection động

Ví dụ:

~~~java
Class<?> c = Class.forName(System.getProperty("plugin.class"));
~~~

Nếu tên class chỉ đến từ config lúc runtime, bytecode không có class symbolic reference cố định cho tên đó. jdeps **không thể suy ra chính xác mọi giá trị khả dĩ từ config/user input**. Vì vậy jdeps có thể không báo một plugin JAR mà runtime thật cần.

### 7.2 ServiceLoader và META-INF/services

~~~java
ServiceLoader<MyService> loader =
        ServiceLoader.load(MyService.class);
~~~

Đây là snippet giả định MyService và imports phù hợp. ServiceLoader có thể tìm providers qua **META-INF/services** hoặc **provides** trong named modules. jdeps không thay thế việc kiểm tra **provider-configuration file** và module descriptors, đặc biệt với plugins được đóng gói bên ngoài app.jar.

Một JAR provider không nằm trong static references từ consumer chưa chắc xuất hiện trong jdeps dependency list, nhưng vẫn cần khi chạy ServiceLoader.

### 7.3 ClassLoader custom và downloaded/generated classes

~~~java
byte[] bytes = downloadClassBytes();
Class<?> c = loader.defineOrLoad(...);
~~~

Đây là mã ý tưởng, không biên dịch độc lập. Class từ database, network, runtime bytecode generation hoặc encrypted JAR có thể không nằm trong input artifact lúc jdeps chạy.

**jdeps không execute custom ClassLoader**. Kết quả phụ thuộc files bạn đưa vào phân tích, không phải toàn bộ class graph sẽ phát sinh ở runtime.

### 7.4 JNI, native libraries và external config

Một class có **native method** hoặc load thư viện bằng **System.loadLibrary** có thể cần **.so / .dll / .dylib** hoặc environment variables. jdeps tập trung vào class dependencies, không chứng minh các native binaries tương thích hoặc đã có.

Tương tự, resource paths, config files, SQL/schema, network services và reflective scanning conventions không nhất thiết được jdeps liệt kê.

### 7.5 Dynamic proxies và invokedynamic

Static analysis có thể nhìn thấy những symbolic references trong class file, bootstrap methods và API classes, nhưng không thể đảm bảo mọi runtime generated proxy/hidden class/call-site target đã được liệt kê đầy đủ.

**Kết luận:** jdeps là một lớp chứng cứ mạnh cho **static references**, không phải mô phỏng chính xác toàn bộ runtime.

## 8. Điều tra Java modules và JPMS

### 8.1 Phân biệt classpath với module path

Trong Java 9+, cùng một JAR có thể có nhiều ngữ nghĩa khi được đặt ở vị trí khác nhau:

- **Classpath**: classes thuộc unnamed module của loader tương ứng.
- **Module path với explicit module-info.class**: named module với descriptor thật.
- **Module path với JAR không có module-info.class**: có thể thành **automatic module**.

**jar --describe-module** giúp xem artifact là modular/automatic; **jdeps --module-path** giúp phân tích module graph, còn **javap module-info.class** giúp xem bytecode descriptor.

### 8.2 Xem module descriptor

Với explicit modular JAR:

~~~bash
jar --describe-module --file some-module.jar
javap -p -v -classpath some-module.jar module-info
~~~

Lệnh thứ hai có thể phụ thuộc cách javap lookup class/module info; một lựa chọn đơn giản với JAR là **javap -v some-module.jar** không phải cú pháp ổn định cho descriptor. Ưu tiên **jar --describe-module** hoặc **javap --module-path path --module module.name module-info** theo môi trường cụ thể.

Đối với JAR fixture **greeting-lib.jar**, **không có module-info.class**, vì vậy không tự bịa một module descriptor với requires/exports do lập trình viên viết.

### 8.3 jdeps trên modules

Khi có hai explicit modules được biên dịch/đóng gói:

~~~bash
jdeps --module-path mods --check my.app
jdeps --module-path mods --module my.app
jdeps --module-path mods --print-module-deps --module my.app
~~~

Đây là **lệnh mẫu có placeholder tên module my.app và đường mods**, không áp dụng trực tiếp cho fixture classpath phía trên. Thay bằng tên module thật; nếu module path không có my.app, công cụ sẽ báo lỗi.

**--check** phân tích dependences và graph của named module, có thể giúp phát hiện requires chưa cần thiết, transitive relationships và graph sau reduction. **--module** chỉ định root module dùng để phân tích. Không dùng **--check** với một tên JAR được suy ra tùy tiện nếu nó chưa ở module path đúng.

### 8.4 jdeps --generate-module-info: gợi ý, không phải kết quả deploy cuối

Trong một số lộ trình migration từ classpath sang JPMS, có thể dùng:

~~~bash
jdeps --generate-module-info generated libs/greeting-lib.jar
~~~

Lệnh phân tích JAR để tạo **module-info.java** đề xuất trong thư mục output. Một số ràng buộc áp dụng: không ghép tùy tiện **--generate-module-info** với **--class-path** hay **--dot-output**; kiểm tra **jdeps --help** của JDK đang dùng.

**Không commit/gắn nhãn module-info do tool sinh ra mà không review.** Static analysis có thể bỏ sót reflective access, services, optional runtime deps, qualified exports hoặc opens cần thiết. Hãy review module name, requires/exports/opens/uses/provides và chạy integration tests.

### 8.5 Multi-release JAR: nhìn đúng bản class theo Java version

Nếu manifest có:

~~~text
Multi-Release: true
~~~

JAR có thể có:

~~~text
com/example/Feature.class
META-INF/versions/11/com/example/Feature.class
META-INF/versions/17/com/example/Feature.class
~~~

Trong Java 17, class được chọn có thể khác base; trong Java 21 có thể dùng bản version 17 hoặc cao nhất phù hợp nếu tồn tại.

Với jdeps:

~~~bash
jdeps --multi-release 17 -summary multi.jar
jdeps --multi-release base -summary multi.jar
~~~

**multi.jar là tên minh họa**, không phải artifact được tạo trong fixture. So sánh results giữa base và 17 khi có MR entries; dependencies khác nhau là dấu hiệu một runtime version có thể cần class/module khác.

Với javap, khi cần xem cụ thể **versioned class bytes**, hãy xác định đúng entry theo đường META-INF/versions/... hoặc dùng option **--multi-release** nếu được hỗ trợ bởi JDK/tool tương ứng. Luôn kiểm tra **javap --help** để không áp dụng nhầm option của jdeps.

## 9. Điều tra những lỗi class loading phổ biến

### 9.1 ClassNotFoundException: lớp không được tìm thấy theo tên

Tình huống:

~~~text
java.lang.ClassNotFoundException: lab.impl.GreetingImpl
~~~

Quy trình:

1. **jar --list** library JAR: có entry **lab/impl/GreetingImpl.class** không?
2. Kiểm tra classpath/runtime loader thực tế: JAR đó có được cung cấp không?
3. **javap -classpath ... lab.impl.GreetingImpl**: class file đọc được theo binary name không?
4. **jdeps --missing-deps app.jar**: có nhắc tới class cần thiết không?
5. Nếu custom loader, kiểm tra parent delegation, child-first package filter, TCCL và source locations.

Nếu JAR có class nhưng **runtime không dùng JAR đó**, không nên thêm ngẫu nhiên URL rồi kết luận đã sửa chính sách loader.

### 9.2 NoClassDefFoundError: JVM không định nghĩa được class cần thiết

Trong fixture:

~~~text
NoClassDefFoundError: lab/api/Greeting
~~~

**jdeps --missing-deps** và **jar --list** giúp tìm dependency thiếu. Nhưng NoClassDefFoundError còn có thể xuất hiện vì class đã **initialization failed** trước đó hoặc linkage issue khác. Hãy xem full cause chain, không mặc định nó luôn do thiếu file.

### 9.3 NoSuchMethodError

Tình huống build chống lại library version mới nhưng deploy version cũ:

~~~text
java.lang.NoSuchMethodError: ...
~~~

Dùng **javap -p -s** trên class được deploy và **javap -c -v** trên class gọi để kiểm tra name/descriptor kỳ vọng. Sau đó so phiên bản JAR và classpath order. jdeps có thể cho biết caller phụ thuộc library nào nhưng **không tự chứng minh method linkage tương thích**.

Một method generic có thể bị erasure thành descriptor khác với source. Bridge methods, static vs instance, access modifiers và return descriptors cũng cần kiểm tra. Đừng chỉ so tên method.

### 9.4 UnsupportedClassVersionError

Ví dụ compile thành class-file major 65 (Java 21), chạy trên Java 17 chỉ hỗ trợ đến major 61:

~~~bash
javap -verbose -classpath app.jar lab.app.Main
~~~

Đọc **major version** trên artifact thực sự deploy. Sửa bằng build **javac --release 17** nếu project hỗ trợ API Java 17, hoặc chạy JVM mới hơn phù hợp.

### 9.5 ClassCastException “X cannot be cast to X”

Nếu cùng binary name bị hai loaders định nghĩa:

~~~text
Class com.example.Dto (LoaderA)
Class com.example.Dto (LoaderB)
~~~

**javap** có thể cho hai artifacts bytecode, **jar --list** có thể xác nhận các JAR đều chứa com/example/Dto.class, **jdeps** có thể cho thấy shared API type xuất hiện trong signatures. Nhưng để khẳng định root cause, cần in runtime:

~~~java
System.out.println(a.getName().equals(b.getName()));
System.out.println(a == b);
System.out.println(a.getClassLoader());
System.out.println(b.getClassLoader());
~~~

Snippet giả định a, b là các **Class<?>** có sẵn. Nếu name giống nhưng a != b, đó là hai runtime types. Giải pháp thường là chia sẻ API/DTO ở một defining loader chung và cô lập implementation riêng.

### 9.6 LinkageError: loading constraint violation

Ở boundary giữa host/plugin, method descriptor chứa **api.Payload** có thể yêu cầu hai initiating loaders thống nhất Class cho tên đó. Nếu plugin tự define bản api.Payload khác với host, có thể phát sinh **LinkageError**.

**javap -s** cho biết descriptor nào đang chứa type nhạy cảm. **jar --list** cho biết shared DTO class có bị đóng gói trùng. **jdeps -verbose:class** cho biết caller references. Cuối cùng **runtime loaders/stack trace** xác nhận chính Class identities bị liên kết sai.

**Không có công cụ nào trong ba lệnh này tự sửa loader constraint.** Phải sửa kiến trúc shared API, delegation và class identity.

### 9.7 ServiceLoader không tìm thấy provider

Kiểm tra **META-INF/services/fully.qualified.Service** trên classpath JAR hoặc **module-info.class** cùng **provides ... with ...** của named module. **jar --list** cho thấy service config file có tồn tại. **javap** xác nhận provider class có method/constructor tương ứng; **jdeps** giúp phát hiện dependencies trực tiếp của provider.

Nếu provider được chọn bằng reflection/service configuration, đừng ngạc nhiên khi jdeps chỉ phân tích consumer không báo ra implementation JAR. Vòng đời module graph/TCCL cũng quan trọng.

### 9.8 JPMS lỗi module not found

Xác nhận module JAR có **module-info.class** hoặc automatic module name, đưa đúng **--module-path** và root modules. Dùng:

~~~bash
jar --describe-module --file suspicious.jar
jdeps --module-path mods --check my.app
~~~

Các lệnh này minh họa theo module artifacts thật. **Module path** khác classpath; chuyển file sang module path có thể thay tên module, readability/exports và service behavior.

## 10. Quy trình điều tra theo từng lớp bằng chứng

~~~text
[0] Ghi runtime JDK, full error/cause và launcher args
              |
              v
[1] jar --list: artifact có class/resource/config đúng path?
              |
              v
[2] jar --describe-module / manifest:
    module-info, Main-Class, Class-Path, Multi-Release?
              |
              v
[3] javap -p -s -c -v:
    bytecode, method descriptors, class version, references?
              |
              v
[4] jdeps -summary / --missing-deps / -verbose:class:
    dependency graph thiếu class/JAR/module nào?
              |
              v
[5] Runtime evidence:
    classpath/module path, ClassLoader, TCCL, Class.getModule,
    class-loading logs, jar/module resolver, plugin lifecycle
              |
              v
[6] Xác minh fix bằng deployment giống production
~~~

Mỗi lớp bằng chứng trả lời một câu hỏi khác nhau. Một lập trình viên nhìn thấy **lab/impl/GreetingImpl.class** qua jar --list vẫn chưa biết:

- class đó có **được chọn** trong runtime không;
- nó có **compatible method descriptor** không;
- ClassLoader nào đã định nghĩa nó;
- dependency transitive hoặc JNI resource có thiếu không;
- JPMS access rules có cho phép caller sử dụng nó không.

Chỉ khi ghép nhiều bằng chứng mới kết luận root cause vững chắc.

## 11. Thực hành mở rộng: chẩn đoán “JAR đúng nhưng chạy sai”

Một lỗi điển hình là **đã sửa và build library nhưng production vẫn chạy class cũ**. Quy trình:

1. Dùng **jar --list --file artifact.jar** kiểm tra JAR triển khai thực sự chứa expected path.
2. Dùng **javap -verbose -classpath artifact.jar package.Class** so major version, method descriptors, constant pool và timestamp/hash nếu cần.
3. Dùng **jdeps -verbose:class ... app.jar** xem static reference tới library artifact mong đợi.
4. Xác định startup **-cp**, **--module-path**, **-jar** và manifest Class-Path chính xác. Đừng nhầm JVM command của local/test với production.
5. Gắn class-loading logging trên JVM đang gặp lỗi nếu phù hợp:
   
   ~~~bash
   java -Xlog:class+load=info -cp "app.jar:libs/greeting-lib.jar" lab.app.Main
   ~~~

6. Trong code chẩn đoán, in Class.getClassLoader() và ProtectionDomain CodeSource khi được phép.
7. Xem custom ClassLoader có **parent-first**, **child-first** hay **cache class đã loaded**; không thể đổi Class hiện tại chỉ bằng thay file JAR.
8. Nếu đã có hai Class identities khác nhau, xem shared API boundary và các method descriptors chịu loading constraints.
9. Xác nhận sửa lỗi trên **chính môi trường runtime/loader configuration** gặp sự cố, không chỉ trên unit test classpath.

**Ghi chú:** Option **-Xlog:class+load** được HotSpot hỗ trợ theo Unified Logging; format chi tiết khác theo JVM/JDK. Nó là nguồn dữ liệu runtime riêng, không phải chức năng của javap/jar/jdeps.

## 12. Các giới hạn khi dùng ba công cụ

### 12.1 javap không chứng minh class đã được JVM load

javap đọc artifact chỉ định. Class file hợp lệ không đủ chứng minh class loader đã chọn nó. Nó cũng không cho biết class đã initialized, instances tồn tại hay Class object đang giữ reference nào.

### 12.2 jar không “giải dependency” chỉ bằng list

jar --list xem entries; một JAR có thể hoàn toàn hợp lệ nhưng vẫn thiếu dependencies runtime. Main-Class không phải Class-Path; Class-Path trong manifest có rules path resolution riêng.

### 12.3 jdeps không phải dynamic tracer

Không coi static graph đầy đủ cho mọi Class.forName, ServiceLoader, JNI, plugins động hoặc bytecode generation. Đặc biệt, **--ignore-missing-deps** chỉ đổi cách tool xử lý/bỏ qua dependencies thiếu; **không tạo những classes thiếu** hay bảo đảm chương trình chạy.

### 12.4 Phụ thuộc không đồng nghĩa compatibility

jdeps có thể thấy class A phụ thuộc class B nhưng không biết B runtime có **method descriptor** mong đợi trong phiên bản triển khai. javap và linkage tests bổ sung góc nhìn này.

### 12.5 Version của JDK tools cũng tác động kết quả

JDK tool options, class-file versions, JPMS module graph và cách disassembler trình bày có thể thay đổi. Nếu chạy javap rất cũ trên class-file của JDK mới, có thể không hiểu định dạng mới. Ưu tiên toolchain phù hợp với Java runtime/artifact đang chẩn đoán và luôn kiểm tra **--help**.

### 12.6 Không dùng logging/inspection như sandbox

Một JAR đến từ nguồn không tin cậy có thể có zip entries không an toàn, malware hoặc bytecode độc hại. **jar --list/javap/jdeps không thực thi application main**, nhưng giải nén và thử chạy một archive không tin cậy vẫn cần môi trường cô lập, tránh ghi đè file và tuân thủ quy trình bảo mật.

## 13. Câu lệnh cheat sheet

### Bytecode và signatures

~~~bash
javap -classpath libs/greeting-lib.jar lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -p -s lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -c lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -verbose lab.impl.GreetingImpl
javap -classpath libs/greeting-lib.jar -l lab.impl.GreetingImpl
~~~

### JAR và manifest

~~~bash
jar --list --file libs/greeting-lib.jar
jar --list --verbose --file app.jar
jar --describe-module --file app.jar
jar --validate --file app.jar
~~~

### Static dependencies

~~~bash
jdeps -summary app.jar
jdeps --missing-deps app.jar
jdeps -summary -cp libs/greeting-lib.jar app.jar
jdeps -verbose:class -cp libs/greeting-lib.jar app.jar
jdeps -apionly -verbose:class -cp libs/greeting-lib.jar app.jar
jdeps --list-deps -cp libs/greeting-lib.jar app.jar
jdeps --print-module-deps -cp libs/greeting-lib.jar app.jar
~~~

Các lệnh trên đã được chạy hoặc đối chiếu với tool help trên OpenJDK 21; kết quả phụ thuộc files và JDK cụ thể.

**Windows:** Dùng dấu **;** khi một classpath chứa nhiều entries, ví dụ **"app.jar;libs/greeting-lib.jar"**. Các lệnh có đúng một entry **-cp libs/greeting-lib.jar** không cần đổi dấu.

## 14. Kiến thức cần tránh nhầm

**“jar --list có class nên JVM chắc chắn load được.”** Sai: còn classpath/module path, loader policy, access và dependencies.

**“jar --validate PASS thì java -jar không thể lỗi.”** Sai: app.jar trong fixture hợp lệ nhưng thiếu greeting-lib.jar.

**“javap -c cho Java source chính xác.”** Sai: nó disassemble JVM instructions, không khôi phục source-level semantics đầy đủ.

**“javap thấy method source code có thì runtime Class chắc chắn có method.”** Sai: có thể javap đang đọc artifact khác runtime chọn.

**“jdeps --missing-deps không có output nghĩa là không có dependency động nào.”** Sai: reflection/services/native/generated classes có thể vượt phạm vi static analysis.

**“jdeps --print-module-deps in java.base nên có thể bỏ thư viện third-party.”** Sai: nó trả module names, không phải tất cả library JARs.

**“Mọi JAR trên module path đều là explicit named module.”** Sai: JAR không có module-info.class có thể là automatic module.

**“Hai JAR có một class cùng tên chắc chắn gây LinkageError.”** Sai: chỉ có class name duplication không đủ; xét defining loader và loading constraints.

**“Cùng getName() là cùng runtime Class.”** Sai: runtime identity còn defining ClassLoader.

**“javap/jdeps tự kiểm tra code coverage hoặc latency.”** Sai: đó là static inspection/analysis; dùng profiler/JFR/coverage agent nếu cần hành vi runtime.

## 15. Bài tập tự kiểm tra

**Câu 1.** Sau khi chạy jar --list app.jar, bạn thấy Main.class nhưng không thấy Greeting.class. Có đủ kết luận app.jar bị hỏng không?

**Đáp án:** Chưa. Nó có thể được thiết kế để dùng dependency JAR riêng. Phải xem runtime classpath/manifest và jdeps.

**Câu 2.** javap -verbose cho major version 61. Nó tương ứng Java release nào?

**Đáp án:** Java 17 class-file version.

**Câu 3.** Method Java **String hello(String)** có descriptor nào?

**Đáp án:** **(Ljava/lang/String;)Ljava/lang/String;**.

**Câu 4.** Tại sao javap -c thấy invokeinterface khi Main gọi Greeting.hello?

**Đáp án:** Static type của biến trong fixture là interface Greeting, method reference được compile thành invokeinterface.

**Câu 5.** Tại sao jdeps -summary app.jar không có library path có dòng “not found”?

**Đáp án:** Bytecode references tới lab.api.Greeting và lab.impl.GreetingImpl không được tool resolve từ input/classpath hiện có.

**Câu 6.** Thêm **-cp libs/greeting-lib.jar** vào jdeps có đồng nghĩa JVM java -jar app.jar sẽ tự có thư viện không?

**Đáp án:** Không. Đó là cấu hình phân tích của jdeps, không thay manifest hoặc runtime classpath của JVM.

**Câu 7.** Vì sao -apionly không nên được dùng như danh sách runtime dependency đầy đủ?

**Đáp án:** Nó tập trung vào public/protected API signatures, bỏ qua nhiều dependencies bên trong implementation.

**Câu 8.** ServiceLoader tìm provider qua META-INF/services. jdeps chỉ phân tích consumer có thể không hiện provider JAR vì sao?

**Đáp án:** Dependency discovery qua resource/service metadata có thể không được phản ánh như symbolic class reference trong consumer bytecode.

**Câu 9.** JAR không có module-info.class trên module path có thể mang dạng module nào?

**Đáp án:** Automatic module theo module system; tên có thể được suy ra hoặc dùng Automatic-Module-Name.

**Câu 10.** Hai ClassLoader khác nhau đều define com.example.Dto; điều gì cần xác minh để biết có vấn đề?

**Đáp án:** Defining loader, Class identity, boundary API signatures và constraints; hai class trùng tên tự nó có thể hợp lệ.

**Câu 11.** “java.lang.NoSuchMethodError” thường dùng công cụ nào để so method descriptors giữa hai versions?

**Đáp án:** **javap -s -p** trên các artifact chính xác; kết hợp javap -c -v ở caller.

**Câu 12.** Tại sao java -jar app.jar trong fixture không chạy dù app.jar có Main-Class?

**Đáp án:** Manifest/launcher không cung cấp greeting-lib.jar, thiếu lab.api.Greeting ở runtime.

## 16. Tóm tắt

~~~text
LỖI JAVA CLASS LOADING / LINKING
                |
                v
       jar: có đúng class/resource/JAR?
                |
                v
       javap: bytecode, version, descriptor đúng?
                |
                v
       jdeps: phụ thuộc tĩnh nào thiếu hoặc sai?
                |
                v
       runtime: loader, module, classpath, API identity?
                |
                v
       sửa artifact/deployment/loader policy
       rồi tái hiện lại dưới đúng JVM
~~~

**Nhớ ba câu:**

- **jar** xác minh **đúng những gì được đóng gói**.
- **javap** xác minh **đúng những gì đã được biên dịch**.
- **jdeps** xác minh **những gì bytecode tham chiếu tĩnh**.

Cả ba hỗ trợ chẩn đoán, nhưng **không thay thế** bằng chứng tại runtime về actual defining loader, parent delegation, module accessibility, runtime-generated classes và lifecycle.

### Nguồn tham khảo chính thức

- Oracle Java SE 21 **javap command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/javap.html
- Oracle Java SE 21 **jar command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jar.html
- Oracle Java SE 21 **jdeps command**: https://docs.oracle.com/en/java/javase/21/docs/specs/man/jdeps.html
- Oracle Java SE 21 **ClassLoader API**: https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/ClassLoader.html
- Oracle Java SE 21 **JAR File Specification**: https://docs.oracle.com/en/java/javase/21/docs/specs/jar/jar.html
- Oracle JVMS **§4 Class File Format**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html
- Oracle JVMS **§5 Loading, Linking, Initializing**: https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-5.html
