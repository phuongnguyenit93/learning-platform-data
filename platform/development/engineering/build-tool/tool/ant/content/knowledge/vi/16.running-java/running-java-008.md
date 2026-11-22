# Chạy ứng dụng dùng Java module và phân biệt modulepath với classpath trong Apache Ant

Từ Java 9, Java Platform Module System (JPMS) cho phép ứng dụng chia thành các module có tên, khai báo dependency và kiểm soát package nào được cung cấp cho module khác. Khi build hoặc chạy ứng dụng theo mô hình này, Java phân biệt hai vùng tìm kiếm thư viện: **classpath** và **modulepath**.

Apache Ant hỗ trợ cả hai. Bạn có thể khai báo path riêng cho thư viện truyền thống và thư viện dạng module, dùng chúng khi biên dịch bằng task javac và khi chạy ứng dụng bằng task java. Chọn đúng loại đường dẫn giúp Java giải quyết dependency theo đúng mô hình của ứng dụng.

## 1. Java module là gì?

Trước Java 9, ứng dụng Java thường tổ chức mã nguồn theo package và đưa các thư viện vào classpath. Classpath tập hợp các thư mục lớp và file JAR mà JVM hoặc trình biên dịch cần tìm.

JPMS bổ sung một cấp tổ chức cao hơn: **module**. Một module có tên định danh, có thể khai báo:

- Module nào nó cần thông qua `requires`.
- Package nào được module khác sử dụng thông qua `exports`.
- Package nào mở cho truy cập phản chiếu thông qua `opens`.
- Những dịch vụ nào nó cung cấp hoặc sử dụng thông qua `provides` và `uses`.

Một module thường có file `module-info.java` ở gốc cây mã nguồn của module. Ví dụ:

~~~java
module com.example.greeter {
    requires java.logging;
    exports com.example.greeter.api;
}
~~~

Trong ví dụ, tên module là `com.example.greeter`, nó phụ thuộc vào module nền tảng `java.logging` và công bố package `com.example.greeter.api` cho module khác. Những package không được export vẫn nằm trong phạm vi nội bộ của module.

Sau khi biên dịch, file `module-info.java` trở thành `module-info.class` trong đầu ra. JVM dùng module descriptor này để xây dựng module graph và kiểm soát quan hệ giữa các module.

### 1.1. Cấu trúc một module đơn giản

~~~text
src/
└── com.example.app/
    ├── module-info.java
    └── com/
        └── example/
            └── app/
                └── Main.java
~~~

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires java.logging;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import java.util.logging.Logger;

public class Main {
    public static void main(String[] args) {
        Logger logger = Logger.getLogger(Main.class.getName());
        logger.info("Application started");
    }
}
~~~

Tên module là `com.example.app`, còn tên package của lớp Main cũng là `com.example.app`. Hai tên này có thể giống nhau, nhưng module name và package name là hai khái niệm riêng.

## 2. Phân biệt classpath và modulepath

Cả classpath và modulepath đều giúp Java tìm mã đã biên dịch và thư viện phụ thuộc. Điểm khác nhau nằm ở cách Java diễn giải những thư viện tìm thấy.

| Tiêu chí | Classpath | Modulepath |
|---|---|---|
| Mô hình | Mô hình class/package truyền thống | Mô hình module của JPMS |
| Đầu vào thường gặp | Thư mục lớp, JAR truyền thống | Modular JAR, module đã biên dịch dạng thư mục, automatic module |
| Định danh | Không yêu cầu tên module | Module có tên |
| Dependency | Class loader tìm lớp theo classpath | Module graph được giải quyết từ module descriptor và các module được yêu cầu |
| Quyền truy cập package | Dựa trên khả năng tìm thấy lớp và quy tắc truy cập Java | Ngoài quy tắc Java còn chịu kiểm soát bởi `exports`, `opens` và quan hệ module |
| Tùy chọn Java | `--class-path` hoặc `-cp` | `--module-path` hoặc `-p` |

### 2.1. Classpath và unnamed module

Khi đưa các lớp hoặc JAR lên classpath, Java xem chúng thuộc về **unnamed module** của class loader tương ứng. Các thư viện này không cần file `module-info.java` để được nạp theo cách truyền thống.

Ví dụ lệnh Java:

