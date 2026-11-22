# Classpath, modulepath và ranh giới sử dụng trong dự án Java

Khi biên dịch hoặc chạy một ứng dụng Java, công cụ cần biết nơi tìm các lớp, thư viện và module mà chương trình sử dụng. Hai cơ chế tìm kiếm quan trọng là **classpath** và **modulepath**. Apache Ant cung cấp datatype `Path` để mô tả các vị trí này trong `build.xml`, sau đó truyền chúng cho task như `javac` hoặc `java`.

Classpath phục vụ cơ chế tìm lớp truyền thống của Java. Modulepath phục vụ hệ thống module JPMS được đưa vào từ Java 9, trong đó mỗi module có tên và có thể khai báo quan hệ phụ thuộc, gói được export hoặc mở cho reflection. Hai đường dẫn này liên quan đến nhau nhưng có ngữ nghĩa khác nhau. Đặt một thư viện vào nhầm đường dẫn có thể khiến build không tìm thấy lớp hoặc khiến module không đọc được dependency.

## 1. Classpath là gì?

Classpath là danh sách các vị trí mà trình biên dịch hoặc JVM tìm kiếm lớp và tài nguyên Java. Một phần tử classpath thường là:

- Thư mục chứa các tệp `.class` đã biên dịch.
- Tệp JAR chứa lớp và tài nguyên.
- Một số vị trí khác mà công cụ Java hỗ trợ như thư mục hoặc archive phù hợp.

Khi dùng dòng lệnh Java, classpath thường được truyền bằng `-cp` hoặc `--class-path`:

```sh
javac -cp "lib/*" -d build/classes src/main/java/com/example/Main.java
java -cp "build/classes:lib/*" com.example.Main
```

Ví dụ trên minh họa ý tưởng. Dấu phân cách các phần tử classpath phụ thuộc hệ điều hành: Windows dùng dấu chấm phẩy (`;`), còn Linux và macOS dùng dấu hai chấm (`:`). Khi viết `build.xml`, nên để Ant datatype `Path` xử lý việc phân cách thay vì tự ghép chuỗi theo một hệ điều hành.

Với ứng dụng classpath truyền thống, các lớp ứng dụng và thư viện được nạp vào unnamed module. Chúng không có ranh giới module tường minh như các module có `module-info.java`.

## 2. Modulepath là gì?

Modulepath là danh sách vị trí mà Java Module System dùng để tìm các module. Một module có thể được đóng gói thành JAR hoặc tồn tại dưới dạng thư mục module đã biên dịch. Module tường minh thường có tệp `module-info.class` trong đầu ra hoặc `module-info.java` trong mã nguồn.

Ví dụ một module khai báo:

```java
module com.example.inventory {
    requires java.sql;
    requires com.example.shared;

    exports com.example.inventory.api;
}
```

Khai báo này nói rằng module `com.example.inventory` cần đọc module `java.sql` và module `com.example.shared`; đồng thời công khai package `com.example.inventory.api` cho các module khác.

Khi biên dịch hoặc chạy module, Java sử dụng modulepath, thường được truyền bằng `--module-path` hoặc dạng viết tắt `-p`:

```sh
javac --module-path lib -d build/modules src/main/java/module-info.java
java --module-path build/modules:lib --module com.example.inventory
```

Đường dẫn trên dòng lệnh vẫn có quy tắc phân cách theo hệ điều hành. Với Ant, dùng datatype `Path` để không phải tự xử lý dấu phân cách.

Ngoài module tường minh có `module-info.class`, một JAR không có module descriptor khi đặt trên modulepath có thể được xử lý như **automatic module** theo quy tắc của Java. Tên automatic module được suy ra từ tên JAR hoặc metadata liên quan. Đây là cơ chế chuyển tiếp hữu ích cho thư viện cũ, nhưng không có nghĩa mọi thư viện trên classpath đều tự động trở thành module nếu chỉ thêm vào classpath.

## 3. So sánh classpath và modulepath

