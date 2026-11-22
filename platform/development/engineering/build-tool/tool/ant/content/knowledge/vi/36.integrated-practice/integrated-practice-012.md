# Thực hành chẩn đoán buildfile lỗi và đánh giá chất lượng thiết kế build với Apache Ant

## 1. Mục tiêu bài thực hành

Một file `build.xml` có thể hợp lệ về cú pháp, chạy được một vài target và kết thúc bằng thông báo `BUILD SUCCESSFUL` nhưng vẫn có lỗi thiết kế: bỏ qua kiểm thử, dùng lớp Java còn sót từ lần build trước, đóng gói thiếu tài nguyên, hoặc chỉ hoạt động trên máy tác giả.

Trong bài thực hành thuộc chủ đề **Build Tool Ant**, bạn sẽ làm hai việc liên quan nhưng khác nhau:

1. **Chẩn đoán buildfile lỗi:** tái hiện lỗi bằng lệnh rõ ràng, tìm nguyên nhân ở XML, thuộc tính, target, classpath, đầu vào, đầu ra hoặc mã thoát, rồi sửa đúng chỗ.
2. **Đánh giá chất lượng thiết kế build:** kiểm tra liệu đồ thị target, chính sách lỗi, khả năng tái lập, tính di động và cách tổ chức cấu hình có giúp người khác vận hành build lâu dài hay không.

Một buildfile được đánh giá tốt phải trả lời được: **đầu vào lấy từ đâu, target nào tạo đầu ra nào, điều kiện nào làm build thất bại, và bằng chứng nào xác nhận sản phẩm cuối có thể sử dụng?**

### Kết quả mong đợi

Sau bài này, người học có thể:

- Phân biệt **lỗi cú pháp XML**, **lỗi cấu hình Ant**, **lỗi tác vụ**, **lỗi dependency/classpath** và **lỗi thiết kế khiến build xanh giả**.
- Dùng `ant -p`, `ant -verbose`, `ant -debug` và thông báo của từng task để khoanh vùng sự cố.
- Nhận ra các lỗi cụ thể như `srcdir` không đúng, chưa tạo `destdir`, thiếu `depends`, thiếu resource, bỏ qua exit code và đóng gói từ thư mục chứa dữ liệu cũ.
- Sửa buildfile theo một đồ thị `clean → compile → test → package → verify` phù hợp.
- Thiết lập tiêu chí đánh giá thiết kế build bằng **bằng chứng chạy thực tế**, thay vì chỉ dựa vào độ ngắn của XML hoặc số lượng target.

> **Phạm vi:** các ví dụ chạy trên Apache Ant 1.10.x, JDK 17 trở lên và hệ điều hành có terminal phù hợp. Bài dùng một lớp Java kiểm thử bằng `main` để tránh yêu cầu tải JUnit. Trong dự án thực, thay nó bằng JUnit/TestNG hoặc test runner đang sử dụng, nhưng vẫn giữ nguyên quy tắc: test fail phải khiến pipeline fail.

## 2. Mô hình chẩn đoán: từ triệu chứng tới nguyên nhân

Khi Ant thất bại hoặc cho kết quả đáng nghi, đừng sửa ngay dòng gần cuối log mà chưa xác định lỗi thuộc lớp nào.

```text
Lệnh chạy + working directory + môi trường
                    |
                    v
             Đọc build.xml
                    |
             XML parse thành công?
                /          \
             Không          Có
              |             |
     Sửa XML/encoding       v
                    Nạp property, task, classpath
                               |
                         Cấu hình hợp lệ?
                           /        \
                        Không        Có
                         |           |
                 Sửa thuộc tính      v
                 và dependency    Chạy target
                                      |
                                  Task fail?
                                 /        \
                               Có         Không
                               |           |
                         Lỗi thật cần      v
                         khoanh vùng    Có tạo đúng
                                      đầu ra/test?
                                        /    \
                                      Không  Có
                                       |      |
                                   Xanh giả   v
                                           Đối chiếu
                                           chất lượng
```

Một lệnh `ant package` không báo lỗi chỉ chứng minh những target **được cấu hình để chạy** đã hoàn tất. Nếu `package` không phụ thuộc `test`, việc kiểm thử không tự động xuất hiện trong kết quả.

### Các loại lỗi đáng phân biệt

| Nhóm lỗi | Dấu hiệu thường thấy | Nơi nên điều tra |
| --- | --- | --- |
| Cú pháp XML | `The element type ... must be terminated`, lỗi dòng/cột | Cặp thẻ, dấu nháy, ký tự `&`, mã hóa XML |
| Cấu hình Ant | `Target "..." does not exist`, task không được nhận dạng | `name` của target, `depends`, `taskdef`, phiên bản Ant |
| Đường dẫn/đầu vào | `srcdir ... does not exist` hoặc thiếu file | `basedir`, `location`, tên tệp, thư mục checkout |
| Compiler/classpath | `cannot find symbol`, `package ... does not exist` | Classpath, phiên bản JDK, nguồn generate, dependency |
| Thực thi chương trình | Exit code khác 0, exception, process không được tìm thấy | `<java>`/`<exec>`, `fork`, `failonerror`, working directory |
| Logic target | `BUILD SUCCESSFUL` dù test không chạy | Đồ thị `depends`, `if`/`unless`, target bỏ trống |
| Đóng gói | JAR thiếu class/resource hoặc có tệp cũ | `basedir`, `fileset`, `clean`, danh sách entry |
| Khả năng tái lập | Hai lượt sạch cho sản phẩm khác nhau | Timestamp, nguồn động, thứ tự input, toolchain |

Thông báo của Ant là **dữ kiện**, chưa phải kết luận. Một lỗi classpath trong `test` có thể bắt nguồn từ target `compile` không chạy; việc sửa câu lệnh Java test mà bỏ qua phụ thuộc target có thể chỉ che giấu vấn đề.

