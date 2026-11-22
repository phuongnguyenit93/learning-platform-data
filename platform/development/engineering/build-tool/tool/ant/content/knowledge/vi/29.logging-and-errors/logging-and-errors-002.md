# Ghi nhật ký từng giai đoạn bằng `record` trong Apache Ant

Một dự án dùng Apache Ant thường đi qua nhiều giai đoạn: chuẩn bị thư mục, biên dịch mã nguồn, chạy kiểm tra và đóng gói. Khi bản build thất bại, việc đọc một luồng thông báo dài trên terminal có thể khiến ta khó xác định lỗi bắt đầu ở đâu. Task **`<record>`** giúp lưu thông báo của từng giai đoạn vào tệp riêng, nhờ đó dễ tra cứu, so sánh và lưu lại bằng chứng khi xử lý lỗi.

Bài này hướng dẫn cách bật và dừng ghi log đúng phạm vi, thiết kế các tệp log theo giai đoạn và nhận biết những giới hạn quan trọng của `record`.

## 1. `record` hoạt động như thế nào?

`record` là task có sẵn của Ant, đăng ký một **listener** để nhận các thông điệp và sự kiện do Ant phát ra trong quá trình build. Khi recorder được bật, những thông điệp phù hợp với mức log đã chọn được ghi vào một tệp. Khi recorder bị dừng, Ant tiếp tục chạy các task khác nhưng recorder đó ngừng ghi.

Ví dụ ngắn nhất:

~~~xml
<target name="compile">
    <record name="compile.log" action="start" loglevel="verbose"/>

    <echo message="Bat dau bien dich"/>
    <javac srcdir="src" destdir="build/classes"
           includeantruntime="false"/>
    <echo message="Bien dich xong"/>

    <record name="compile.log" action="stop"/>
</target>
~~~

Đoạn này giả định thư mục `build/classes` đã tồn tại. Task `record` đầu tiên bắt đầu ghi vào `compile.log`; task `record` cuối cùng ngừng ghi. Các thông điệp của `javac` nằm giữa hai mốc có thể được lưu ở mức `verbose`, kể cả khi mức hiển thị trên terminal khác.

**Điểm cần nhớ:** `record` ghi thông điệp mà Ant phát ra thông qua hệ thống log. Nó không tự động thu thập mọi nội dung mà một chương trình bên ngoài ghi trực tiếp ra hệ thống, hoặc nội dung đã bị task chuyển hướng sang tệp khác.

### Các thuộc tính thường dùng

| Thuộc tính | Ý nghĩa | Ghi chú |
|---|---|---|
| `name` | Đường dẫn tệp nhận log | **Bắt buộc**; đồng thời là khóa định danh recorder. |
| `action` | `start` để ghi, `stop` để ngừng | Với recorder mới, mặc định là `start`; ở lần gọi sau, nếu bỏ qua `action` thì trạng thái trước đó được giữ. |
| `loglevel` | `error`, `warn`, `info`, `verbose` hoặc `debug` | Mặc định là `info`; có thể thay đổi trong cùng một build. |
| `append` | `true` để nối vào tệp cũ, `false` để tạo nội dung mới | Mặc định là `false`; chỉ có hiệu lực khi recorder của tên tệp đó được tạo lần đầu trong build. |
| `emacsmode` | Bỏ phần tiền tố tên task như `[javac]` khi đặt `true` | Mặc định `false`; thường nên giữ tiền tố để dễ tìm nguồn lỗi. |

Ví dụ ghi nhiều thông tin hơn:

~~~xml
<record name="logs/compile.log"
        action="start"
        append="false"
        loglevel="debug"/>
~~~

Ở mức `debug`, số dòng log có thể lớn. Hãy chọn `info` để theo dõi tiến trình cơ bản, `verbose` khi phân tích các bước của task và `debug` khi cần xem chi tiết chẩn đoán.

## 2. Mô hình tổ chức log theo giai đoạn

Có thể tách log như sau:

~~~text
du-an/
├── build.xml
├── src/
│   └── example/
│       └── Hello.java
├── build/                 # Tao ra trong qua trinh build
│   ├── classes/
│   └── dist/
└── logs/
    ├── 01-prepare.log
    ├── 02-compile.log
    ├── 03-smoke-test.log
    └── 04-package.log