| Tiêu chí | Classpath | Modulepath |
|---|---|---|
| Mục đích | Tìm lớp và tài nguyên theo cơ chế class loading truyền thống | Tìm và phân giải module JPMS |
| Tham số Java | `-cp`, `--class-path` | `-p`, `--module-path` |
| Đầu vào phổ biến | Thư mục class, JAR | Module JAR, thư mục module, automatic module |
| Ranh giới truy cập | Chủ yếu dựa trên package, class visibility và class loader | Có thêm ranh giới module, `requires`, `exports`, `opens` |
| Khai báo phụ thuộc | Không có `requires` trong module descriptor | Module khai báo dependency trong `module-info.java` |
| Phù hợp với | Ứng dụng hoặc thư viện chưa chuyển sang JPMS | Ứng dụng/module sử dụng Java Platform Module System |

Không nên coi hai đường dẫn là hai cách viết khác nhau của cùng một cấu hình. Một thư viện trên classpath thuộc unnamed module; một thư viện được tìm thấy trên modulepath có thể trở thành named module hoặc automatic module. Việc chuyển vị trí thư viện có thể làm thay đổi khả năng truy cập và cách Java giải quyết phụ thuộc.

## 4. Mô hình thư mục và ranh giới dependency

Một dự án Ant có thể phân chia mã nguồn, thư viện và đầu ra theo cấu trúc như sau:

```text
inventory-app/
├── build.xml
├── src/
│   └── main/java/
│       ├── module-info.java
│       └── com/example/inventory/
│           └── Main.java
├── lib/
│   ├── classpath/
│   │   └── legacy-helper.jar
│   └── modules/
│       └── com.example.shared.jar
├── build/
│   ├── classes/
│   └── modules/
└── dist/
```

Đây chỉ là một cách tổ chức minh họa. Dự án có thể chọn tên thư mục khác, nhưng nên thể hiện rõ:

- Mã nguồn thuộc module nào.
- Thư viện nào là dependency trên classpath.
- Thư viện nào là dependency trên modulepath.
- Đầu ra biên dịch nằm ở đâu.
- Đầu ra dùng để chạy hoặc đóng gói nằm ở đâu.

Không nên gom mọi JAR vào một thư mục rồi đưa toàn bộ thư mục đó đồng thời vào cả classpath và modulepath. Cách đó làm mờ ranh giới module, có thể gây xung đột package hoặc khiến một dependency bị giải quyết theo cơ chế không mong muốn.

## 5. Khai báo classpath bằng Ant datatype `Path`

Ant có datatype `path` để mô tả một danh sách đường dẫn. Một path có thể gồm `pathelement`, `fileset` hoặc path khác được tham chiếu.

```xml
<path id="compile.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib/classpath" includes="**/*.jar"/>
</path>
```

Trong ví dụ:

- `id` đặt tên tham chiếu cho path.
- `pathelement` thêm một vị trí cụ thể.
- `fileset` tìm các JAR phù hợp trong thư mục thư viện.
- `includes="**/*.jar"` chọn JAR ở mọi cấp thư mục bên dưới thư mục gốc.

Khi một task cần classpath, có thể dùng thuộc tính tham chiếu hoặc phần tử lồng tương ứng. Ví dụ với `javac`:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       includeantruntime="false"
       encoding="UTF-8">
    <classpath refid="compile.classpath"/>
</javac>
```

`includeantruntime="false"` ngăn các thư viện runtime của Ant tự động được đưa vào classpath biên dịch của ứng dụng. Điều này giúp dependency của ứng dụng được khai báo tường minh và giảm phụ thuộc vô tình vào môi trường chạy build.

## 6. Khai báo modulepath bằng Ant datatype `Path`

Modulepath cũng được mô tả bằng một path, nhưng cần đặt ở vị trí riêng để giữ đúng ý nghĩa của dependency module:

```xml
<path id="compile.modulepath">
    <pathelement location="lib/modules/com.example.shared.jar"/>
</path>
```

Khi biên dịch một module, truyền path này vào task `javac` thông qua phần tử `modulepath`:

```xml
<javac srcdir="src/main/java"
       destdir="build/modules/com.example.inventory"
       release="21"
       includeantruntime="false"
       encoding="UTF-8">
    <modulepath refid="compile.modulepath"/>