## 3. Tạo dự án Java nhỏ để thực hành

Dùng cấu trúc thư mục:

```text
ant-debug-lab/
├── build-broken.xml
├── build.xml                  # tạo sau khi phân tích lỗi
└── src/
    ├── main/
    │   ├── java/
    │   │   └── example/
    │   │       └── Greeter.java
    │   └── resources/
    │       └── app.properties
    └── test/
        └── java/
            └── example/
                └── GreeterTest.java
```

Sau này Ant sinh `build/` và `dist/`; các thư mục này không chứa dữ liệu người dùng cần bảo tồn.

### Mã nguồn chính

`src/main/java/example/Greeter.java`:

```java
package example;

public final class Greeter {
    private Greeter() {
    }

    public static String greet(String name) {
        return "Xin chào, " + name;
    }

    public static void main(String[] args) {
        String who = args.length == 0 ? "Ant" : args[0];
        System.out.println(greet(who));
    }
}
```

### Một phép kiểm thử không cần dependency bên ngoài

`src/test/java/example/GreeterTest.java`:

```java
package example;

public final class GreeterTest {
    private GreeterTest() {
    }

    public static void main(String[] args) {
        String actual = Greeter.greet("Linh");
        String expected = "Xin chào, Linh";
        if (!expected.equals(actual)) {
            throw new AssertionError(
                "expected=" + expected + "; actual=" + actual);
        }
        System.out.println("TEST PASSED: Greeter.greet");
    }
}
```

Nếu điều kiện kiểm tra sai, chương trình ném `AssertionError` chưa được bắt, JVM thoát với mã lỗi. Điều này giúp kiểm tra khả năng Ant **phát hiện và lan truyền lỗi** của một tiến trình Java mà không cần tải thêm framework.

### Tài nguyên phải được đóng gói

`src/main/resources/app.properties`:

```properties
app.name=ant-debug-lab
app.locale=vi
```

Khi hoàn thành bài, JAR cuối phải chứa cả `example/Greeter.class` lẫn `app.properties`, nhưng không chứa `example/GreeterTest.class`.

## 4. Buildfile cố ý có lỗi

Tạo `build-broken.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-debug-lab-broken"
         default="package"
         basedir=".">

    <!-- LỖI: thư mục source thực tế là src/main/java -->
    <property name="src.dir" value="source"/>
    <property name="out.dir" value="out"/>

    <target name="compile"
            description="Biên dịch ứng dụng (bản lỗi)">
        <!-- LỖI: không chuẩn bị out/classes -->
        <javac srcdir="${src.dir}"
               destdir="${out.dir}/classes"
               includeantruntime="false"/>
    </target>

    <target name="test"
            description="Kiểm thử (bản lỗi)">
        <!-- LỖI: không phụ thuộc compile/compile-test -->
        <java classname="example.GreeterTest"
              fork="true"
              failonerror="false">
            <classpath>
                <!-- LỖI: chưa biên dịch test và thiếu class main -->
                <pathelement location="${out.dir}/test-classes"/>
            </classpath>
        </java>
    </target>

    <target name="package"
            description="Đóng gói (bản lỗi)">
        <!-- LỖI: không phụ thuộc compile/test -->
        <mkdir dir="dist"/>
        <!-- LỖI: cho phép cập nhật archive cũ không kiểm soát -->
        <jar destfile="dist/demo.jar"
             basedir="${out.dir}/classes"
             update="true"/>
    </target>

</project>
```

File trên **hợp lệ về cú pháp XML** để tập trung vào lỗi vận hành và thiết kế. Nó có nhiều vấn đề độc lập; người học sẽ quan sát từng target trước khi chuyển sang bản sửa.

### Chạy từng tình huống

Trong thư mục dự án:

```bash
ant -f build-broken.xml -p
ant -f build-broken.xml compile
ant -f build-broken.xml test
ant -f build-broken.xml package
```

Không bắt buộc chạy liên tiếp nếu một lệnh thất bại; hãy thực hiện từng lệnh để ghi nhận triệu chứng. Tạo dự án trong một thư mục thử nghiệm riêng vì target `package` có thể tạo `dist/`.

| Lệnh | Kết quả có thể quan sát trên cây nguồn sạch | Lỗi cần tìm |
| --- | --- | --- |
| `ant -f build-broken.xml -p` | Thấy target có `description` | Parser đọc được XML; điều đó chưa chứng minh các target đúng |
| `... compile` | Báo `source` không tồn tại | `src.dir` sai; thiếu chuẩn bị nơi ghi class |
| `... test` | JVM không tìm thấy `GreeterTest`; Ant vẫn có thể kết thúc thành công | Test chưa được compile, thiếu classpath, `failonerror="false"` che lỗi |
| `... package` | Không thấy `out/classes` và lỗi archive, hoặc lấy class cũ nếu có | Không có `depends` và dùng `update="true"` |

Kết quả chính xác của stdout/stderr có thể khác theo phiên bản Ant/JDK và tình trạng thư mục. **Không chép cứng câu thông báo dự kiến làm điều kiện pass**; hãy xác nhận mã thoát, target thực sự chạy và file kết quả.

### Vì sao lỗi `test` nguy hiểm nhất?

`failonerror="false"` của `<java>` cho phép Ant tiếp tục khi tiến trình Java trả mã khác 0. Nó không biến phép thử thất bại thành thành công thực sự; nó chỉ khiến **trạng thái build** không phản ánh thất bại. Một CI chỉ nhìn exit code của Ant có thể báo xanh trong khi test không chạy.

Với trường hợp khác, `<exec>` gọi chương trình ngoài cũng cần quản lý exit code. Không nên xem một dòng `echo "Tests passed"` là bằng chứng đã thực thi test.

## 5. Công cụ điều tra của Ant: dùng đúng mục đích

