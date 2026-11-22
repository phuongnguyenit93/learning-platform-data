# Xử lý lỗi biên dịch bằng failonerror và errorProperty

Task `<javac>` của Apache Ant biên dịch mã nguồn Java. Khi compiler phát hiện lỗi, build cần có cách phản hồi rõ ràng: dừng ngay để không chạy các bước sau, hoặc ghi nhận trạng thái lỗi để thực hiện một số thao tác xử lý rồi mới dừng với thông báo phù hợp.

Hai thuộc tính quan trọng của task `<javac>` là `failonerror` và `errorProperty`:

- `failonerror` quyết định task có làm build thất bại ngay khi biên dịch có lỗi hay không.
- `errorProperty` đặt một property khi quá trình biên dịch báo lỗi, để các bước sau có thể kiểm tra trạng thái đó.

Hiểu đúng hai thuộc tính này giúp lựa chọn giữa fail-fast và xử lý lỗi có kiểm soát, đồng thời tránh một build báo thành công dù source vẫn còn lỗi biên dịch.

## 1. Hành vi mặc định của javac

Một target compile cơ bản:

```xml
<target name="compile">
    <mkdir dir="build/classes"/>

    <javac srcdir="src/main/java"
           destdir="build/classes"
           encoding="UTF-8"
           includeantruntime="false"/>
</target>
```

Theo mặc định, `failonerror` là `true`. Nếu compiler báo lỗi, task `<javac>` làm build thất bại ngay. Ant hiển thị các chẩn đoán của compiler và dừng thực hiện những task tiếp theo trong luồng hiện tại.

Ví dụ, nếu `App.java` gọi một phương thức không tồn tại, compiler báo lỗi và target `compile` không hoàn tất. Các target phụ thuộc vào `compile`, chẳng hạn `test` hoặc `package`, cũng không được chạy.

Đây là hành vi phù hợp với phần lớn build thông thường: source không biên dịch được thì không nên tạo artifact phát hành.

## 2. Dùng failonerror để chọn cách phản hồi khi compile lỗi

`failonerror` nhận giá trị `true` hoặc `false`:

| Giá trị | Hành vi khi compiler báo lỗi |
|---|---|
| `true` | Task javac làm build thất bại ngay; đây là mặc định |
| `false` | Task không dừng build ngay chỉ vì lỗi biên dịch; các task tiếp theo trong target có thể tiếp tục |

Ví dụ cho phép target tiếp tục sau lỗi compile:

```xml
<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           failonerror="false"/>

    <echo message="The javac task has returned."/>
</target>
```

Nếu source có lỗi, compiler vẫn in diagnostics. Tuy nhiên, vì `failonerror="false"`, lỗi biên dịch đó không tự làm target dừng tại task javac. Task `<echo>` phía sau vẫn có thể chạy.

Điều này không có nghĩa compile thành công. Nó chỉ thay đổi thời điểm và cách build xử lý lỗi. Nếu không có bước kiểm tra bổ sung, build có thể kết thúc thành công dù class chưa được tạo đầy đủ. Vì vậy, khi dùng `failonerror="false"`, cần kết hợp `errorProperty` hoặc một cơ chế khác để không bỏ sót lỗi.

## 3. Dùng errorProperty để ghi nhận compile failure

Thuộc tính `errorProperty` nhận tên property mà Ant sẽ đặt khi compiler báo lỗi:

```xml
<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           includeantruntime="false"
           failonerror="false"
           errorProperty="compile.failed"/>

    <echo message="Compilation task completed; checking result."/>
</target>
```

Nếu compiler báo lỗi, Ant đặt property `compile.failed`. Nếu biên dịch thành công, property này không được đặt bởi lần gọi javac đó.

`errorProperty` chỉ là một dấu hiệu trạng thái. Nó không chứa toàn bộ thông báo lỗi, tên file, số dòng hoặc nội dung diagnostics. Các chi tiết compiler vẫn được in ra log; property giúp build quyết định bước tiếp theo.

Một điểm quan trọng: điều kiện cổ điển `if` và `unless` của Ant kiểm tra property có tồn tại hay không, không kiểm tra giá trị boolean của property. Với `errorProperty`, ta tận dụng đúng ngữ nghĩa này: property chỉ được đặt khi compile lỗi, vì vậy có thể dùng `if="compile.failed"` hoặc `<fail if="compile.failed">` để phản ứng.

## 4. Kết hợp failonerror=false và errorProperty để đưa ra thông báo riêng

Đây là mẫu thường dùng khi muốn compiler in diagnostics trước, sau đó Ant dừng với message của dự án:

```xml
<target name="compile">
    <javac srcdir="src/main/java"
           destdir="build/classes"
           encoding="UTF-8"
           includeantruntime="false"
           failonerror="false"
           errorProperty="compile.failed"/>

    <fail if="compile.failed"
          message="Compilation failed for the main source set. Review the compiler diagnostics above."/>

    <echo message="Main sources compiled successfully."/>
</target>
```

**Trình tự thực hiện:**

1. Ant gọi compiler thông qua task `<javac>`.
2. Nếu compiler báo lỗi, task đặt property `compile.failed` nhưng không dừng ngay vì `failonerror="false"`.
3. Ant thực hiện task `<fail>` tiếp theo.
4. Nếu `compile.failed` tồn tại, `<fail>` được kích hoạt và build thất bại với message riêng.
5. Nếu property không tồn tại, `<fail>` không kích hoạt và thông báo compile thành công được in ra.

Message của `<fail>` có thể nêu module, source set hoặc giai đoạn đang biên dịch. Compiler diagnostics phía trên vẫn cung cấp chi tiết file và dòng lỗi.

Nếu chỉ cần build dừng với lỗi compiler mặc định, không cần đặt `failonerror="false"` và `errorProperty`; giữ mặc định `failonerror="true"` đơn giản hơn.

## 5. Sơ đồ hai cách xử lý

**Fail-fast với mặc định:**

```text
<javac failonerror="true">
        |
        v
  Compiler result
        |
   +----+----+
   |         |
 Success    Error
   |         |
 Next task  BUILD FAILED
```

**Ghi nhận lỗi rồi dừng có kiểm soát:**

```text
<javac failonerror="false" errorProperty="compile.failed">
        |
        v
  Compiler result
        |
   +----+----+
   |         |
 Success    Error
   |         |
 no flag    set compile.failed
   |         |
   +----+----+
        |
        v
<fail if="compile.failed" message="..."/>
        |
   +----+----+
   |         |
 no flag   flag exists
   |         |
 Continue  BUILD FAILED
```

Trong mẫu thứ hai, `<fail>` là điểm quyết định cuối cùng. Không nên bỏ bước fail hoặc một bước kiểm tra tương đương nếu compile failure phải làm pipeline thất bại.

## 6. Dùng errorProperty trong target compile riêng

Một build có thể tách `init`, `compile`, `test` và `package`. Khi đó target compile chịu trách nhiệm xác nhận compiler thành công trước khi target sau được phép chạy.

```xml
<project name="sample-app" default="package" basedir=".">
    <property name="src.main" location="${basedir}/src/main/java"/>
    <property name="classes.dir" location="${basedir}/build/classes"/>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.main}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false"
               failonerror="false"
               errorProperty="main.compile.failed"/>

        <fail if="main.compile.failed"
              message="Main source compilation failed. Package was cancelled."/>
    </target>

    <target name="test" depends="compile">
        <echo message="Run tests after successful compilation."/>
    </target>

    <target name="package" depends="test">
        <jar destfile="dist/app.jar" basedir="${classes.dir}"/>
    </target>
</project>
```

Khi compile lỗi, `<fail>` trong target compile dừng build. Vì `test` phụ thuộc `compile`, target test không được chạy; tương tự, package cũng không được thực hiện.

Đây là cách đưa quy tắc lỗi vào đúng ranh giới của bước biên dịch. Target phía sau không cần tự kiểm tra lại property compile failure.

## 7. Xử lý riêng main source và test source

Ứng dụng Java thường có hai nhóm source: mã nguồn chính và mã nguồn kiểm thử. Có thể dùng hai property lỗi riêng để thông báo chính xác nhóm nào thất bại.

```xml
<project name="tested-app" default="verify" basedir=".">
    <property name="src.main" location="${basedir}/src/main/java"/>
    <property name="src.test" location="${basedir}/src/test/java"/>
    <property name="classes.dir" location="${basedir}/build/classes"/>
    <property name="test.classes.dir" location="${basedir}/build/test-classes"/>

    <path id="test.classpath">
        <pathelement location="${classes.dir}"/>
        <pathelement location="${test.classes.dir}"/>
        <fileset dir="lib">
            <include name="**/*.jar"/>
        </fileset>
    </path>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${test.classes.dir}"/>
    </target>

    <target name="compile-main" depends="init">
        <javac srcdir="${src.main}"
               destdir="${classes.dir}"
               includeantruntime="false"
               failonerror="false"
               errorProperty="main.compile.failed"/>
        <fail if="main.compile.failed"
              message="Main source compilation failed."/>
    </target>

    <target name="compile-test" depends="compile-main">
        <javac srcdir="${src.test}"
               destdir="${test.classes.dir}"
               includeantruntime="false"
               failonerror="false"
               errorProperty="test.compile.failed">
            <classpath refid="test.classpath"/>
        </javac>
        <fail if="test.compile.failed"
              message="Test source compilation failed. Unit tests were not started."/>
    </target>

    <target name="test" depends="compile-test">
        <echo message="Run the configured test runner here."/>
    </target>

    <target name="verify" depends="test">
        <echo message="Compilation and test preparation completed."/>
    </target>
</project>
```