</javac>
```

Ví dụ này giả định mã nguồn chứa `module-info.java` và module descriptor khai báo `requires com.example.shared;`. JAR `com.example.shared.jar` phải cung cấp module tương ứng trên modulepath.

Một modulepath có thể chứa nhiều phần tử:

```xml
<path id="runtime.modulepath">
    <pathelement location="build/modules/com.example.inventory"/>
    <pathelement location="lib/modules/com.example.shared.jar"/>
    <fileset dir="lib/modules" includes="*.jar"/>
</path>
```

Hãy bảo đảm collection chỉ chứa những module cần thiết và tránh đưa cùng một thư viện vào nhiều vị trí khác nhau. Khi có nhiều module, nên mô tả rõ module đầu ra và dependency để người đọc có thể xác định nguồn của từng module.

## 7. Phân biệt compile classpath và runtime classpath

Classpath khi biên dịch và classpath khi chạy không nhất thiết giống nhau. Compiler cần các thư viện chứa kiểu dữ liệu được tham chiếu trực tiếp trong mã nguồn. JVM khi chạy cần các lớp mà chương trình thực sự sử dụng tại runtime.

Ví dụ:

```xml
<path id="compile.classpath">
    <fileset dir="lib/compile" includes="*.jar"/>
</path>

<path id="runtime.classpath">
    <pathelement location="build/classes"/>
    <fileset dir="lib/runtime" includes="*.jar"/>
    <fileset dir="lib/compile" includes="*.jar"/>
</path>
```

Target biên dịch dùng compile classpath:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false">
        <classpath refid="compile.classpath"/>
    </javac>
</target>
```

Target chạy ứng dụng dùng runtime classpath:

```xml
<target name="run" depends="compile">
    <java classname="com.example.Main" fork="true" failonerror="true">
        <classpath refid="runtime.classpath"/>
    </java>
</target>
```

`fork="true"` chạy ứng dụng trong JVM con. `failonerror="true"` yêu cầu Ant đánh dấu target thất bại nếu chương trình trả về lỗi. Với ứng dụng classpath truyền thống, classpath runtime phải chứa lớp ứng dụng và các dependency cần thiết.

## 8. Compile và chạy ứng dụng theo module

Với ứng dụng JPMS, module descriptor xác định dependency bằng `requires`. Ví dụ:

```java
module com.example.inventory {
    requires java.sql;
    requires com.example.shared;

    exports com.example.inventory.api;
}
```

Mã nguồn có thể gọi các lớp trong module `com.example.shared` nếu module đó có mặt trên modulepath và các package cần dùng được export theo quy tắc JPMS.

Một cấu hình Ant minh họa:

```xml
<project name="inventory-modules" default="compile" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="module.output" location="build/modules/com.example.inventory"/>

    <path id="compile.modulepath">
        <pathelement location="lib/modules/com.example.shared.jar"/>
    </path>

    <target name="compile">
        <mkdir dir="${module.output}"/>
        <javac srcdir="${src.dir}"
               destdir="${module.output}"
               release="21"
               includeantruntime="false"
               encoding="UTF-8">
            <modulepath refid="compile.modulepath"/>
        </javac>
    </target>

</project>
```

Khi chạy module, JVM cần module ứng dụng và các module phụ thuộc trên modulepath. Với phiên bản Ant hỗ trợ thuộc tính `module` và nested `modulepath` của task `java`, có thể cấu hình:

```xml
<path id="runtime.modulepath">
    <pathelement location="build/modules/com.example.inventory"/>
    <pathelement location="lib/modules/com.example.shared.jar"/>
</path>

<target name="run" depends="compile">
    <java module="com.example.inventory/com.example.inventory.Main"
          fork="true"
          failonerror="true">
        <modulepath refid="runtime.modulepath"/>
    </java>
</target>
```

Cú pháp module launch và mức hỗ trợ của các thuộc tính modulepath phụ thuộc phiên bản Apache Ant. Hãy dùng phiên bản Ant có hỗ trợ Java module system tương ứng với JDK của dự án; nếu phiên bản Ant quá cũ, nâng cấp Ant trước khi dựa vào các thuộc tính này.

## 9. Ranh giới JPMS: `requires`, `exports` và `opens`

Modulepath chỉ giúp Java tìm module. Nó không tự cấp quyền truy cập mọi lớp trong module đó. Quyền đọc và quyền truy cập package được điều khiển bằng module descriptor.