### 5.1. Xác nhận lệnh khởi động và buildfile được nạp

```bash
ant -version
java -version
ant -f build-broken.xml -p
```

- `ant -version` xác định phiên bản Ant đang chạy.
- `java -version` cho biết JVM của terminal; nếu launcher hoặc cấu hình `JAVA_HOME` khác, cần xác minh JVM Ant thực sự dùng.
- `-f` chọn buildfile cụ thể để tránh vô tình chạy một `build.xml` khác.
- `-p`/`-projecthelp` hiển thị thông tin target được khai báo để hiển thị, đặc biệt các target có `description`. Không nhất thiết liệt kê mọi target nội bộ.

Khi lỗi chỉ xuất hiện trên CI, ghi lại **working directory**, đường dẫn checkout, `JAVA_HOME` và `ANT_HOME` (nếu được dùng), cùng command line đầy đủ. Một target đúng nhưng thực thi từ sai dự án vẫn cho cảm giác “cấu hình Ant bị lỗi”.

### 5.2. Tăng mức log một cách có mục đích

```bash
ant -f build-broken.xml -verbose compile
ant -f build-broken.xml -debug compile
```

- `-verbose` thường đủ để xem task và các file/tham số được xử lý.
- `-debug` in nhiều thông tin về property, target, classpath và cơ chế nội bộ; dùng khi log thường chưa giải thích được.
- Với output quá dài, tập trung vào **thông báo lỗi đầu tiên có nguyên nhân**, các task ngay trước đó và đầu vào của task. Một exception cuối log có thể là hậu quả dây chuyền.

Có thể gửi log sang file trong môi trường thử nghiệm:

```bash
ant -f build-broken.xml -verbose compile > ant-compile.log 2>&1
```

Ví dụ redirect trên áp dụng cho Bash và nhiều shell thông dụng; cú pháp/ý nghĩa luồng lỗi có thể khác trên PowerShell, đặc biệt khi gọi chương trình native. **Trước khi chia sẻ log**, cần loại bỏ token, mật khẩu, URL có credential, đường dẫn riêng tư hoặc dữ liệu nhạy cảm mà lệnh `-debug` có thể in ra.

### 5.3. Xác định một lỗi là fail thật hay xanh giả

Với Bash, chạy hai lệnh riêng để xem mã thoát:

```bash
ant -f build-broken.xml test
echo "Ant exit status: $?"
```

Với PowerShell:

```powershell
ant -f build-broken.xml test
Write-Output "Ant exit status: $LASTEXITCODE"
```

Nếu output Java báo `ClassNotFoundException` nhưng Ant trả mã `0` vì `failonerror="false"`, đó là một **lỗi thiết kế cơ chế báo thất bại**. Đổi `failonerror`, xác định test phải được compile và kết nối đúng dependency sẽ giải quyết nguyên nhân.

### 5.4. `ant -diagnostics` dùng khi nào?

```bash
ant -diagnostics
```

Lệnh này xuất thông tin chẩn đoán phiên bản và môi trường Ant/Java, hữu ích khi máy phát triển và CI có hành vi khác nhau hoặc task optional không được tìm thấy. Nó **không** tự chạy target và không xác định được logic test có bị bỏ qua. Chỉ chạy khi cần kiểm tra môi trường và lưu log cẩn thận vì thông tin môi trường có thể chứa dữ liệu nội bộ.

### 5.5. Kiểm tra một target riêng trước khi chạy toàn chuỗi

Khi nghi vấn buildfile, hãy gọi target nhỏ nhất có khả năng tái hiện vấn đề:

```bash
ant -f build-broken.xml compile
ant -f build-broken.xml test
ant -f build-broken.xml package
```

Sau khi hiểu từng phần, mới gọi target tổng. Điều này giúp không nhầm “package bị lỗi” với nguyên nhân “compile chưa hề chạy”.

## 6. Chẩn đoán lỗi XML trước khi tìm lỗi target

Buildfile có thể không được parse, khi đó **không target nào đã chạy**. Ví dụ đoạn XML sai:

```xml
<target name="compile">
    <mkdir dir="build/classes">
</target>
```

Thẻ `<mkdir>` chưa đóng; cần viết:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>
</target>
```

Tương tự, ký tự `&` trong thuộc tính hoặc nội dung XML phải được escape khi không thuộc entity hợp lệ:

```xml
<!-- Sai nếu viết trực tiếp & giữa hai từ -->
<echo message="compile & package"/>

