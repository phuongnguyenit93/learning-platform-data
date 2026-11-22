# Tách buildfile bằng `import` và `include` trong Apache Ant

Khi dự án Ant lớn dần, một file `build.xml` duy nhất có thể chứa quá nhiều target: biên dịch, kiểm thử, đóng gói, tạo Javadoc, triển khai và các tác vụ dùng chung. Việc tách các nhóm target thành những buildfile nhỏ giúp cấu trúc dễ đọc, dễ tái sử dụng và dễ giao trách nhiệm cho từng phần của dự án.

Apache Ant cung cấp hai task cấp project để ghép buildfile: `<import>` và `<include>`. Cả hai đều nạp định nghĩa từ một buildfile khác vào cùng project Ant hiện tại. Điểm khác biệt chính nằm ở cách đặt tên target, cách xử lý quan hệ `depends` và khả năng ghi đè target.

- Dùng **`import`** khi buildfile chính cần tùy biến hoặc ghi đè target được khai báo trong file dùng chung.
- Dùng **`include`** khi muốn nạp một nhóm target dưới namespace riêng, giữ nguyên dependency nội bộ của file được nạp và tránh target trùng tên.

## 1. Vì sao nên tách buildfile?

Giả sử một dự án có các nhóm công việc:

| Nhóm | Target thường gặp |
|---|---|
| Java | `init`, `compile`, `jar` |
| Kiểm thử | `compile-test`, `test`, `test-report` |
| Tài liệu | `javadoc`, `docs-archive` |
| Web | `war`, `deploy` |
| Phát hành | `release`, `publish`, `clean` |

Nếu đặt tất cả vào một file, người đọc phải tìm qua nhiều phần không liên quan để hiểu một quy trình. Khi tách file, mỗi phần có thể tập trung vào một nhóm target và buildfile chính chỉ còn vai trò điều phối.

Ví dụ cấu trúc:

```text
project/
├── build.xml
└── build/
    ├── java-targets.xml
    ├── test-targets.xml
    ├── docs-targets.xml
    └── web-targets.xml
```

Buildfile chính có thể nạp các file con bằng `import` hoặc `include`, sau đó gọi các target của chúng như một phần của cùng project.

## 2. Cách hoạt động chung của `import` và `include`

Cả hai task đều được đặt trực tiếp bên trong phần tử `<project>`, ở cấp cao nhất của buildfile. Chúng không được đặt bên trong một `<target>` vì Ant phải đọc các buildfile con trong lúc phân tích project, trước khi thực thi target.

Ví dụ:

```xml
<project name="inventory" default="build" basedir=".">
    <import file="build/java-targets.xml"/>
    <include file="build/test-targets.xml"/>

    <target name="build" depends="compile,test"/>
</project>
```

Khi Ant đọc buildfile, nó nạp các target được khai báo trong hai file con vào project hiện tại. Sau đó dependency graph được xây dựng từ toàn bộ các target có sẵn.

Điều này khác với task `<ant>`: `<ant>` chạy một buildfile như một project con trong một lần gọi Ant khác. `import` và `include` chỉ ghép định nghĩa target vào project hiện tại, không tạo một quy trình build độc lập.

## 3. Dùng `import` để chia sẻ và ghi đè target

`import` làm cho target của file được nạp có thể được gọi bằng tên thông thường. Nếu target trong buildfile chính có cùng tên với target đã import, target của buildfile chính được ưu tiên. Target gốc từ file import vẫn có thể được gọi qua tên có prefix.

Đây là tính năng hữu ích khi muốn có quy trình mặc định dùng chung nhưng cho phép từng ứng dụng thay đổi một bước cụ thể.

### File dùng chung `build/java-targets.xml`

```xml
<project name="shared-java">

    <target name="init">
        <mkdir dir="build/classes"/>
        <mkdir dir="build/libs"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="src/main/java"
               destdir="build/classes"
               encoding="UTF-8"
               includeantruntime="false"/>
    </target>

    <target name="jar" depends="compile">
        <jar destfile="build/libs/application.jar"
             basedir="build/classes"/>
    </target>

</project>
```

### Buildfile chính `build.xml`

```xml
<project name="inventory" default="jar" basedir=".">

    <import file="build/java-targets.xml" as="java"/>

    <!-- Ghi đè target compile của file dùng chung. -->
    <target name="compile" depends="java.compile">
        <echo message="Đã biên dịch phần mã riêng của Inventory."/>
    </target>

</project>
```

Khi chạy `ant jar`, Ant thực hiện chuỗi sau:

1. Target `jar` từ file dùng chung có dependency `compile`.
2. Vì buildfile chính định nghĩa target `compile`, target này được chọn.
3. Target `compile` của buildfile chính phụ thuộc `java.compile`, tức phiên bản gốc đã import.
4. `java.compile` thực hiện compile dùng chung và dependency `init` của nó.
5. Sau khi `java.compile` xong, phần thân target `compile` của ứng dụng chạy.
6. Target `jar` tiếp tục đóng gói.

Target gốc có thể được gọi bằng `java.compile`; target `compile` không prefix là phiên bản tùy biến của buildfile chính. Cách này cho phép mở rộng hành vi mà không phải sao chép toàn bộ target dùng chung.

### Tên target sau khi import

Giả sử file được import có khai báo `<project name="shared-java">` và target `compile`. Nếu không chỉ định `as`, Ant dùng tên project `shared-java` làm prefix cho tên target gốc. Nếu dùng `as="java"`, tên có prefix là `java.compile`.

Với `import`, target thường có thể được gọi theo hai cách:

- Tên thông thường, ví dụ `compile`, có thể bị target trong buildfile chính ghi đè.
- Tên có prefix, ví dụ `java.compile`, gọi target được import từ file con.

Prefix mặc định được phân cách bằng dấu chấm. Có thể đổi dấu phân cách bằng `prefixSeparator`, ví dụ `prefixSeparator="-"` sẽ tạo tên `java-compile`.

## 4. Dùng `include` để tạo namespace riêng

`include` cũng nạp target vào project hiện tại, nhưng tất cả target được đặt dưới prefix. Các dependency trong file được include cũng được viết lại để dùng prefix đó. Vì vậy, target trong file được include giữ được quan hệ nội bộ và không bị target cùng tên trong buildfile chính ghi đè.

### File `build/web-targets.xml`

```xml
<project name="web">

    <target name="init">
        <mkdir dir="build/web"/>
    </target>

    <target name="war" depends="init">
        <war destfile="build/web/application.war"
             webxml="src/main/webapp/WEB-INF/web.xml">
            <fileset dir="src/main/webapp"
                     excludes="WEB-INF/**"/>
        </war>
    </target>

</project>
```

### Buildfile chính

```xml
<project name="inventory" default="release" basedir=".">
    <include file="build/web-targets.xml" as="web"/>

    <target name="init">
        <echo message="Chuẩn bị thư mục chung của ứng dụng"/>
        <mkdir dir="build"/>
    </target>

    <target name="release" depends="web.war"/>
</project>
```

Các target được include có tên `web.init` và `web.war`. Dependency của `web.war` được viết lại thành `web.init`, vì vậy chạy `ant release` sẽ gọi `web.init` trước `web.war`. Target `init` không prefix trong buildfile chính là target khác; nó không ghi đè `web.init`.

Đây là điểm quan trọng của `include`: các target bên trong file con tự quản lý dependency theo namespace của chúng. Buildfile chính gọi target công khai như `web.war` mà không cần biết toàn bộ các bước nội bộ.

## 5. Khác biệt chính giữa `import` và `include`

| Đặc điểm | `import` | `include` |
|---|---|---|
| Tên target | Có tên thường và tên có prefix | Chỉ có tên có prefix |
| Ghi đè target từ file con | Có thể ghi đè bằng target cùng tên trong buildfile chính | Không ghi đè được target đã prefix |
| Dependency của file con | Giữ nguyên tên target ban đầu | Được viết lại với prefix |
| Mục đích phù hợp | Tùy biến target dùng chung | Đóng gói nhóm target độc lập, tránh xung đột tên |
| Nạp cùng một file nhiều lần | Không hỗ trợ import lặp cùng file | Có thể include nhiều lần với prefix khác nhau |

Quy tắc lựa chọn dễ nhớ: nếu cần ghi đè target hoặc muốn target dùng chung gọi target tùy biến của ứng dụng, dùng `import`. Nếu muốn file con hoạt động như một nhóm target có namespace riêng và dependency tự khép kín, dùng `include`.

## 6. Các thuộc tính của `import` và `include`

| Thuộc tính | Ý nghĩa | Mặc định/Ghi chú |
|---|---|---|
| `file` | File build cần nạp | Bắt buộc nếu không dùng nested resource collection |
| `as` | Prefix đặt trước tên target | Mặc định lấy từ thuộc tính `name` của phần tử `project` trong file con; với `include`, cần có prefix từ `as` hoặc `project name` |
| `prefixSeparator` | Ký tự phân cách prefix và tên target | Mặc định là dấu chấm `.` |
| `optional` | Cho phép tiếp tục nếu file không tồn tại | Mặc định `false`; file thiếu thường làm build thất bại |