~~~

Mỗi tệp tương ứng với một giai đoạn. Tiền tố số giúp sắp xếp theo thứ tự thực hiện. Đặt `logs/` **ngoài** `build/` để lệnh dọn dẹp `build/` không xóa mất log cần dùng khi điều tra lỗi.

Luồng thực hiện:

~~~text
bootstrap (tao thu muc logs)
          |
          v
prepare  ----> 01-prepare.log
          |
          v
compile  ----> 02-compile.log
          |
          v
smoke-test ---> 03-smoke-test.log
          |
          v
package  ----> 04-package.log
~~~

`bootstrap` tạo thư mục chứa log trước khi recorder đầu tiên mở tệp. Mỗi target khác sẽ bật một recorder ở đầu giai đoạn và dừng nó khi công việc hoàn tất.

## 3. Ví dụ hoàn chỉnh với `build.xml`

Tạo cấu trúc tối thiểu:

~~~text
du-an/
├── build.xml
└── src/
    └── example/
        └── Hello.java
~~~

Nội dung `src/example/Hello.java`:

~~~java
package example;

public class Hello {
    public static void main(String[] args) {
        System.out.println("Hello from Ant");
    }
}
~~~

Nội dung `build.xml`:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="phase-record-demo" default="build" basedir=".">

    <!-- Dung location de Ant tao duong dan tuyet doi theo basedir. -->
    <property name="src.dir" location="src"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="dist.dir" location="${build.dir}/dist"/>
    <property name="logs.dir" location="logs"/>

    <!-- Khoi tao thu muc log truoc khi goi record. -->
    <target name="bootstrap">
        <mkdir dir="${logs.dir}"/>
    </target>

    <!-- Giai doan 1: chuan bi thu muc dau ra. -->
    <target name="prepare" depends="bootstrap">
        <record name="${logs.dir}/01-prepare.log"
                action="start" append="false" loglevel="verbose"/>

        <echo message="[PREPARE] Bat dau chuan bi"/>
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
        <echo message="[PREPARE] Hoan tat"/>

        <record name="${logs.dir}/01-prepare.log" action="stop"/>
    </target>

    <!-- Giai doan 2: bien dich. -->
    <target name="compile" depends="prepare">
        <record name="${logs.dir}/02-compile.log"
                action="start" append="false" loglevel="verbose"/>

        <echo message="[COMPILE] Bat dau bien dich Java"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               debug="true"
               includeantruntime="false"/>
        <echo message="[COMPILE] Hoan tat"/>

        <record name="${logs.dir}/02-compile.log" action="stop"/>
    </target>

    <!-- Giai doan 3: chay ung dung de kiem tra co ban. -->
    <target name="smoke-test" depends="compile">
        <record name="${logs.dir}/03-smoke-test.log"
                action="start" append="false" loglevel="info"/>

        <echo message="[SMOKE TEST] Chay example.Hello"/>
        <java classname="example.Hello"
              fork="true"
              failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>
        </java>
        <echo message="[SMOKE TEST] Hoan tat"/>

        <record name="${logs.dir}/03-smoke-test.log" action="stop"/>
    </target>

    <!-- Giai doan 4: tao JAR. -->
    <target name="package" depends="smoke-test">
        <record name="${logs.dir}/04-package.log"
                action="start" append="false" loglevel="verbose"/>

        <echo message="[PACKAGE] Dong goi JAR"/>
        <jar destfile="${dist.dir}/app.jar"
             basedir="${classes.dir}"/>
        <echo message="[PACKAGE] Hoan tat"/>

        <record name="${logs.dir}/04-package.log" action="stop"/>
    </target>

    <target name="build" depends="package">
        <echo message="Build hoan tat: ${dist.dir}/app.jar"/>
    </target>

    <!-- Chi xoa san pham build, giu logs de xem lai. -->
    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

</project>
~~~

**Vì sao khai báo đường dẫn bằng `location`?** Ant chuyển các giá trị như `src`, `build` và `logs` thành đường dẫn tuyệt đối dựa trên `basedir`. Điều này tránh nhầm lẫn giữa thư mục dự án và thư mục hiện hành của tiến trình khi xác định vị trí tệp log.