`main.compile.failed` và `test.compile.failed` giúp phân biệt lỗi biên dịch ứng dụng với lỗi biên dịch test. Classpath của test có cả class chính, test class và thư viện test. Trong dự án thực tế, cần cấu hình dependency test đúng với framework đang sử dụng.

## 8. Phân biệt lỗi biên dịch với lỗi cấu hình compiler

`failonerror` và `errorProperty` được dùng để xử lý kết quả biên dịch do compiler báo về. Chúng không biến mọi vấn đề cấu hình Ant thành một compile failure có thể xử lý bằng property.

Ví dụ các vấn đề có thể khiến task thất bại theo cơ chế lỗi của Ant:

- Không tìm thấy compiler hoặc JDK cần thiết.
- `srcdir` hoặc `destdir` sai, không truy cập được.
- Classpath hoặc cấu hình task không hợp lệ.
- Adapter/compiler không thể khởi tạo hoặc gặp lỗi thực thi.

Trong các trường hợp này, Ant có thể ném lỗi task/build trực tiếp. Không nên giả định `failonerror="false"` sẽ che giấu tất cả lỗi môi trường, lỗi cấu hình hoặc lỗi nội bộ của compiler. `errorProperty` không phải một bộ bắt ngoại lệ tổng quát.

Vì vậy, hãy đọc diagnostics đầu tiên trong log. Nếu compiler chạy và báo lỗi source, `errorProperty` là cờ phù hợp. Nếu task không thể khởi tạo compiler hoặc truy cập thư mục, cần sửa cấu hình môi trường, đường dẫn hoặc classpath.

## 9. Property lỗi có tính bất biến

Ant property có tính bất biến: khi đã được đặt, property không thể được gán lại giá trị khác bằng một lần khai báo thông thường sau đó.

Điều này có ý nghĩa khi nhiều task `<javac>` dùng cùng một `errorProperty` trong một lần chạy build. Nếu lần compile đầu tiên đặt `compile.failed`, property đó vẫn tồn tại cho những lần kiểm tra tiếp theo trong cùng project. Một lần compile sau thành công không tự xóa cờ lỗi.

Ví dụ không nên dùng lại một property chung cho các bước độc lập nếu cần phân biệt trạng thái:

```xml
<!-- Nên dùng property riêng cho từng nhóm source. -->
<javac ... errorProperty="main.compile.failed"/>
<javac ... errorProperty="test.compile.failed"/>
```

Nếu cần thực hiện nhiều lượt compile độc lập với trạng thái mới, có thể tách thành build invocation riêng hoặc thiết kế property theo từng bước. Không giả định Ant tự reset error property giữa các lần gọi task.

## 10. Kết hợp errorProperty với các bước xử lý sau lỗi

Một lý do hợp lý để đặt `failonerror="false"` là cần chạy thêm một số thao tác chẩn đoán trước khi dừng. Ví dụ, có thể ghi thông tin về module hoặc lưu một báo cáo phụ trợ:

```xml
<target name="compile-module">
    <javac srcdir="modules/catalog/src/main/java"
           destdir="modules/catalog/build/classes"
           includeantruntime="false"
           failonerror="false"
           errorProperty="catalog.compile.failed"/>

    <echo message="Compiler diagnostics for module catalog are available in the build log."/>

    <fail if="catalog.compile.failed"
          message="Module 'catalog' could not be compiled. Stop the release pipeline and fix the reported source errors."/>
</target>
```

Task sau javac chỉ nên thực hiện công việc an toàn khi compile lỗi, chẳng hạn ghi message hoặc lưu báo cáo. Không nên tiếp tục đóng gói, publish hoặc deploy class output không hoàn chỉnh rồi mới fail ở cuối.

Nếu cần thu thập lỗi của nhiều module trước khi dừng, có thể ghi nhận cờ lỗi riêng cho từng module và tổng hợp ở một target cuối. Tuy nhiên, điều này phải được thiết kế rõ ràng để tránh một module lỗi nhưng module phụ thuộc vẫn dùng output không hợp lệ.