<!-- Đúng -->
<echo message="compile &amp; package"/>
```

XML khác với shell: cặp dấu nháy bao quanh thuộc tính XML không tự tách đối số tại khoảng trắng. Với đường dẫn trong task tích hợp, không thêm dấu nháy thành ký tự thật của tên file.

**Quy trình:** sửa lỗi parser trước; chỉ sau khi `ant -p`/target được đọc mới phân tích logic `depends` và các tác vụ. Một log báo lỗi dòng/cột là nơi bắt đầu, không phải bằng chứng mọi vấn đề đều nằm tại đúng dòng đó.

## 7. Lập bản đồ nguyên nhân cho buildfile lỗi

Trước khi viết lại `build.xml`, hãy ghi lại mỗi lỗi theo cấu trúc:

| Triệu chứng | Chứng cứ | Nguyên nhân gốc | Thay đổi cần thực hiện |
| --- | --- | --- | --- |
| `compile` không thấy source | Đường dẫn in ra là `source` | Property không khớp cấu trúc `src/main/java` | Khai báo `src.main.dir` đúng và độc lập |
| Compiler không có nơi ghi | `destdir` chưa tồn tại | Target không tạo thư mục đầu ra | Tạo bằng `<mkdir>` trong target phụ thuộc |
| `test` không tìm thấy class | Không có `build/test-classes` | Test chưa được compile | Thêm target `compile-tests` phụ thuộc compile chính |
| `test` che lỗi tiến trình | Java exit khác 0 nhưng Ant thành công | `failonerror="false"` | Dùng `failonerror="true"` với `fork="true"` |
| `package` không chạy test | Log không có target `test` | Thiếu `depends="test"` | Tạo đường dependency rõ ràng |
| JAR thiếu resource | Không có `app.properties` trong archive | Không có bước copy resources | Copy vào class output trước package |
| Archive có thể giữ byte cũ | `update="true"` và không làm sạch | Đóng gói tăng dần không có kiểm chứng | Dùng output sạch/không update cho đường xác minh |
| Dùng tệp cũ sau build lỗi | Đầu ra không được tách và dọn | Không có contract cho clean build | Có `clean` giới hạn và CI gọi tường minh |

Đây là **bản đồ để giải quyết đúng nguyên nhân**, không phải lý do sửa bất kỳ đoạn XML nào chỉ vì nó nằm gần thông báo lỗi.

### Lưu ý với property bất biến

Ant thường coi property là **set once**: khai báo sau không ghi đè khai báo trước. Chẳng hạn:

```xml
<property name="build.dir" value="out"/>
<property name="build.dir" value="build"/>
<echo message="build.dir=${build.dir}"/>
```

Thông thường log vẫn dùng `out`. Vì thế đừng “sửa” một đường dẫn bằng cách thêm property cùng tên ở cuối file; hãy chỉnh nguồn khai báo có hiệu lực hoặc thiết kế override rõ ràng bằng `-D...`.

Nếu dùng `<property environment="env"/>`, biến môi trường chỉ trở thành property đầu vào của Ant; sự có mặt của nó không đảm bảo phù hợp mọi hệ điều hành hoặc CI. Hạn chế phụ thuộc vào đường dẫn tuyệt đối riêng của máy lập trình.

## 8. Thiết kế lại đồ thị target trước khi sửa câu lệnh

Đối với dự án này, chuỗi phù hợp là:

```text
clean                    (gọi rõ khi cần clean build)

prepare
   |
   v
compile-main
   |
   v
copy-resources
   |
   v
compile-tests
   |
   v
test
   |
   v
package
   |
   v
verify
```

- `prepare` tạo các thư mục thuộc build output.
- `compile-main` biên dịch chỉ nguồn chính.
- `copy-resources` đưa tài nguyên runtime vào cây classes.
- `compile-tests` biên dịch test sang output riêng và dùng classes chính trong classpath.
- `test` chạy tiến trình kiểm thử và lan truyền lỗi.
- `package` lấy **chỉ** cây classes chính.
- `verify` kiểm tra JAR được tạo và ghi nhận SHA-256.
- `clean` xóa đúng `build/` và `dist/` của dự án, không xóa `src/` hoặc dữ liệu không thuộc build.

Tại sao `clean` không nên là dependency tự động của mọi target? Trong quá trình phát triển, build tăng dần có thể hữu ích. Khi cần bằng chứng rằng không có output cũ, CI chạy rõ ràng `ant clean verify`. Cách này phân biệt **chính sách của lượt chạy** và **đồ thị sản xuất artifact**.

## 9. Bản `build.xml` tham khảo sau khi sửa

Tạo file `build.xml` mới:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="ant-debug-lab"
         default="verify"
         basedir=".">

    <!-- Đầu vào được quản lý trong repository -->
    <property name="src.main.dir" location="src/main/java"/>
    <property name="src.test.dir" location="src/test/java"/>
    <property name="res.main.dir" location="src/main/resources"/>

    <!-- Đầu ra chỉ do build tạo -->
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir"
              location="${build.dir}/test-classes"/>
    <property name="dist.dir" location="dist"/>
    <property name="jar.file" location="${dist.dir}/demo.jar"/>

    <target name="clean"
            description="Xóa các đầu ra được tạo bởi Ant">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="prepare">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
    </target>

    <target name="compile-main"
            depends="prepare"
            description="Biên dịch mã nguồn ứng dụng">
        <javac srcdir="${src.main.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17"
               debug="true"/>
    </target>

    <target name="copy-resources" depends="compile-main">
        <copy todir="${classes.dir}">
            <fileset dir="${res.main.dir}">
                <include name="**/*"/>
            </fileset>
        </copy>
    </target>

    <target name="compile-tests"
            depends="copy-resources"
            description="Biên dịch test sang thư mục riêng">
        <javac srcdir="${src.test.dir}"
               destdir="${test.classes.dir}"
               includeantruntime="false"
               encoding="UTF-8"
               release="17">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>
        </javac>
    </target>

    <target name="test"
            depends="compile-tests"
            description="Chạy phép kiểm thử bắt buộc">
        <java classname="example.GreeterTest"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <pathelement location="${test.classes.dir}"/>
            </classpath>
        </java>
    </target>

    <target name="package"
            depends="test"
            description="Tạo JAR chỉ sau khi test đạt">
        <mkdir dir="${dist.dir}"/>
        <jar destfile="${jar.file}"
             basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class"
                           value="example.Greeter"/>
            </manifest>
        </jar>
    </target>

    <target name="verify"
            depends="package"
            description="Xác nhận artifact và checksum">
        <available file="${jar.file}"
                   property="jar.exists"/>
        <fail unless="jar.exists"
              message="Không tìm thấy JAR đã đóng gói"/>

        <checksum file="${jar.file}"
                  algorithm="SHA-256"
                  property="jar.sha256"/>
        <echo message="Artifact: ${jar.file}"/>
        <echo message="SHA-256: ${jar.sha256}"/>
    </target>

</project>
```

Đây là bản tham khảo cho **cấu trúc dự án đã nêu**, không phải template có thể áp dụng nguyên xi cho mọi hệ thống. Trong dự án thực, cần điều chỉnh cách giải quyết dependency, test suite, Java version, loại archive, generated sources và yêu cầu phát hành.