**Vì sao mỗi target dùng một tên tệp khác nhau?** Ant nhận diện recorder theo `name`. Nếu dùng cùng một `name` ở nhiều giai đoạn, các lần gọi sẽ điều khiển **cùng một recorder**, nên kết quả có thể là nhiều đoạn được nối tiếp trong một tệp, thay vì các tệp riêng.

**Vì sao có `echo` ở đầu và cuối?** Chúng tạo mốc dễ tìm khi đọc file. Mốc hoàn tất xuất hiện khi các task trong giai đoạn chạy thành công đến cuối; nếu task ném lỗi và dừng build, dòng kết thúc phía sau sẽ không được thực hiện.

## 4. Chạy bản build và tìm log

Yêu cầu: đã cài JDK, Apache Ant và có thể gọi lệnh `ant` từ terminal. Tại thư mục chứa `build.xml`, chạy:

~~~bash
ant clean build
~~~

Ant thực hiện `clean` trước, sau đó theo chuỗi phụ thuộc `bootstrap → prepare → compile → smoke-test → package → build`. Kết quả mong đợi:

- `build/classes/example/Hello.class`: mã đã biên dịch.
- `build/dist/app.jar`: sản phẩm đóng gói.
- `logs/01-prepare.log` đến `logs/04-package.log`: thông điệp của từng giai đoạn.

Ví dụ **minh họa** phần nội dung `logs/02-compile.log` (số dòng và thông điệp thực tế tùy phiên bản Ant, JDK và trạng thái mã nguồn):

~~~text
[echo] [COMPILE] Bat dau bien dich Java
[javac] Compiling 1 source file to .../build/classes
[echo] [COMPILE] Hoan tat
~~~

Xem log bằng terminal:

~~~bash
# macOS/Linux
cat logs/02-compile.log
grep -n "error" logs/02-compile.log
~~~

~~~powershell
# Windows PowerShell
Get-Content .\logs\02-compile.log
Select-String -Path .\logs\02-compile.log -Pattern 'error'
~~~

Khi cần biên dịch lại để quan sát log `javac`, chạy `ant clean build`. Nếu chạy `ant build` ngay sau một bản build thành công mà mã nguồn không đổi, `javac` có thể nhận thấy class đã cập nhật và không biên dịch lại; log khi đó ít dòng hơn.

### Cách đọc log khi xảy ra lỗi

Giả sử mã Java có lỗi cú pháp và `javac` thất bại:

1. Kiểm tra giai đoạn cuối được bắt đầu: `02-compile.log` có marker `[COMPILE] Bat dau`.
2. Tìm thông báo `error`, tên tệp và số dòng do `javac` cung cấp (nếu đã được Ant phát ra).
3. Nếu thiếu marker `[COMPILE] Hoan tat`, công việc đã không chạy đến cuối giai đoạn.
4. Vì `package` phụ thuộc `smoke-test`, còn `smoke-test` phụ thuộc `compile`, lỗi biên dịch chặn các giai đoạn sau. File log từ lần chạy trước có thể vẫn còn, nên không được xem sự tồn tại của `04-package.log` là bằng chứng rằng lần chạy hiện tại đã đóng gói thành công.

Lưu ý cuối cùng đặc biệt quan trọng: `append="false"` làm mới tệp **khi recorder đó được tạo trong lần chạy hiện tại**. Nếu giai đoạn chưa chạy đến, Ant không đụng tới tệp log cũ của giai đoạn ấy. Để đối chiếu một lần build, nên kết hợp timestamp của tệp hoặc tạo thư mục log riêng cho từng lần chạy.

## 5. Điều chỉnh mức độ chi tiết và cách ghi tiếp

### Chọn mức log

~~~xml
<!-- Chi thong diep loi -->
<record name="${logs.dir}/errors.log"
        action="start" loglevel="error"/>

<!-- Ghi ca thong diep chan doan chi tiet -->
<record name="${logs.dir}/compile-debug.log"
        action="start" loglevel="debug"/>
~~~