Ví dụ dùng prefix tùy chỉnh và dấu phân cách gạch ngang:

```xml
<include file="build/db-targets.xml"
         as="database"
         prefixSeparator="-"/>
```

Target `migrate` trong file con sẽ có tên `database-migrate`.

### `optional="true"`

Có thể đánh dấu file nạp là tùy chọn:

```xml
<import file="build/local-developer-targets.xml"
        optional="true"/>
```

Nếu file không tồn tại, Ant tiếp tục build thay vì dừng lỗi. Chỉ dùng `optional="true"` cho phần mở rộng thực sự không bắt buộc, ví dụ target tiện ích dành riêng cho máy lập trình viên. Không nên dùng cho file chứa target compile, test hoặc package thiết yếu vì lỗi thiếu file sẽ bị che giấu.

## 7. Quy tắc đường dẫn khi nạp buildfile

Đường dẫn tương đối trong thuộc tính `file` của `import` và `include` được phân giải tương đối với buildfile đang thực hiện thao tác nạp. Ví dụ:

```xml
<project name="inventory" basedir=".">
    <import file="build/common/java.xml"/>
</project>
```

Nếu `build.xml` nằm ở thư mục gốc dự án, Ant tìm file trong `build/common/java.xml` tương đối với vị trí của `build.xml`.

Có một điểm cần chú ý: file được import/include được xử lý như thể nội dung của nó nằm trong buildfile chính. Vì vậy, các đường dẫn tài nguyên tương đối được khai báo bên trong file con thường được giải quyết theo `basedir` của project chính, không tự động theo thư mục chứa file con.

Ví dụ, file `build/common/java.xml` muốn tham chiếu `build/common/config/checkstyle.xml`. Có thể lấy đường dẫn file build con thông qua property đặc biệt `ant.file.<projectname>`:

```xml
<!-- Trong build/common/java.xml -->
<project name="common">
    <dirname property="common.build.dir"
             file="${ant.file.common}"/>

    <property name="common.checkstyle.config"
              location="${common.build.dir}/config/checkstyle.xml"/>
</project>
```

Khi project con có `name="common"`, Ant cung cấp property `ant.file.common` chứa đường dẫn đến file được nạp. Task `dirname` lấy thư mục chứa file đó; từ đó có thể tạo đường dẫn đến resource đặt cạnh buildfile con.

Không nhầm `ant.file.common` với `basedir`: một cái chỉ vị trí file build con, cái kia là thư mục gốc của project đang chạy. Nếu file được nạp không khai báo `project name`, property `ant.file.<projectname>` tương ứng không được tạo theo cách này.

## 8. Properties không được tự động namespace

Prefix của `import` và `include` áp dụng cho tên target, không tự động thêm prefix vào tên property. Ví dụ file con:

```xml
<project name="common">
    <property name="output.dir" location="build/common"/>
</project>
```

Khi nạp file này với `as="java"`, property vẫn có tên `output.dir`, không phải `java.output.dir`.

Ant property thông thường có tính bất biến: khi một property đã được đặt, khai báo sau cùng tên thường không thay đổi giá trị đó. Vì vậy, nhiều buildfile con cùng khai báo `build.dir`, `output.dir` hoặc `lib.dir` có thể vô tình dùng chung giá trị hoặc phụ thuộc vào thứ tự nạp.

Để tránh xung đột:

- Tự đặt prefix cho tên property, ví dụ `java.output.dir`, `web.output.dir`, `docs.output.dir`.
- Chỉ khai báo property dùng chung một lần trong buildfile chính nếu nhiều module thực sự cần cùng một giá trị.
- Không giả định `as="java"` sẽ biến mọi property trong file con thành property có prefix `java.`.
- Nếu cần cùng một nhóm target chạy với nhiều cấu hình độc lập, cân nhắc macro có tham số hoặc gọi buildfile con bằng task `<ant>` thay vì include cùng file nhiều lần rồi mong property tự tách biệt.

## 9. Nạp một file nhiều lần và quản lý namespace

`include` cho phép nạp cùng một file nhiều lần với các prefix khác nhau. Điều này hữu ích khi file con chỉ khai báo target và mỗi lần include có một namespace khác:

```xml
<project name="application" default="all">
    <include file="build/check-targets.xml" as="backend"/>
    <include file="build/check-targets.xml" as="frontend"/>

    <target name="all" depends="backend.check,frontend.check"/>
</project>
```

Ant tạo ra các target `backend.check` và `frontend.check` từ cùng định nghĩa `check`.