### Những quyết định thiết kế đáng chú ý

**1. Đường dẫn được khai báo bằng `location`.** Điều này giúp Ant phân giải chúng theo `basedir` và giảm phụ thuộc vào thư mục làm việc bên ngoài project.

**2. Không compile nhầm test vào production.** `src/main/java` và `src/test/java` dùng hai thư mục output riêng biệt. Lệnh `<jar>` chỉ lấy `build/classes`.

**3. Có quan hệ phụ thuộc đầy đủ.** Chạy `ant package` tự đi qua compile, copy resource và test; thiếu test không thể bị bỏ qua do quên gọi target.

**4. Một kiểm thử lỗi làm Ant trả lỗi.** `<java fork="true" failonerror="true">` khiến lỗi exit code của JVM con được phản ánh trong trạng thái target.

**5. Không đóng gói tăng dần với `update="true"` ở đường xác minh.** Bản clean build được dùng để xác định tập tệp đúng. Nếu tối ưu build tăng dần về sau, phải có tiêu chí rằng file đã xóa khỏi nguồn không còn sót trong archive.

**6. Có tách điều kiện “tạo artifact” và “xác minh artifact”.** `verify` xác nhận file xuất hiện và ghi digest để liên hệ với lượt build, nhưng chưa phải phép kiểm tra hai lượt build tái lập.

**7. Chỉ `clean` xóa thư mục sinh.** Không dùng `<delete dir="${basedir}"/>` hoặc xóa thư mục nằm ngoài quyền sở hữu của target build.

## 10. Chạy lại và ghi bằng chứng thực hành

Đứng trong thư mục dự án, chạy:

```bash
ant -f build.xml -p
ant -f build.xml clean verify
jar tf dist/demo.jar
java -jar dist/demo.jar
```

Dự kiến theo mã nguồn mẫu:

- `test` in `TEST PASSED: Greeter.greet` rồi kết thúc thành công.
- `verify` thấy `dist/demo.jar` và in checksum SHA-256.
- `jar tf` hiển thị `example/Greeter.class`, `app.properties` và manifest, không chứa `example/GreeterTest.class`.
- `java -jar` in `Xin chào, Ant`.

Giá trị checksum có thể thay đổi theo thời gian nếu metadata entry trong JAR khác nhau. Khi cần đánh giá tính tái lập, chạy hai lượt clean build độc lập và đối chiếu digest, danh sách entry và metadata; không mặc định kết luận chỉ từ một lần build.

### Kiểm tra lỗi âm tính để chống xanh giả

Thử sửa test trong dự án thực hành:

```java
String expected = "Sai cố ý";
```

Sau đó chạy:

```bash
ant -f build.xml clean verify
```

Với cấu hình đúng, test sẽ thất bại và Ant phải kết thúc với lỗi; `package` và `verify` không được chạy sau khi test fail. **Hoàn nguyên test** sau khi quan sát.

Thử nghiệm này rất có giá trị vì một pipeline có thể pass hàng trăm lần nhưng vẫn che lỗi nếu không từng xác nhận quy tắc fail-fast. Làm trên môi trường thử nghiệm, không phá dữ liệu production.

### Kiểm tra từ checkout sạch

Một cách tránh kết quả “đậu nhờ dữ liệu cũ” là tạo lại cây nguồn ở thư mục độc lập và chạy:

```bash
ant -f build.xml clean verify
```

Nếu build chỉ thành công khi đã từng chạy một lệnh không được khai báo trong `depends`, có một dependency ẩn hoặc bước chuẩn bị chưa được mô tả. Đừng sửa bằng cách commit thư mục `build/` từ máy phát triển; hãy đưa điều kiện sinh file và target tương ứng vào build rõ ràng.

## 11. Những lỗi Ant khó phát hiện khi XML vẫn hợp lệ

### 11.1. `if` và `unless` trên target kiểm tra *sự tồn tại* của property

Ví dụ:

```xml
<property name="skip.tests" value="false"/>

<target name="test" unless="skip.tests">
    <echo message="Run tests"/>
</target>
```

Người mới có thể tưởng `skip.tests=false` sẽ cho target chạy. Nhưng `unless` của target dựa trên việc **property đã được định nghĩa hay chưa**, nên vì `skip.tests` tồn tại, target bị bỏ qua. Đây là một nguồn xanh giả phổ biến khi cờ boolean được lưu dưới dạng chuỗi.

Cách rõ hơn là tạo property điều kiện chỉ khi cần bỏ qua:

```xml
<condition property="tests.skipped">
    <equals arg1="${skip.tests}" arg2="true"/>
</condition>

<target name="test" unless="tests.skipped">
    <!-- Test runner thật, không chỉ echo -->
</target>
```

Nếu giá trị `skip.tests` chưa được khai báo, cần đặt mặc định hoặc xử lý rõ ngay trước `<condition>`. Trong đường phát hành, chính sách nên mặc định **không bỏ qua test**. Bản minh họa bằng `echo` không thay thế test runner thật.

### 11.2. Trộn `<antcall>` với `depends` làm luồng khó đọc

Ví dụ:

```xml
<target name="package">
    <antcall target="compile-main"/>
    <jar destfile="dist/demo.jar" basedir="build/classes"/>
</target>
```

`<antcall>` chạy target trong một Ant project con với cơ chế truyền property/reference riêng; nó không tương đương quan hệ `depends` đơn giản. Nếu không có yêu cầu đặc biệt, nên biểu diễn phụ thuộc:

```xml
<target name="package" depends="compile-main">
    <!-- Khâu đóng gói sau compile -->
</target>
```

Dùng `depends` khi target thực sự phụ thuộc vào đầu ra của target khác. Khi một target thực thi cùng công việc nhiều lần qua `antcall` hoặc đổi property theo các nhánh khó theo dõi, khả năng bảo trì giảm.