## 11. failonerror và errorProperty khác nhau thế nào?

| Thuộc tính | Vai trò | Có tự dừng build? | Dùng khi nào? |
|---|---|---|---|
| `failonerror="true"` | Chỉ định javac làm build thất bại ngay khi compile lỗi | Có | Build thông thường, muốn fail-fast |
| `failonerror="false"` | Cho phép task tiếp tục sau compile error | Không chỉ vì compile error | Cần xử lý trạng thái trước khi dừng |
| `errorProperty="compile.failed"` | Đặt cờ property nếu compiler báo lỗi | Không, tự nó không dừng build | Cần kiểm tra hoặc phân loại lỗi ở task tiếp theo |
| `<fail if="compile.failed">` | Dừng build nếu cờ lỗi tồn tại | Có | Muốn message riêng hoặc đặt điểm dừng có chủ đích |

Hai thuộc tính không thay thế nhau. `failonerror` điều khiển hành vi thất bại của task javac; `errorProperty` cung cấp thông tin trạng thái cho build script. Khi dùng `failonerror=false`, cần có bước xử lý cờ lỗi nếu compile failure vẫn phải làm build thất bại.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Build dừng ngay, không chạy `<fail>` tùy chỉnh | `failonerror` đang là `true` | Đặt `failonerror="false"` nếu cần kiểm soát điểm dừng sau javac |
| Build báo thành công dù compiler in lỗi | Dùng `failonerror="false"` nhưng không kiểm tra `errorProperty` | Thêm `<fail if="...">` hoặc một bước kiểm tra tương đương |
| `<fail if="compile.failed">` không chạy | Tên property khác với `errorProperty` hoặc compiler không báo compile error | Kiểm tra chính tả property và diagnostics javac |
| Build vẫn fail trước khi đến bước kiểm tra property | Lỗi task/cấu hình/compiler adapter thay vì compile error được ghi nhận | Kiểm tra JDK, `srcdir`, `destdir`, classpath và log lỗi gốc |
| Lần compile sau vẫn bị xem là lỗi | Property đã được đặt từ lần compile trước và không tự bị xóa | Dùng property riêng cho từng compile step hoặc invocation |
| Message không nêu module nào lỗi | Dùng một message chung cho nhiều source set | Đưa tên module/source set vào message |

## 13. Bài tập thực hành

1. Tạo lớp Java có một lỗi cú pháp và chạy target compile với cấu hình mặc định. Quan sát Ant dừng ngay khi compiler báo lỗi.
2. Đặt `failonerror="false"` và chạy lại. Quan sát compiler vẫn in diagnostics nhưng các task tiếp theo có thể chạy.
3. Thêm `errorProperty="compile.failed"` rồi thêm `<fail if="compile.failed">` với message riêng.
4. Sửa lỗi source và chạy lại. Khi compile thành công, property lỗi không được đặt trong invocation mới và target có thể tiếp tục.
5. Tách main source và test source, dùng hai error property khác nhau để xác định nhóm compile lỗi.
6. Thử sai đường dẫn `srcdir` để phân biệt lỗi cấu hình task với lỗi source do compiler báo.
7. Tạo target `package` phụ thuộc `compile`, xác nhận package không chạy khi target compile kết thúc bằng `<fail>`.
8. Viết message có tên module, source set và bước bị chặn để người đọc log có thể xác định nơi cần sửa.

## 14. Nguyên tắc áp dụng trong CI

Với pipeline thông thường, giữ `failonerror="true"` để compile lỗi làm job thất bại ngay. Chỉ dùng `failonerror="false"` khi có nhu cầu rõ ràng phải thực hiện thêm thao tác sau khi compiler báo lỗi. Trong trường hợp đó, luôn khai báo `errorProperty` và có bước fail hoặc tổng hợp trạng thái trước khi target phụ thuộc tiếp tục.

Đặt kiểm tra compile ở ranh giới giữa `compile` và `test`/`package`. Không cho bước phát hành sử dụng output không hoàn chỉnh. Giữ compiler diagnostics trong log và thêm message Ant có ngữ cảnh để phân biệt module hoặc source set bị lỗi.

Điều quan trọng là trạng thái build cuối cùng phải phản ánh đúng kết quả compiler. Một lần chạy Ant chỉ được xem là thành công khi tất cả nhóm source bắt buộc đã biên dịch thành công và các bước kiểm tra tiếp theo hoàn tất.