Tuy nhiên, đây không phải hai project độc lập. Chúng vẫn thuộc cùng project Ant, dùng chung property và reference. Nếu file `check-targets.xml` đặt property `report.dir` ở cấp project, property đó không tự có hai bản `backend.report.dir` và `frontend.report.dir`. Muốn hai lần chạy dùng đầu ra khác nhau, phải thiết kế property/target riêng hoặc dùng cơ chế có tham số.

`import` không được dùng để nạp cùng một file nhiều lần như vậy. Nếu cần tái sử dụng định nghĩa target dưới nhiều namespace, `include` là lựa chọn phù hợp hơn.

## 10. `import`/`include` khác với task `<ant>` và `<antcall>`

Các cơ chế sau có mục đích khác nhau:

| Cơ chế | Cách hoạt động | Khi nên dùng |
|---|---|---|
| `import` | Nạp target vào cùng project; cho phép ghi đè target | Chia sẻ logic build có điểm tùy biến |
| `include` | Nạp target vào cùng project dưới prefix, dependency được prefix hóa | Ghép các nhóm target có namespace riêng |
| `<ant>` | Chạy một buildfile khác như project con | Xây dựng subproject có lifecycle riêng hoặc cần project/basedir riêng |
| `<antcall>` | Gọi lại một target trong project qua một lượt thực thi Ant con | Trường hợp cần gọi target theo cách Ant task hỗ trợ; thường không cần dùng để thay thế dependency thông thường |

Ví dụ gọi subproject bằng `<ant>`:

```xml
<target name="build-web-module">
    <ant antfile="web/build.xml"
         dir="web"
         target="war"
         inheritAll="false">
        <property name="environment" value="staging"/>
    </ant>
</target>
```

Ở đây, `web/build.xml` chạy trong một project con. Task `<ant>` phù hợp khi module có build lifecycle riêng hoặc cần truyền property có kiểm soát. Với `import`/`include`, target được ghép vào project hiện tại và chia sẻ cùng không gian property/reference.

## 11. Ví dụ tổ chức buildfile cho ứng dụng

Giả sử dự án có các file:

```text
project/
├── build.xml
└── build/
    ├── java.xml
    ├── test.xml
    └── docs.xml
```

Buildfile chính có thể điều phối các nhóm bằng `include`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory" default="verify" basedir=".">

    <property name="build.dir" location="build-output"/>
    <property name="java.classes.dir" location="${build.dir}/classes"/>
    <property name="test.classes.dir" location="${build.dir}/test-classes"/>
    <property name="docs.dir" location="${build.dir}/docs"/>

    <include file="build/java.xml" as="java"/>
    <include file="build/test.xml" as="test"/>
    <include file="build/docs.xml" as="docs"/>

    <target name="verify" depends="test.run,docs.generate"/>

    <target name="clean">
        <delete dir="${build.dir}"/>
    </target>