### 11.3. Dùng đường dẫn cố định của máy

```xml
<property name="lib.dir" value="C:\Users\Dev\Desktop\libs"/>
```

Cấu hình này có thể chạy trên một máy nhưng không có ý nghĩa ở runner Linux hoặc người mới clone repository. Ưu tiên đầu vào thuộc dự án hoặc property được truyền có hợp đồng rõ:

```xml
<property name="lib.dir" location="lib"/>
```

Khi thư viện lấy từ repository artifact, nên có bước resolve được kiểm soát và ghi dependency/version, thay vì phụ thuộc thư mục cá nhân.

### 11.4. Target `clean` xóa quá rộng

Cấu hình nguy hiểm:

```xml
<target name="clean">
    <delete dir="${basedir}"/>
</target>
```

`basedir` là thư mục project; xóa nó có thể xóa cả mã nguồn. Một target clean cần chỉ xóa những thư mục **được sinh tự động và thuộc quyền sở hữu của build**, chẳng hạn `build/` và `dist/`, và phải cẩn thận với property có thể bị override từ command line.

### 11.5. Classpath test bị đưa vào JAR phát hành

Nếu dùng `<jar basedir="build">` thay vì `build/classes`, archive có thể chứa cả `test-classes`, báo cáo kiểm thử và file trung gian. Hãy xem `jar tf` và đánh giá **tập entry**, không chỉ sự tồn tại của một class cần thiết.

### 11.6. Cấu hình mã hóa mơ hồ

Nếu mã nguồn lưu UTF-8 nhưng compiler dùng charset phụ thuộc môi trường, chuỗi tiếng Việt có thể lỗi trên máy khác. Khai báo:

```xml
<javac srcdir="src/main/java"
       destdir="build/classes"
       encoding="UTF-8"
       includeantruntime="false"
       release="17"/>
```

Trong target thật, phải tạo `build/classes` trước. Thuộc tính `encoding` này điều khiển **nội dung file Java**; nó không tự giải quyết mọi khác biệt tên tệp Unicode hoặc mã hóa archive.

### 11.7. Dùng phiên bản Java khác nhau

Một build có thể pass với JDK mới nhưng không chạy trên runtime cũ. Dùng `release` phù hợp để giới hạn API và bytecode, kiểm tra JDK thực sự được sử dụng, và không dựa chỉ vào `java -version` nếu Ant fork compiler khác.

### 11.8. Task download/exec thành công nhưng dữ liệu không đúng

Nếu Ant gọi `<get>` để lấy dependency hoặc `<exec>` để tạo code, việc tiến trình báo thành công chưa đảm bảo file có đúng checksum hay format. Với artifact ngoài, cần pin phiên bản, nguồn và kiểm tra nội dung. Với `<exec>`, hãy cấu hình lỗi thoát đúng và xác minh file đầu ra.

## 12. Đánh giá chất lượng thiết kế build bằng tiêu chí có thể kiểm chứng

Để đánh giá một `build.xml`, nên xem **thiết kế** và **kết quả vận hành**. Tài liệu đẹp hoặc target đặt tên rõ không bù được việc bỏ qua test. Ngược lại, build pass hôm nay chưa chứng minh thiết kế có thể duy trì khi tăng số module hoặc thay CI.

Một bảng đánh giá thực hành gồm 10 tiêu chí, mỗi tiêu chí chấm từ **0 tới 2**:

- **0 điểm:** thiếu cơ chế hoặc có lỗi thiết kế rõ ràng.
- **1 điểm:** có cơ chế nhưng chưa đầy đủ hoặc chưa có bằng chứng hoạt động.
- **2 điểm:** thiết kế nhất quán và có bằng chứng phù hợp từ lệnh/log/sản phẩm.

| Tiêu chí (tối đa 2đ) | Dấu hiệu đạt mức tốt | Bằng chứng nên thu thập |
| --- | --- | --- |
| 1. Đồ thị target | Target mô tả đúng thứ tự và dependency, không chạy thừa/thiếu | `ant -p`, log target, sơ đồ `depends` |
| 2. Phát hiện lỗi | Compiler/test/package fail làm build fail; không có xanh giả | Chủ động gây lỗi và xem exit code |
| 3. Đầu vào rõ ràng | Source, dependency, cấu hình/version có nguồn xác định | Danh sách input, commit và toolchain |
| 4. Clean build | Không phụ thuộc output cũ, clean chỉ xóa đầu ra | Build từ checkout sạch, phạm vi `clean` |
| 5. Tách output | Class production/test, resource, report, artifact có thư mục riêng | Cây `build/` và `dist/` |
| 6. Đóng gói đúng | Đúng main class, resource, dependency runtime và định dạng phát hành | `jar tf`, manifest, smoke test |
| 7. Đa nền tảng | Không hard-code đường dẫn riêng; encoding rõ ràng | Chạy trên CI và môi trường đích |
| 8. An toàn build | Không lộ secret, không xóa quá rộng, input ngoài được kiểm soát | Review task `delete/exec/get` và quyền runner |
| 9. Quan sát và truy lỗi | Log có target, lỗi và artifact tương ứng; CI lưu bằng chứng hữu ích | Log, report, mã thoát, checksum |
| 10. Khả năng bảo trì | Property tập trung, target trách nhiệm rõ, ít logic trùng và dễ mở rộng | Cấu trúc `build.xml` và cách thêm test/module |

**Tổng tối đa: 20 điểm.** Đây là **thước đo thảo luận trong bài học**, không phải tiêu chuẩn chính thức của Apache Ant và không thay thế kiểm tra kỹ thuật. Có thể dùng mức tham khảo:

- **18–20:** thiết kế phù hợp để xem xét dùng làm pipeline chính, với điều kiện các yêu cầu nghiệp vụ riêng đã đạt.
- **14–17:** đã có cấu trúc tốt nhưng cần xử lý những điểm yếu được chỉ ra.
- **0–13:** còn rủi ro đáng kể; ưu tiên sửa tính đúng, fail-fast và đầu vào trước khi tối ưu hiệu năng.