| Khai báo | Ý nghĩa |
|---|---|
| `requires other.module;` | Module hiện tại cần đọc module khác |
| `requires transitive other.module;` | Dependency được truyền tiếp tới module đọc module hiện tại |
| `requires static other.module;` | Dependency cần khi biên dịch nhưng có thể không bắt buộc ở runtime |
| `exports com.example.api;` | Công khai package cho các module khác |
| `exports com.example.api to client.module;` | Chỉ export package cho module được chỉ định |
| `opens com.example.model;` | Cho phép truy cập sâu bằng reflection vào package theo quy tắc JPMS |
| `opens com.example.model to framework.module;` | Chỉ mở package cho module được chỉ định |

Một module có thể nằm đúng trên modulepath nhưng chương trình vẫn không biên dịch được nếu chưa khai báo `requires`, hoặc không thể truy cập lớp nếu package chưa được export. Reflection cũng có thể bị chặn nếu package chưa được mở phù hợp.

Không nên giải quyết mọi lỗi truy cập bằng cách chuyển dependency sang classpath hoặc thêm tùy chọn mở rộng toàn bộ module. Hãy xác định package nào cần được công khai và chọn `exports` hoặc `opens` theo đúng mục đích.

## 10. Automatic module và thư viện cũ

Khi một JAR không có `module-info.class` được đặt trên modulepath, Java có thể coi nó là automatic module. Điều này hỗ trợ ứng dụng module hóa từng bước trong khi vẫn sử dụng một số thư viện cũ.

Tuy nhiên, automatic module có một số khác biệt so với module tường minh:

- Tên module thường được suy ra từ tên JAR hoặc thuộc tính metadata.
- Module tự động đọc các module khác trong hệ thống module theo quy tắc của JPMS.
- Các package của automatic module được export theo cơ chế automatic module.
- Việc đổi tên JAR có thể ảnh hưởng tên module suy ra nếu không có metadata đặt tên ổn định.

Khi cần `requires` một automatic module, hãy xác định tên module thực tế bằng công cụ `jar --describe-module` hoặc metadata của thư viện, không đoán tên từ tên file một cách tùy tiện.

Ví dụ:

```sh
jar --describe-module --file lib/legacy-helper.jar
```

Kết quả cho biết module descriptor hoặc tên automatic module mà Java nhận diện. Sau đó mới sử dụng tên phù hợp trong `requires`.

## 11. Ranh giới thư viện và đầu ra trong dự án Ant

Một dự án dễ bảo trì nên xác định rõ từng nhóm dependency:

| Nhóm | Vị trí minh họa | Dùng ở đâu? |
|---|---|---|
| Thư viện compile truyền thống | `lib/classpath/` | Compile classpath và thường cả runtime classpath |
| Module dependency | `lib/modules/` | Compile modulepath và runtime modulepath |
| Lớp ứng dụng đã biên dịch | `build/classes/` | Runtime classpath của ứng dụng classpath |
| Module ứng dụng đã biên dịch | `build/modules/<module-name>/` | Runtime modulepath |
| JAR phát hành | `dist/` | Đầu ra đóng gói, không phải nơi mặc định để compiler tìm dependency |

Trong dự án nhiều module, mỗi module nên khai báo dependency trực tiếp mà nó thực sự cần. Không dựa vào việc một module tình cờ nhận được thư viện do một module khác thêm vào classpath. Điều đó khiến build khó tái lập và có thể che giấu dependency chưa được khai báo.

Nếu module A dùng module B, module A cần khai báo dependency tương ứng và build của A phải cung cấp B trên modulepath. Nếu ứng dụng classpath dùng thư viện C, C phải nằm trên compile classpath và runtime classpath theo nhu cầu thực tế.

## 12. Kiểm tra cấu hình đường dẫn

Khi compiler hoặc JVM không tìm thấy lớp/module, trước hết hãy kiểm tra path Ant đã tạo ra. Có thể dùng `pathconvert` để chuyển một Path thành property có thể in ra log:

```xml
<path id="compile.classpath">
    <fileset dir="lib/classpath" includes="*.jar"/>
</path>

<target name="show-classpath">
    <pathconvert property="compile.classpath.text" refid="compile.classpath"/>
    <echo message="Compile classpath: ${compile.classpath.text}"/>
</target>
```