</project>
```

Trong ví dụ, file `java.xml` có thể cung cấp target `compile`; `test.xml` cung cấp `compile` và `run`; `docs.xml` cung cấp `generate`. Do các target được prefix hóa, các tên có thể trùng giữa các file mà không gây xung đột: `java.compile`, `test.compile`, `docs.generate`.

Ví dụ trên giả định các file con đã dùng đúng dependency có prefix nội bộ của chúng. Nếu `test.run` cần `java.compile`, file test phải phụ thuộc target đó theo tên công khai phù hợp hoặc buildfile chính phải điều phối dependency giữa các nhóm.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Ant không tìm thấy target có prefix | Prefix lấy từ `as` hoặc `project name` khác với tên đang gọi | Kiểm tra `as`, `name` và `prefixSeparator` |
| Target trong file include không chạy khi gọi tên thường | `include` chỉ tạo tên có prefix | Gọi `prefix.target`, ví dụ `web.war` |
| Target trong file import không dùng bản tùy biến | Target chính không trùng tên hoặc dependency đang gọi alias prefixed | Xác định target nào cần override và kiểm tra tên dependency không prefix |
| Target import gọi sai bước phụ thuộc | `depends` của import giữ nguyên tên không prefix | Kiểm tra target cùng tên trong buildfile chính có đang override dependency đó không |
| Include không ghi đè target chính | Đây là hành vi được thiết kế của include | Dùng `import` nếu cần override hoặc đổi tên target để tránh xung đột |
| File build con không tìm thấy resource cạnh nó | Đường dẫn tương đối được giải quyết theo project chính | Dùng `ant.file.<projectname>` và `dirname` để tính thư mục của file con |
| Hai file con ghi đè property của nhau | Property dùng chung tên và Ant property bất biến | Đặt prefix thủ công cho property hoặc chuyển cấu hình thành tham số |
| Build dừng khi file tùy chọn không có | `optional` mặc định là false | Chỉ với module tùy chọn, đặt `optional="true"` |
| Không thể import cùng file hai lần | Import không hỗ trợ nạp trùng cùng file | Dùng include với các prefix khác nhau nếu thật sự cần |
| Đặt import/include trong target gây lỗi | Đây là task cấp project, phải được xử lý lúc parse buildfile | Chuyển phần tử lên trực tiếp dưới `<project>` |

Khi debug, chạy `ant -p` để xem danh sách target có mô tả và gọi target có prefix rõ ràng. Có thể dùng `ant -projecthelp` để xem trợ giúp project. Khi cần xem thứ tự dependency, chạy Ant với chế độ verbose hoặc debug để theo dõi target được gọi.

## 13. Quy tắc tổ chức buildfile

- Giữ `build.xml` chính làm điểm vào và điều phối các nhóm công việc.
- Tách file theo trách nhiệm, ví dụ `java.xml`, `test.xml`, `docs.xml`, `web.xml`.
- Dùng `include` cho các nhóm target độc lập cần namespace riêng.
- Dùng `import` khi buildfile chính cần ghi đè target hoặc mở rộng target dùng chung.
- Đặt `as` rõ ràng để tên target không phụ thuộc vào một project name khó hiểu.
- Giữ dependency nội bộ trong file include; để buildfile chính gọi target công khai có prefix.
- Đặt prefix thủ công cho property và reference vì `as` chỉ prefix tên target.
- Dùng `ant.file.<projectname>` khi file con cần tham chiếu resource nằm cạnh chính file build đó.
- Chỉ đặt `optional="true"` cho module thực sự không bắt buộc.
- Không lạm dụng include cùng file nhiều lần nếu các lần chạy cần property hoặc reference độc lập.
- Dùng task `<ant>` khi cần project con có lifecycle/basedir riêng.

## 14. Bài tập tự kiểm tra

**Bài 1.** Khi nào nên dùng `import` thay vì `include`?

**Đáp án:** Khi buildfile chính cần ghi đè target từ file dùng chung hoặc muốn giữ tên target thông thường để các dependency gọi phiên bản tùy biến.

**Bài 2.** File được include với `as="web"` có target `package` và target `package` phụ thuộc `compile`. Ant tạo những tên target và dependency nào?

**Đáp án:** Target có tên `web.package` và `web.compile`; dependency của `web.package` được viết lại thành `web.compile`.

**Bài 3.** Vì sao target `init` trong buildfile chính không ghi đè `web.init` được tạo bởi include?

**Đáp án:** Vì include chỉ công bố target có prefix. `init` và `web.init` là hai tên khác nhau; include cũng không cho phép override target theo cơ chế của import.

**Bài 4.** Thuộc tính `as="java"` có đổi tên property `output.dir` thành `java.output.dir` không?

**Đáp án:** Không. Prefix chỉ áp dụng cho tên target. Property vẫn là `output.dir`, nên cần đặt prefix thủ công nếu muốn tránh trùng.

**Bài 5.** Một file build con nằm trong `build/common/` cần đọc file `config/checkstyle.xml` nằm cạnh nó. Dùng property nào để xác định vị trí file build con?

**Đáp án:** Nếu project trong file con có `name="common"`, dùng `${ant.file.common}` cùng task `dirname` để lấy thư mục chứa buildfile, rồi ghép đường dẫn resource.

**Bài 6.** Có thể include cùng một file hai lần với `as="dev"` và `as="prod"` để có hai bộ property độc lập không?

**Đáp án:** Không. Target được prefix thành `dev.*` và `prod.*`, nhưng property và reference vẫn thuộc cùng project. Cần thiết kế property riêng hoặc dùng macro/thực thi sub-build với tham số nếu cần cấu hình độc lập.

## Kết luận

`import` và `include` giúp chia buildfile Ant thành các nhóm target có thể quản lý và tái sử dụng. `import` giữ tên target thông thường, cho phép buildfile chính ghi đè target và vẫn cung cấp alias có prefix để gọi bản gốc. `include` chỉ công bố target dưới prefix và viết lại dependency để nhóm target giữ được cấu trúc nội bộ. Khi hiểu rõ namespace target, phạm vi property, đường dẫn tài nguyên và khác biệt với task `<ant>`, buildfile lớn có thể được chia nhỏ mà vẫn có dependency graph dễ theo dõi.