**Điểm cao không cho phép bỏ qua lỗi nghiêm trọng.** Nếu build xóa mất nguồn, làm lộ secret hoặc không báo test fail, nó chưa phù hợp cho phát hành dù tổng điểm về các tiêu chí khác cao.

### Ví dụ áp dụng bảng đánh giá

Với `build-broken.xml`, có thể quan sát ngay một số mức 0:

- Đồ thị target: `package` không phụ thuộc `compile` hay `test`.
- Phát hiện lỗi: `failonerror="false"` che exit code của test.
- Clean build: không có target clean, archive được cập nhật từ dữ liệu có thể cũ.
- Đóng gói: không copy `app.properties` và không thiết lập main manifest.

Với `build.xml` tham khảo, những điểm này có cơ chế rõ hơn, nhưng chỉ nên đánh dấu **2 điểm** cho tiêu chí tương ứng sau khi người học chạy các phép thử và thu bằng chứng. Không suy luận “đúng tuyệt đối” chỉ bằng cách đọc XML.

## 13. Mẫu biên bản điều tra dành cho người review build

Với mỗi lỗi, ghi một mục có thể tái hiện:

```text
Buildfile: build-broken.xml
Commit: <git-commit>
Ant/JDK: <versions>
Command: ant -f build-broken.xml test
Environment: <OS, working directory, relevant vars>

Observed:
  Java process: failed to find example.GreeterTest
  Ant process: ended successfully because failonerror=false

Expected:
  Required test must execute and fail the Ant build if failing

Root cause:
  Missing compile-tests dependency and incorrect test classpath;
  failonerror=false suppresses nonzero child process status

Change:
  compile-tests depends on main compilation;
  test depends on compile-tests;
  java uses both class dirs and failonerror=true

Verification:
  1) Test passes on valid source
  2) Deliberately incorrect assertion fails Ant
  3) package is not executed after test failure
```

Thay placeholder bằng dữ kiện của lần chạy thật. Không lưu token hoặc mật khẩu trong biên bản. Một báo cáo tốt nói được **cách tái hiện**, **điều quan sát được**, **nguyên nhân**, **thay đổi** và **bằng chứng sau thay đổi**.

### Phân biệt khắc phục triệu chứng và sửa nguyên nhân

Nếu `test` không thấy `GreeterTest`, copy một file `.class` thủ công vào thư mục test có thể khiến lượt chạy sau pass. Nhưng giải pháp đó tạo dependency ẩn. Sửa đúng là đưa `compile-tests` vào DAG và khai báo classpath thích hợp.

Nếu `package` thiếu resource, copy resource sau khi đóng gói cũng chỉ tạo ra một artifact phụ ngoài pipeline. Sửa đúng là có target `copy-resources` trước `package` và kiểm tra resource trong archive.

Nếu build cần gọi lệnh chuẩn bị bí mật trên máy cá nhân, chuẩn hóa thành bước CI có quyền hạn rõ ràng, không chép secret vào file build để “cho tiện”.

## 14. Kiểm tra tính tái lập và sự đầy đủ của artifact

Hai lần chạy có thể cho `BUILD SUCCESSFUL` nhưng khác sản phẩm. Cần xác định mục tiêu so sánh:

- **Đúng tập file:** hai archive hoặc hai thư mục `dist/` có cùng danh sách file cần thiết không?
- **Đúng nội dung:** SHA-256 của những artifact được so sánh có giống nhau không?
- **Đúng runtime contract:** chương trình có chạy được theo lệnh triển khai không?
- **Đúng tính độc lập:** build từ checkout sạch có cần cache/đầu ra của máy trước đó không?

Ví dụ trên Bash:

```bash
ant -f build.xml clean verify
mkdir -p ../ant-evidence/run-1
cp dist/demo.jar ../ant-evidence/run-1/demo.jar

ant -f build.xml clean verify
mkdir -p ../ant-evidence/run-2
cp dist/demo.jar ../ant-evidence/run-2/demo.jar

sha256sum ../ant-evidence/run-1/demo.jar
sha256sum ../ant-evidence/run-2/demo.jar
```

Các lệnh chỉ nên chạy trong workspace thực hành, và thư mục snapshot nằm ngoài `build/`, `dist/`. Nếu hai digest khác, so sánh entry sau giải nén rồi kiểm tra timestamp, thứ tự entry, cách nén và thuộc tính manifest. Nếu digest bằng, điều đó chứng minh mạnh về byte của **hai JAR đó**, chưa chứng minh mọi đầu vào và môi trường build đều bất biến.

Với mục tiêu sửa buildfile lỗi, thứ tự ưu tiên là **tính đúng của target và artifact trước**, sau đó mới đo tính tái lập đầy đủ và tối ưu thời gian build.

## 15. Đưa kiểm tra vào CI sau khi sửa

Một job CI tối thiểu cho dự án mẫu có thể gồm:

```yaml
name: Ant build checks

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-24.04

    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '17'

      - name: Prepare Ant
        run: |
          sudo apt-get update
          sudo apt-get install -y ant
          ant -version
          java -version

      - name: Clean compile, test, package and verify
        run: ant -noinput -f build.xml clean verify

      - name: Inspect artifact and smoke test
        run: |
          jar tf dist/demo.jar
          java -jar dist/demo.jar

      - name: Upload verified candidate
        uses: actions/upload-artifact@v4
        with:
          name: ant-debug-lab
          path: dist/demo.jar
          if-no-files-found: error
```