Với modulepath, có thể làm tương tự:

```xml
<path id="compile.modulepath">
    <fileset dir="lib/modules" includes="*.jar"/>
</path>

<target name="show-modulepath">
    <pathconvert property="compile.modulepath.text" refid="compile.modulepath"/>
    <echo message="Compile modulepath: ${compile.modulepath.text}"/>
</target>
```

Sau đó chạy target cần xem:

```sh
ant show-classpath
ant show-modulepath
```

`ant -verbose compile` cũng giúp quan sát lệnh compiler và các tham số Ant truyền xuống. Nếu cần kiểm tra một JAR có phải module hay không, dùng `jar --describe-module` với đúng tệp JAR.

## 13. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `javac` báo không tìm thấy package hoặc class | Thiếu JAR hoặc thư mục lớp trên compile classpath/modulepath | Kiểm tra dependency trực tiếp và in Path bằng `pathconvert` |
| Chạy ứng dụng báo `ClassNotFoundException` | Runtime classpath thiếu lớp hoặc JAR cần thiết | Bổ sung dependency vào runtime classpath và kiểm tra lệnh chạy |
| JVM báo không tìm thấy module | Module JAR hoặc thư mục module chưa có trên modulepath | Kiểm tra `modulepath`, tên module và cấu trúc module đầu ra |
| Module đọc được dependency khi compile nhưng lỗi khi chạy | Runtime modulepath thiếu dependency hoặc module không được resolve | Đưa dependency cần thiết vào runtime modulepath và kiểm tra `requires` |
| Lớp nằm trong module nhưng không truy cập được | Package không được export hoặc module chưa khai báo `requires` | Kiểm tra module descriptor của cả module sử dụng và module cung cấp |
| Reflection bị từ chối | Package chưa được mở cho module framework cần truy cập | Dùng `opens` có phạm vi phù hợp nếu thực sự cần reflection |
| JAR cũ không được nhận diện trên modulepath | Tên automatic module không như dự kiến hoặc JAR có cấu trúc không phù hợp | Dùng `jar --describe-module` để xác định tên và trạng thái module |
| Build chạy được trên máy này nhưng lỗi trên máy khác | Dependency được lấy từ đường dẫn cục bộ hoặc classpath ngầm | Khai báo Path rõ ràng, quản lý thư viện trong dự án và loại bỏ phụ thuộc môi trường ngoài |
| Classpath có thư viện của Ant | `includeantruntime` được bật hoặc dùng mặc định không mong muốn | Đặt `includeantruntime="false"` và khai báo dependency ứng dụng rõ ràng |

## 14. Checklist tổ chức classpath và modulepath

- [ ] Đã xác định dự án đang dùng classpath truyền thống hay module JPMS.
- [ ] Dependency classpath và modulepath được phân loại riêng.
- [ ] Compile classpath/modulepath chứa các dependency cần cho biên dịch.
- [ ] Runtime classpath/modulepath chứa các dependency cần khi thực thi.
- [ ] Các Path được khai báo bằng `id` và tái sử dụng bằng `refid` khi phù hợp.
- [ ] Đường dẫn được xây dựng từ vị trí trong dự án thay vì hard-code theo máy cá nhân.
- [ ] Module descriptor khai báo `requires`, `exports` và `opens` đúng nhu cầu.
- [ ] Đã kiểm tra automatic module name của thư viện cũ trước khi viết `requires`.
- [ ] Đã kiểm tra Ant và JDK có hỗ trợ các thuộc tính modulepath đang sử dụng.
- [ ] Không đưa tệp nhị phân hoặc dependency không liên quan vào đường dẫn tìm kiếm.
- [ ] Đã kiểm tra đường dẫn thực tế bằng log hoặc `pathconvert`.

Classpath và modulepath xác định cách Java tìm dependency, còn Ant `Path` là cách buildfile mô tả các vị trí đó. Giữ ranh giới compile/runtime và classpath/modulepath rõ ràng giúp build dễ tái lập, tránh phụ thuộc ngầm và tận dụng được hệ thống module của Java khi dự án cần các ranh giới truy cập tường minh.