~~~bash
java -cp "build/classes:lib/core.jar:lib/logging.jar" com.example.app.Main
~~~

Trên Windows, dấu phân cách classpath thường là dấu chấm phẩy:

~~~powershell
java -cp "build\classes;lib\core.jar;lib\logging.jar" com.example.app.Main
~~~

Các classpath entry được phân tách theo quy tắc hệ điều hành. Với ứng dụng chưa chuyển sang JPMS, đây vẫn là cách chạy bình thường.

### 2.2. Modulepath và named module

Khi đưa một modular JAR hoặc thư mục module lên modulepath, Java đọc module descriptor để xác định tên module và các dependency.

Ví dụ lệnh Java:

~~~bash
java --module-path "build/modules:lib" --module com.example.app/com.example.app.Main
~~~

Dạng rút gọn:

~~~bash
java -p "build/modules:lib" -m com.example.app/com.example.app.Main
~~~

Ở đây:

- `--module-path` hoặc `-p` chỉ định nơi tìm module.
- `--module` hoặc `-m` chỉ định module cần khởi chạy.
- `com.example.app` là tên module.
- `com.example.app.Main` là lớp chứa phương thức main.

Với named module, Java giải quyết các module được khai báo bằng `requires`. Một package chỉ được module khác sử dụng theo cơ chế thông thường khi package đó được export và module tiêu thụ có quan hệ đọc phù hợp.

### 2.3. Một JAR có thể được đặt trên hai loại đường dẫn

Cần chú ý cách Java diễn giải JAR phụ thuộc vào nơi bạn đặt nó:

- Modular JAR có `module-info.class` khi nằm trên modulepath được xử lý như named module.
- JAR truyền thống không có module descriptor khi nằm trên modulepath thường được xử lý như **automatic module**.
- JAR có module descriptor nhưng nằm trên classpath được xử lý như JAR truyền thống trong unnamed module; module descriptor không được dùng để xây dựng module graph.

Automatic module giúp thư viện cũ có thể tham gia module graph trong nhiều trường hợp, nhưng tên module tự động có thể phụ thuộc tên file JAR nếu manifest không khai báo `Automatic-Module-Name`. Với ứng dụng dài hạn, nên dùng tên module ổn định hoặc một phiên bản thư viện đã cung cấp module descriptor.

### 2.4. Không thể thay modulepath bằng classpath một cách máy móc

Một named module không tự động đọc mọi lớp nằm trên classpath. Vì vậy, nếu `module-info.java` khai báo:

~~~java
module com.example.app {
    requires com.example.util;
}
~~~

thì Java cần tìm module `com.example.util` trên modulepath hoặc trong các nguồn module hợp lệ khác. Chỉ thêm `com.example.util.jar` vào classpath không đáp ứng yêu cầu `requires com.example.util`.

Nếu một thư viện cũ chưa phải modular JAR, có thể đặt JAR đó trên modulepath dưới dạng automatic module khi thư viện tương thích. Không nên giả định mọi thư viện classpath đều có thể được named module sử dụng trực tiếp.

## 3. Khai báo modulepath và classpath trong Apache Ant

Trong Ant, cả hai loại đường dẫn thường được mô tả bằng task path. Việc dùng path riêng giúp build file dễ đọc và tránh trộn các dependency thuộc hai mô hình.

### 3.1. Khai báo classpath

Ví dụ cho một ứng dụng truyền thống:

~~~xml
<path id="compile.classpath">
    <pathelement location="build/classes"/>
    <pathelement location="lib/core.jar"/>
    <pathelement location="lib/logging.jar"/>
</path>
~~~

Có thể tái sử dụng path này trong task javac:

~~~xml
<javac
    srcdir="src"
    destdir="build/classes"
    includeantruntime="false">
    <classpath refid="compile.classpath"/>
</javac>
~~~

Và khi chạy lớp chính bằng task java:

~~~xml
<java
    classname="com.example.legacy.Main"
    fork="true"
    failonerror="true">
    <classpath refid="runtime.classpath"/>
</java>
~~~

Trong build thực tế, `compile.classpath` và `runtime.classpath` có thể khác nhau. Ví dụ, thư viện chỉ dùng lúc biên dịch không nhất thiết phải được đóng gói trong runtime classpath.

### 3.2. Khai báo modulepath

Với ứng dụng JPMS, tạo path riêng:

~~~xml
<path id="compile.modulepath">
    <pathelement location="build/modules"/>
    <pathelement location="lib/modules"/>
</path>
~~~

Đường dẫn `build/modules` có thể chứa các module đã biên dịch dạng thư mục; `lib/modules` có thể chứa các modular JAR hoặc automatic module.

Dùng modulepath trong task javac:

~~~xml
<javac
    srcdir="src/com.example.app"
    destdir="build/modules/com.example.app"
    includeantruntime="false"
    release="17">
    <modulepath refid="compile.modulepath"/>
</javac>
~~~

Khi biên dịch một named module, `module-info.java` phải nằm trong cây mã nguồn mà javac xử lý. Module descriptor khai báo dependency, còn modulepath cung cấp các module mà trình biên dịch cần tìm.

### 3.3. Modulepath khi chạy ứng dụng

Task java của Ant có thể chạy một module bằng thuộc tính `module` và cung cấp modulepath bằng phần tử lồng `modulepath`:

~~~xml
<java
    module="com.example.app/com.example.app.Main"
    fork="true"
    failonerror="true">
    <modulepath refid="runtime.modulepath"/>
</java>
~~~

Cách viết này tương ứng với ý nghĩa của lệnh Java:

~~~bash
java --module-path <module-path> --module com.example.app/com.example.app.Main
~~~

`module` chỉ định module và lớp main cần chạy. `modulepath` chỉ định nơi JVM tìm các module. Với lệnh chạy named module, hãy dùng modulepath thay cho classpath của ứng dụng module.

`fork="true"` yêu cầu Ant chạy JVM con. Đây là cách phù hợp khi cần truyền tùy chọn launcher và chạy ứng dụng bằng cơ chế module của Java. `failonerror="true"` giúp Ant báo build thất bại nếu chương trình trả về mã thoát khác 0.

## 4. Ví dụ project có hai module

Để thấy rõ modulepath hoạt động như thế nào, hãy xây dựng một ứng dụng gồm:

- `com.example.util`: module cung cấp lớp tiện ích.
- `com.example.app`: module ứng dụng sử dụng tiện ích đó.

Cấu trúc project:

~~~text
inventory-app/
├── build.xml
├── src/
│   ├── com.example.util/
│   │   ├── module-info.java
│   │   └── com/example/util/Greeting.java
│   └── com.example.app/
│       ├── module-info.java
│       └── com/example/app/Main.java
└── build/
    └── modules/
~~~

### 4.1. Tạo module thư viện

File `src/com.example.util/module-info.java`:

~~~java
module com.example.util {
    exports com.example.util;
}
~~~

File `src/com.example.util/com/example/util/Greeting.java`:

~~~java
package com.example.util;

public class Greeting {
    public static String message() {
        return "Hello from a named module";
    }
}
~~~

Module này export package `com.example.util`, do đó module khác có thể sử dụng lớp Greeting được public trong package đó.

### 4.2. Tạo module ứng dụng

File `src/com.example.app/module-info.java`:

~~~java
module com.example.app {
    requires com.example.util;
}
~~~