Một dự án có thể bật **nhiều recorder cùng lúc**. Ví dụ, recorder `errors.log` và `compile-debug.log` có thể cùng nhận sự kiện ở giai đoạn biên dịch, nhưng lọc theo mức log khác nhau. Khi cần log tách biệt hoàn toàn giữa các giai đoạn, không bật chồng lấn recorder không liên quan.

`loglevel` của `record` quy định nội dung của **tệp được ghi**; nó khác với mức hiển thị trên terminal do các tùy chọn như `ant -verbose` và `ant -debug` điều khiển.

### Ghi nối giữa các lần chạy

~~~xml
<record name="${logs.dir}/history.log"
        action="start" append="true" loglevel="info"/>
~~~

Dùng `append="true"` khi muốn giữ lịch sử trong cùng tệp. Nên thêm dòng đánh dấu lần chạy để phân biệt các phiên:

~~~xml
<tstamp>
    <format property="run.started" pattern="yyyy-MM-dd HH:mm:ss"/>
</tstamp>
<record name="${logs.dir}/history.log"
        action="start" append="true"/>
<echo message="===== BUILD BAT DAU: ${run.started} ====="/>
~~~

Với các log theo giai đoạn chỉ dùng để phân tích lần chạy mới nhất, `append="false"` thường dễ đọc hơn. Hãy nhớ: thuộc tính `append` chỉ có tác dụng lúc tạo recorder lần đầu cho một tên tệp trong build; gọi `stop` rồi `start` với cùng tên trong cùng build **không xóa và tạo lại tệp**.

## 6. Phân biệt `record` với các cách ghi log khác

| Cách làm | Phạm vi | Tình huống phù hợp |
|---|---|---|
| `<record name="..." action="start/stop"/>` | Khoảng thời gian được bật trong luồng sự kiện Ant | Tạo `compile.log`, `test.log`, `package.log` theo giai đoạn. |
| `ant -logfile full-build.log build` | Log của cả lệnh Ant, từ góc nhìn logger dòng lệnh | Lưu nhật ký tổng thể, nhất là khi lỗi xảy ra trước khi một recorder được bật. |
| `<echo file="..." append="true" message="..."/>` | Một thông điệp do người viết build chủ động tạo | Ghi marker hoặc thông tin tóm tắt tùy chỉnh. |
| `ant -verbose build` hoặc `ant -debug build` | Mức hiển thị của logger trên terminal | Xem thêm chi tiết trong phiên chạy thủ công. |

`record` và `-logfile` có thể sử dụng cùng nhau. Chẳng hạn:

~~~bash
ant -f build.xml -logfile full-build.log clean build
~~~

Lệnh này tạo log tổng thể `full-build.log`; đồng thời các task `record` trong `build.xml` vẫn tạo các tệp riêng của từng giai đoạn.

## 7. Các lỗi triển khai thường gặp

### 7.1. Không tạo được tệp log

**Biểu hiện:** Ant báo lỗi khi thực hiện `record`, hoặc đường dẫn log không đúng dự kiến.

**Nguyên nhân thường gặp:** thư mục cha chưa tồn tại, quyền ghi không đủ hoặc đường dẫn tương đối được hiểu theo thư mục chạy lệnh.

**Cách xử lý:** tạo `logs.dir` ở target `bootstrap` rồi dùng `<property name="logs.dir" location="logs"/>` và `name="${logs.dir}/..."`.

### 7.2. Tệp log không có thông tin mong đợi

Kiểm tra ba yếu tố: recorder đã `start` trước task cần theo dõi chưa, `loglevel` đã đủ chi tiết chưa, và task đó có thực sự phát thông điệp qua hệ thống logging của Ant không. Đối với các lệnh bên ngoài chạy bằng `<exec>` hoặc `<java>`, việc chuyển hướng output riêng có thể làm những dòng ấy không đi vào `record`.

### 7.3. Log của hai giai đoạn bị trộn

Điều này xảy ra khi cùng một recorder được bật xuyên qua nhiều giai đoạn hoặc các recorder khác nhau có khoảng thời gian hoạt động chồng nhau. Đặt `action="stop"` ngay sau nhóm task muốn ghi và dùng tên tệp riêng cho mỗi giai đoạn.