Đây là một **minh họa CI**, không phải cấu hình đã được kiểm thử cho mọi repository. Bản Ant do gói `apt-get` cung cấp có thể thay đổi theo kho của hệ điều hành; dự án cần yêu cầu tái lập nghiêm ngặt nên khóa toolchain theo cách được quản lý. Quyền phát hành production và secret triển khai không nên được cấp cho workflow chạy mã/`build.xml` chưa được review từ nguồn không đáng tin.

Điểm cần giữ là **nếu compile, test hoặc verify lỗi, bước upload artifact không được chạy như thể thành công**. Có thể thêm report test, scan dependency và kiểm tra nội dung ZIP/JAR khi dự án phát triển lớn hơn.

## 16. Bài tập chẩn đoán mở rộng

Các bài dưới đây có thể làm độc lập sau khi hoàn tất ví dụ chính. Mỗi lần chỉ thay đổi một yếu tố để biết nguyên nhân gây ra kết quả.

### Bài A — Sai tên target

Đổi `depends="compile-tests"` thành `depends="compile-test"` trong target `test`, nhưng không tạo target `compile-test`. Chạy `ant test` và đọc lỗi. Xác định vì sao đây là lỗi **cấu hình DAG**, không phải lỗi Java compiler.

### Bài B — Test bị bỏ qua do property

Thêm:

```xml
<property name="skip.tests" value="false"/>
<target name="test" unless="skip.tests">
    <!-- Chạy test runner -->
</target>
```

Quan sát target có thể bị skip dù chuỗi giá trị là `false`. Đề xuất cách dùng `<condition>` để tách nghĩa boolean khỏi việc property tồn tại.

### Bài C — Build xanh dù test lỗi

Trong `build.xml` tham khảo, tạm đổi `failonerror="true"` thành `false`, rồi làm `GreeterTest` thất bại. Quan sát mã thoát của Ant và ảnh hưởng tới `package`. Sau đó phục hồi `failonerror="true"` và khẳng định pipeline fail đúng.

### Bài D — Resource bị bỏ quên

Tạm bỏ `<copy>` trong `copy-resources` và chạy từ clean build. So sánh `jar tf` trước/sau. Dùng phép kiểm thử đọc `app.properties` từ classpath để chứng minh rằng chỉ tạo JAR có class chính chưa đủ.

### Bài E — Rủi ro file cũ

Thêm một resource bất kỳ, build JAR, rồi xóa resource khỏi `src/main/resources`. Chạy một lượt không clean và một lượt có clean, so sánh nội dung JAR. Quan sát cách file sinh còn sót có thể làm sai kết quả package, sau đó điều chỉnh chính sách clean/staging/đóng gói.

### Bài F — Đường dẫn chứa dấu cách

Chuyển dự án vào thư mục `Bài thực hành Ant`. Chạy từ thư mục cha:

```bash
ant -f "./Bài thực hành Ant/build.xml" clean verify
```

Quan sát sự khác biệt giữa quote đường dẫn ở **shell** và việc dùng property `location` **bên trong Ant**. Từ đó đánh giá tính đa nền tảng của buildfile.

### Bài G — Đánh giá buildfile của một dự án khác

Lấy một buildfile đã được phép đọc và lập báo cáo theo 10 tiêu chí phần 12. Với mỗi tiêu chí, ghi:

1. Phát hiện dựa trên XML/log/sản phẩm nào.
2. Mức 0/1/2 và lý do.
3. Thay đổi cụ thể có giá trị cao nhất.
4. Cách kiểm chứng sau thay đổi.

Không cho điểm `2` chỉ vì có tên target `test`; cần bằng chứng thực sự có runner test và quy tắc fail-fast.

## 17. Câu hỏi tự kiểm tra

1. Vì sao `BUILD SUCCESSFUL` chưa chứng minh ứng dụng đã được compile, test và đóng gói đủ?
2. Khác biệt giữa lỗi XML malformed và lỗi target không tồn tại là gì?
3. Khi `test` báo không tìm được class, cần kiểm tra những target và đường dẫn classpath nào?
4. Tại sao `<java fork="true" failonerror="false">` có thể khiến CI báo xanh sai?
5. `depends="test"` trong `package` giúp bảo vệ hợp đồng phát hành như thế nào?
6. Vì sao `clean` chỉ được xóa thư mục build sở hữu?
7. Giá trị `skip.tests=false` có khiến `unless="skip.tests"` cho phép chạy target không?
8. Nếu JAR được tạo nhưng thiếu `app.properties`, bạn tìm nguyên nhân trong những target nào?
9. Khi nào nên dùng `-verbose`, khi nào cần `-debug` hoặc `-diagnostics`?
10. Một tiêu chí trong bảng đánh giá thiết kế chỉ có thể đạt mức cao khi có loại bằng chứng nào?
11. Vì sao hai lần đóng gói JAR thành công vẫn có thể cho checksum khác nhau?
12. Nếu pipeline chỉ pass sau khi từng chạy một script thủ công, đó có thể là dấu hiệu của lỗi thiết kế nào?

## 18. Tổng kết bài thực hành

Chẩn đoán buildfile lỗi trong Apache Ant là quá trình **tái hiện đúng triệu chứng, xác định target và đầu vào liên quan, sửa nguyên nhân, rồi kiểm chứng kết quả**. Lỗi parser cần được giải quyết trước; lỗi đường dẫn/classpath cần đọc giá trị thực tế; lỗi logic target đòi hỏi xem `depends` và kiểm tra thực sự có chạy test; lỗi xanh giả cần thử mã thoát khi gây lỗi có chủ đích.

Đánh giá chất lượng thiết kế build phải xét cả **tính đúng, khả năng thất bại đúng, đầu ra sạch, khả năng tái lập, tính di động, an toàn và khả năng bảo trì**. Một `build.xml` đáng tin không đơn thuần chạy thành công ở máy tác giả: nó cho phép người khác thực thi từ một checkout sạch, hiểu vì sao từng bước chạy và dùng bằng chứng cụ thể để xác nhận sản phẩm cuối.