File `src/com.example.app/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.util.Greeting;

public class Main {
    public static void main(String[] args) {
        System.out.println(Greeting.message());
    }
}
~~~

Khai báo `requires com.example.util` tạo quan hệ dependency giữa ứng dụng và module thư viện. Nếu thiếu khai báo này, module ứng dụng không thể sử dụng module thư viện theo quy tắc JPMS thông thường.

### 4.3. Build file Ant hoàn chỉnh

File `build.xml`:

~~~xml
<project name="inventory-app" default="run" basedir=".">

    <property name="src.dir" location="src"/>
    <property name="build.dir" location="build"/>
    <property name="modules.dir" location="${build.dir}/modules"/>

    <!-- Thư mục cha chứa các module đã biên dịch. -->
    <path id="compile.modulepath">
        <pathelement location="${modules.dir}"/>
    </path>

    <path id="runtime.modulepath">
        <pathelement location="${modules.dir}"/>
    </path>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

    <target name="prepare">
        <mkdir dir="${modules.dir}/com.example.util"/>
        <mkdir dir="${modules.dir}/com.example.app"/>
    </target>

    <target name="compile-util" depends="prepare">
        <javac
            srcdir="${src.dir}/com.example.util"
            destdir="${modules.dir}/com.example.util"
            release="17"
            encoding="UTF-8"
            includeantruntime="false"/>
    </target>

    <target name="compile-app" depends="compile-util">
        <javac
            srcdir="${src.dir}/com.example.app"
            destdir="${modules.dir}/com.example.app"
            release="17"
            encoding="UTF-8"
            includeantruntime="false">
            <modulepath refid="compile.modulepath"/>
        </javac>
    </target>

    <target name="run" depends="compile-app">
        <java
            module="com.example.app/com.example.app.Main"
            fork="true"
            failonerror="true">
            <modulepath refid="runtime.modulepath"/>
        </java>
    </target>

</project>
~~~

Trong ví dụ, hai module được biên dịch vào hai thư mục con của `build/modules`. Khi biên dịch `com.example.app`, modulepath trỏ đến thư mục cha `build/modules`, nơi chứa module `com.example.util` đã biên dịch.

Khi chạy, JVM cũng tìm module từ cùng thư mục cha. Ant khởi chạy module `com.example.app` và chỉ rõ lớp `com.example.app.Main` làm điểm vào.

### 4.4. Chạy build

Tại thư mục chứa `build.xml`, chạy:

~~~bash
ant
~~~

Vì target mặc định là `run`, Ant thực hiện chuỗi:

~~~text
prepare
   |
   v
compile-util
   |
   v
compile-app
   |
   v
run
~~~

Có thể gọi từng bước riêng:

~~~bash
ant clean
ant compile-util
ant compile-app
ant run
~~~

Nếu cần truyền đối số cho chương trình, dùng nested `arg` trong task java:

~~~xml
<java
    module="com.example.app/com.example.app.Main"
    fork="true"
    failonerror="true">
    <modulepath refid="runtime.modulepath"/>
    <arg value="staging"/>
    <arg value="verbose"/>
</java>
~~~

Trong mã Java, các giá trị này xuất hiện trong mảng `args` của phương thức main.

## 5. Đóng gói module thành modular JAR

Module đã biên dịch dạng thư mục có thể chạy trực tiếp từ modulepath. Khi phân phối ứng dụng, bạn thường đóng gói từng module thành JAR.

Nếu đầu ra đã có `module-info.class` ở gốc thư mục module, task jar có thể đóng gói nó:

~~~xml
<property name="dist.dir" location="dist/modules"/>

<target name="package-modules" depends="compile-app">
    <mkdir dir="${dist.dir}"/>

    <jar
        destfile="${dist.dir}/com.example.util.jar"
        basedir="${modules.dir}/com.example.util"/>

    <jar
        destfile="${dist.dir}/com.example.app.jar"
        basedir="${modules.dir}/com.example.app"/>
</target>
~~~

Các JAR tạo ra vẫn là modular JAR vì chúng chứa module descriptor `module-info.class`.

Tạo runtime modulepath cho JAR:

~~~xml
<path id="packaged.modulepath">
    <pathelement location="${dist.dir}/com.example.util.jar"/>
    <pathelement location="${dist.dir}/com.example.app.jar"/>
</path>
~~~

Chạy ứng dụng từ các JAR:

~~~xml
<target name="run-packaged" depends="package-modules">
    <java
        module="com.example.app/com.example.app.Main"
        fork="true"
        failonerror="true">
        <modulepath refid="packaged.modulepath"/>
    </java>
</target>
~~~

Khi chạy từ modular JAR, JVM đọc module descriptor trong từng JAR để giải quyết module graph. Thứ tự các phần tử trong modulepath không thay thế khai báo `requires`; dependency phải được mô tả trong module descriptor.

## 6. Chạy ứng dụng truyền thống bằng classpath trong Ant

Không phải ứng dụng nào cũng cần chuyển sang JPMS. Nếu project chưa có `module-info.java` và thư viện đang được quản lý theo classpath, hãy dùng thuộc tính `classname` của task java cùng nested `classpath`.

Ví dụ:

~~~xml
<path id="legacy.runtime.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib">
        <include name="*.jar"/>
    </fileset>
</path>

<target name="run-legacy">
    <java
        classname="com.example.legacy.Main"
        fork="true"
        failonerror="true">
        <classpath refid="legacy.runtime.classpath"/>
    </java>
</target>
~~~

Đây là cách chạy ứng dụng thông thường. Ant gọi lớp main theo tên đầy đủ của lớp và đưa các thư mục/JAR vào classpath.

Lệnh Java tương đương về ý nghĩa:

~~~bash
java -cp "build/classes:lib/*" com.example.legacy.Main
~~~

Trên Windows, thay dấu hai chấm bằng dấu chấm phẩy trong classpath.

### 6.1. So sánh cách khai báo task java

| Mục đích | Ứng dụng classpath | Ứng dụng module |
|---|---|---|
| Điểm vào | `classname="com.example.Main"` | `module="com.example.app/com.example.app.Main"` |
| Đường dẫn thư viện | `<classpath refid="..."/>` | `<modulepath refid="..."/>` |
| Cơ chế khởi chạy | Lớp trong unnamed module | Named module và module graph |
| Mã nguồn | Thường không có module-info.java | Có module-info.java cho named module |

Hai cách không nên trộn lẫn tùy tiện. Nếu ứng dụng được thiết kế như named module, hãy khai báo module dependency và chạy bằng modulepath. Nếu ứng dụng vẫn theo mô hình truyền thống, dùng classpath và classname là phù hợp.

## 7. Dùng thư viện cũ với Java module

Một tình huống thường gặp là ứng dụng đã có `module-info.java` nhưng vẫn cần một thư viện JAR cũ chưa có module descriptor.

### 7.1. Automatic module

Java có thể đưa JAR truyền thống lên modulepath dưới dạng automatic module. Tên module có thể được lấy từ thuộc tính `Automatic-Module-Name` trong manifest hoặc suy ra từ tên file JAR theo quy tắc của Java.

Ví dụ, một thư viện có manifest:

~~~text
Manifest-Version: 1.0
Automatic-Module-Name: com.example.legacy.logging
~~~

Module ứng dụng có thể khai báo:

~~~java
module com.example.app {
    requires com.example.legacy.logging;
}
~~~

Sau đó thêm JAR vào modulepath của Ant:

~~~xml
<path id="runtime.modulepath">
    <pathelement location="lib/legacy-logging.jar"/>
    <pathelement location="build/modules"/>
</path>
~~~

Cần kiểm tra tên module thực tế của thư viện trước khi viết `requires`. Nếu tên được suy ra từ tên file, đổi tên JAR có thể làm thay đổi tên module được suy luận.

### 7.2. Vì sao không chỉ thêm JAR vào classpath?

Named module không tự động đọc unnamed module. Do đó, thêm JAR cũ vào classpath chưa chắc làm cho các lớp của nó có thể được dùng từ mã nguồn thuộc named module.

Đưa JAR tương thích lên modulepath để Java xem nó như automatic module là một lựa chọn chuyển tiếp phổ biến. Tuy nhiên, automatic module có hành vi đóng gói và khả năng đọc rộng hơn named module thông thường. Với hệ thống lớn, nên kiểm tra kỹ khả năng tương thích và lên kế hoạch dùng thư viện modular rõ ràng.

### 7.3. Trường hợp cần tùy chọn module nâng cao

Java cung cấp một số tùy chọn launcher/compiler để xử lý tình huống đặc biệt, chẳng hạn:

- `--add-modules`: bổ sung module vào tập module gốc cần giải quyết.
- `--add-reads`: thêm quan hệ đọc giữa module.
- `--add-exports`: cho phép truy cập một package chưa được export theo cấu hình mặc định.
- `--add-opens`: mở package cho truy cập phản chiếu sâu.
- `--patch-module`: bổ sung hoặc thay thế nội dung trong một module.

Trong Ant, các tùy chọn launcher bổ sung có thể được truyền bằng nested `jvmarg` khi dùng task java với `fork="true"`:

~~~xml
<java
    module="com.example.app/com.example.app.Main"
    fork="true"
    failonerror="true">
    <modulepath refid="runtime.modulepath"/>
    <jvmarg value="--add-opens"/>
    <jvmarg value="com.example.app/com.example.app.internal=ALL-UNNAMED"/>
</java>
~~~

Chỉ dùng các tùy chọn này khi có yêu cầu tương thích cụ thể. Chúng làm thay đổi ranh giới truy cập của module và không nên được thêm chỉ để che một dependency khai báo sai.

## 8. Truyền tham số JVM và tham số ứng dụng

Khi chạy ứng dụng bằng task java, cần phân biệt tham số dành cho JVM với tham số dành cho phương thức main.

### 8.1. JVM argument bằng jvmarg

`jvmarg` truyền tùy chọn cho tiến trình JVM được fork:

~~~xml
<java
    module="com.example.app/com.example.app.Main"
    fork="true"
    failonerror="true">
    <modulepath refid="runtime.modulepath"/>
    <jvmarg value="-Xmx512m"/>
    <jvmarg value="-Dapp.environment=staging"/>
</java>
~~~

Trong đó:

- `-Xmx512m` giới hạn heap tối đa của JVM.
- `-Dapp.environment=staging` đặt system property trong JVM con.

Nếu cần bật thông tin giải quyết module khi chạy, có thể dùng tùy chọn launcher như `--show-module-resolution`:

~~~xml
<jvmarg value="--show-module-resolution"/>
~~~

### 8.2. Tham số ứng dụng bằng arg

`arg` truyền tham số vào `main(String[] args)`:

~~~xml
<java
    module="com.example.app/com.example.app.Main"
    fork="true"
    failonerror="true">
    <modulepath refid="runtime.modulepath"/>
    <arg value="staging"/>
    <arg value="--verbose"/>
</java>
~~~

Mã Java nhận:

~~~java
public static void main(String[] args) {
    for (String arg : args) {
        System.out.println(arg);
    }
}
~~~

Không dùng `arg` cho tùy chọn JVM. Tùy chọn như `-Xmx`, `-D...` hoặc `--add-opens` phải được truyền trước khi JVM khởi chạy, nên dùng `jvmarg`.

## 9. Phiên bản Ant và JDK

JPMS bắt đầu từ Java 9. Để biên dịch và chạy module, cần JDK có hỗ trợ module system và phiên bản Ant có hỗ trợ các thuộc tính modulepath/module của task tương ứng.

Một số lưu ý khi thiết lập môi trường:

- Dùng JDK 9 trở lên để biên dịch và chạy ứng dụng module.
- Dùng phiên bản Ant đủ mới để task javac và java hỗ trợ modulepath và module launching.
- Nếu dùng thuộc tính `release` của javac, hãy bảo đảm phiên bản Ant hỗ trợ thuộc tính này.
- Kiểm tra `JAVA_HOME` và phiên bản JDK mà Ant thực sự đang sử dụng.
- Tránh dùng JDK khác nhau giữa bước biên dịch và chạy nếu project phụ thuộc vào tính năng hoặc API riêng của một phiên bản.

Có thể kiểm tra phiên bản công cụ bằng:

~~~bash
ant -version
java -version
javac -version
~~~

Nếu Ant chạy bằng một JDK khác với JDK bạn nghĩ đã cài, hãy kiểm tra biến môi trường và cấu hình khởi chạy Ant. Việc có JDK mới trong PATH không bảo đảm tiến trình Ant đang dùng đúng JDK đó.

## 10. Những lỗi thường gặp khi chạy module bằng Ant

### 10.1. Module not found

Thông báo module không tìm thấy thường có nghĩa modulepath không trỏ đến nơi chứa module cần thiết, tên module không đúng hoặc module chưa được biên dịch/đóng gói.

Hãy kiểm tra:

- Module dependency đã được biên dịch chưa.
- Thư mục cha chứa các module đã nằm trên modulepath chưa.
- Tên trong `requires` có khớp tên module thực tế không.
- JAR có `module-info.class` hay được nhận diện như automatic module không.

### 10.2. Package is not visible

Lỗi package không hiển thị thường liên quan đến module descriptor. Hãy kiểm tra module chứa package đã export package đó chưa:

~~~java
module com.example.util {
    exports com.example.util.api;
}
~~~

Nếu module ứng dụng cần package `com.example.util.api`, package đó phải được export. Một lớp public trong package chưa export vẫn không tự động trở thành API công khai cho module khác.

### 10.3. Module does not read another module

Nếu module ứng dụng dùng một module khác, cần khai báo `requires`:

~~~java
module com.example.app {
    requires com.example.util;
}
~~~

Đồng thời, module được yêu cầu phải có mặt trên modulepath. Chỉ khai báo `requires` mà không cung cấp module tương ứng vẫn khiến quá trình biên dịch hoặc khởi chạy thất bại.

### 10.4. Main class không tìm thấy

Khi dùng thuộc tính module của Ant, hãy xác định đúng cả module name và tên lớp main:

~~~xml
<java
    module="com.example.app/com.example.app.Main"
    fork="true">
    <modulepath refid="runtime.modulepath"/>
</java>
~~~

Module name là tên trong module descriptor. Main class là tên đầy đủ gồm package và class. Hai tên này không nhất thiết giống nhau.

### 10.5. Đặt modular JAR trên classpath

Nếu một modular JAR được đưa lên classpath, Java xử lý nó như JAR truyền thống trong unnamed module. Module descriptor không được dùng để tạo module graph.

Nếu muốn dùng JPMS, hãy đặt JAR lên modulepath và khai báo dependency bằng `requires`.

### 10.6. Nhầm arg với jvmarg

Nếu truyền `--add-opens` hoặc `-Xmx` bằng `arg`, các giá trị đó sẽ đi vào `main(String[] args)` thay vì được JVM xử lý. Dùng `jvmarg` cho tùy chọn JVM và `arg` cho tham số ứng dụng.

### 10.7. Chỉ đặt modulepath lúc biên dịch

Ứng dụng có thể biên dịch thành công nhưng thất bại khi chạy nếu runtime modulepath thiếu dependency. Hãy cấu hình riêng modulepath cho compile và runtime, rồi bảo đảm cả hai chứa đầy đủ module cần thiết ở giai đoạn tương ứng.

## 11. Quy trình chọn classpath hay modulepath

Khi thiết kế build file, hãy xác định mô hình của ứng dụng trước:

1. Nếu ứng dụng không có module descriptor và vẫn dùng package/classpath truyền thống, khai báo classpath và chạy bằng `classname`.
2. Nếu ứng dụng có `module-info.java`, xác định module name và các dependency `requires`.
3. Đưa modular JAR, automatic module hoặc thư mục module đã biên dịch vào modulepath.
4. Khi biên dịch named module, dùng nested `modulepath` trong task javac để tìm các module phụ thuộc.
5. Khi chạy named module, dùng thuộc tính `module` và nested `modulepath` trong task java.
6. Giữ classpath và modulepath thành các path riêng, có tên rõ ràng theo mục đích compile hoặc runtime.
7. Kiểm tra `exports` nếu module khác cần truy cập package; kiểm tra `opens` nếu framework cần reflection.
8. Kiểm tra phiên bản JDK và Ant nếu task không nhận các thuộc tính liên quan đến module.

Một project có thể chứa cả mã nguồn module mới và thư viện cũ. Khi đó, cần quyết định thư viện cũ sẽ được dùng như automatic module trên modulepath hay tiếp tục nằm trên classpath với một cơ chế tương thích phù hợp. Đừng chuyển toàn bộ JAR sang một loại path chỉ vì tiện khai báo.

## 12. Ghi nhớ

- **Classpath** là đường dẫn cho mô hình Java truyền thống; các lớp ở đó thuộc unnamed module.
- **Modulepath** là nơi Java tìm named module và automatic module để xây dựng module graph.
- `module-info.java` khai báo tên module, dependency bằng `requires` và package công khai bằng `exports`.
- Trong Ant, dùng `<classpath>` với task javac/java cho ứng dụng truyền thống.
- Dùng `<modulepath>` với task javac/java khi biên dịch hoặc chạy ứng dụng theo JPMS.
- Với task java, `classname` chạy lớp theo classpath; `module` chạy module và có thể chỉ rõ lớp main bằng cú pháp module/class.
- Modular JAR trên classpath được xử lý như JAR truyền thống; JAR cũ trên modulepath có thể trở thành automatic module nếu tương thích.
- `arg` truyền tham số cho ứng dụng; `jvmarg` truyền tùy chọn cho JVM.
- Cần cấu hình dependency riêng cho compile và runtime, đồng thời kiểm tra JDK và phiên bản Ant hỗ trợ module.

Khi phân biệt được classpath và modulepath, đồng thời khai báo đúng module descriptor và dependency, bạn có thể dùng Apache Ant để biên dịch, đóng gói và chạy ứng dụng Java module một cách nhất quán.