### 7.4. Không thấy dòng kết thúc khi build lỗi

Ant thường ngừng thực hiện các task tiếp theo trong target khi một task thất bại. Vì thế, lệnh `<record action="stop"/>` nằm sau task lỗi có thể không chạy. Recorder vẫn thuộc vòng đời build và Ant đóng stream khi build kết thúc, nhưng **không nên coi `stop` như cơ chế `finally` luôn được thực thi**. Cần giữ thêm log tổng thể nếu yêu cầu điều tra lỗi bao gồm cả bước khởi tạo và thông tin lỗi cuối của build.

### 7.5. Log không được làm mới dù đã đặt `append="false"`

Nếu tệp chưa được kích hoạt trong lần chạy mới, nội dung cũ vẫn nằm trên đĩa. Đây là lý do không nên lấy sự tồn tại của tệp làm tín hiệu giai đoạn đã chạy. Có thể lưu log trong thư mục mang mã lần chạy do hệ thống CI cấp, hoặc xóa log cũ một cách có chủ đích trước khi build nếu chính sách lưu trữ cho phép.

### 7.6. Log chứa đường dẫn hoặc dữ liệu nhạy cảm

Ở mức `verbose`/`debug`, một số task có thể in ra tham số lệnh, đường dẫn và cấu hình. Tránh đưa token, mật khẩu hoặc khóa bí mật vào thông điệp `echo` và tham số được log; phân quyền tệp log phù hợp khi đưa chúng vào CI hoặc hệ thống chia sẻ.

## 8. Quy tắc thiết kế cho dự án thực tế

Một cấu trúc dễ bảo trì thường áp dụng các nguyên tắc sau:

- **Một giai đoạn, một tệp log:** dùng tên mô tả và số thứ tự để xác định nơi xảy ra lỗi.
- **Mở và dừng có chủ đích:** đặt `start` ngay trước khối task chính; đặt `stop` ngay sau khối đó khi luồng chạy bình thường.
- **Tạo thư mục trước khi ghi:** target chuẩn bị nơi lưu trữ phải chạy trước `record`.
- **Chọn độ chi tiết theo nhu cầu:** mặc định `info` hoặc `verbose`; chỉ dùng `debug` khi điều tra chuyên sâu.
- **Đánh dấu đầu/cuối giai đoạn:** dùng `echo` để phân biệt lần chạy thành công tới cuối target với lần bị gián đoạn.
- **Quản lý log cũ:** dùng `append` và chính sách giữ log rõ ràng, nhất là trên CI; không suy ra thành công từ sự tồn tại của tệp.
- **Giữ bản log tổng thể khi cần:** các lỗi trước khi recorder được bật và một số thông báo cuối build cần được theo dõi qua logger toàn cục.

## 9. Bài thực hành gợi ý

Sau khi chạy bản ví dụ, thử ba thay đổi để quan sát cơ chế hoạt động:

1. Đổi `loglevel` của `02-compile.log` từ `verbose` sang `info`, chạy `ant clean build` rồi quan sát lượng thông tin trong log biên dịch.
2. Cố ý bỏ dấu chấm phẩy trong `Hello.java`, chạy lại và tìm tên tệp, số dòng lỗi trong `02-compile.log`; kiểm tra xem marker `[COMPILE] Hoan tat` có xuất hiện không.
3. Sửa lại mã Java, chạy thành công, sau đó đổi `append="false"` thành `append="true"` cho một log và chạy hai lần; so sánh với chế độ tạo mới nội dung.

Qua bài thực hành, điểm cốt lõi cần nắm là: **`record` tạo vùng quan sát có giới hạn trong thời gian thực thi Ant**. Bằng cách đặt ranh giới `start/stop` đúng chỗ, chọn `loglevel` phù hợp và quản lý vòng đời tệp, ta có thể biến một bản build nhiều bước thành tập nhật ký dễ theo dõi và dễ xử lý lỗi.

**Tài liệu tham khảo:** [Apache Ant Manual — Record task](https://ant.apache.org/manual/Tasks/recorder.html), [Listeners & Loggers](https://ant.apache.org/manual/listeners.html).
