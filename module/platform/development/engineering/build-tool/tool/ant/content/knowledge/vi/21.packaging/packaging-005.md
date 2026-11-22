# JAR thực thi với thư viện bên ngoài và giới hạn đường dẫn manifest

Một JAR thực thi (executable JAR) là gói Java có thể khởi chạy bằng lệnh `java -jar`. JAR này thường chứa lớp ứng dụng và tài nguyên của dự án. Nếu ứng dụng dùng thư viện bên ngoài, có thể phân phối các JAR dependency trong một thư mục `lib` cạnh JAR chính và khai báo chúng trong thuộc tính `Class-Path` của manifest.

Apache Ant hỗ trợ tạo JAR bằng task `<jar>`, ghi thuộc tính `Main-Class` và `Class-Path` vào manifest, đồng thời có task `<manifestclasspath>` để tính đường dẫn tương đối tới các thư viện. Cách đóng gói này giữ dependency thành các tệp riêng, dễ cập nhật và tránh phải giải nén JAR lồng bên trong JAR khi chạy.

## 1. JAR thực thi cần những gì?

Một JAR thông thường chỉ là archive chứa class và resource. Để chạy bằng `java -jar`, manifest của JAR cần khai báo lớp có phương thức `main` thông qua thuộc tính `Main-Class`.

Ví dụ manifest tối thiểu:

```text
Manifest-Version: 1.0
Main-Class: com.example.inventory.Main
```

`Main-Class` là tên lớp đầy đủ, có package, không có phần mở rộng `.class`. Lớp được chỉ định cần có phương thức entry point phù hợp, thường là:

```java
package com.example.inventory;

public class Main {
    public static void main(String[] args) {
        System.out.println("Inventory application started");
    }
}
```

Nếu manifest không có `Main-Class`, lệnh `java -jar application.jar` sẽ báo không có main manifest attribute. Nếu khai báo sai tên lớp hoặc thiếu lớp đó trong JAR, JVM không thể khởi chạy ứng dụng.

## 2. Vì sao cần khai báo `Class-Path`?

Giả sử ứng dụng dùng thư viện JSON và logging. Các lớp của ứng dụng nằm trong `inventory-app.jar`, còn thư viện được phân phối riêng:

```text
dist/
├── inventory-app.jar
└── lib/
    ├── jackson-core-2.17.2.jar
    ├── jackson-databind-2.17.2.jar
    ├── jackson-annotations-2.17.2.jar
    └── slf4j-api-2.0.16.jar
```

Nếu manifest chỉ có `Main-Class`, JVM biết lớp bắt đầu nhưng không tự động tìm mọi JAR trong thư mục `lib`. Ứng dụng có thể khởi động rồi gặp `ClassNotFoundException` hoặc `NoClassDefFoundError` khi cần lớp thuộc dependency.

Thêm thuộc tính `Class-Path` vào manifest:

```text
Manifest-Version: 1.0
Main-Class: com.example.inventory.Main
Class-Path: lib/jackson-core-2.17.2.jar lib/jackson-databind-2.17.2.jar lib/jackson-annotations-2.17.2.jar lib/slf4j-api-2.0.16.jar
```

Khi chạy:

```sh
java -jar inventory-app.jar
```

JVM sử dụng JAR chính và các URL được liệt kê trong manifest để tìm lớp và resource. Các JAR bên ngoài vẫn là những tệp riêng trong `dist/lib`; chúng không được nhúng vào JAR chính.

## 3. Quy tắc của manifest `Class-Path`

`Class-Path` trong manifest có quy tắc khác với tham số `-cp` của dòng lệnh:

- Giá trị là danh sách URL, mỗi entry được phân cách bằng một hoặc nhiều dấu cách.
- Entry tương đối được phân giải tương đối với URL của JAR chứa manifest.
- Entry tới JAR thường là URL tới tệp JAR; entry tới thư mục cần kết thúc bằng dấu `/`.
- Đây không phải chuỗi classpath theo cú pháp hệ điều hành. Không dùng dấu `;` trên Windows hoặc dấu `:` trên Linux/macOS để phân cách các entry manifest.
- Các entry phải xác định được vị trí của thư viện khi ứng dụng được triển khai.
- Manifest `Class-Path` không hỗ trợ wildcard theo kiểu `lib/*`; cần liệt kê từng JAR cụ thể.

Ví dụ, với JAR chính ở `dist/inventory-app.jar`, entry:

```text
Class-Path: lib/jackson-core-2.17.2.jar lib/slf4j-api-2.0.16.jar
```

được phân giải thành các vị trí bên dưới `dist/lib`. Nếu di chuyển JAR chính sang một thư mục khác mà không di chuyển thư mục `lib` theo cùng cấu trúc tương đối, các dependency sẽ không còn ở vị trí được khai báo.

Một entry URL tuyệt đối cũng có thể được biểu diễn theo quy tắc URL, nhưng hard-code đường dẫn của một máy như `C:\Users\...` hoặc `/home/alice/...` khiến gói không di động. Với ứng dụng phân phối cho nhiều máy, hãy ưu tiên layout tương đối nằm trong cùng thư mục phát hành.

## 4. Phân biệt `Class-Path` trong manifest với `-cp` và `-jar`

| Cách chạy | Nguồn classpath của ứng dụng | Cách chọn lớp main |
|---|---|---|
| `java -cp "app.jar;lib/*" com.example.Main` trên Windows | Classpath được truyền bằng `-cp` | Tên lớp được ghi rõ trên dòng lệnh |
| `java -cp "app.jar:lib/*" com.example.Main` trên Linux/macOS | Classpath được truyền bằng `-cp` | Tên lớp được ghi rõ trên dòng lệnh |
| `java -jar app.jar` | JAR chính và các entry trong manifest `Class-Path` | Manifest `Main-Class` |

Khi dùng `-jar`, các thiết lập classpath khác trên dòng lệnh bị bỏ qua đối với user classpath; manifest của executable JAR là nơi khai báo dependency đi kèm. Vì vậy, không nên kỳ vọng `java -jar app.jar -cp lib/*` sẽ bổ sung classpath như khi dùng chế độ gọi lớp trực tiếp.

Wildcard như `lib/*` được hỗ trợ trong classpath dòng lệnh theo quy tắc Java, nhưng không phải cú pháp hợp lệ để thay thế danh sách URL trong manifest `Class-Path`. Nếu dùng manifest, hãy ghi rõ từng dependency.

## 5. Đóng gói bằng Ant task `<jar>`

Ant có thể tạo JAR từ thư mục bytecode và ghi manifest bằng nested element `<manifest>`:

```xml
<jar destfile="dist/inventory-app.jar" basedir="build/classes">
    <manifest>
        <attribute name="Main-Class" value="com.example.inventory.Main"/>
    </manifest>
</jar>
```

`basedir` chỉ định thư mục có nội dung đưa vào JAR. Ant giữ cấu trúc thư mục bên dưới `build/classes`, vì vậy lớp `com.example.inventory.Main` được lưu tại `com/example/inventory/Main.class` trong archive.

Nếu ứng dụng cần tài nguyên như tệp `.properties`, có thể đưa thêm bằng `fileset`:

```xml
<jar destfile="dist/inventory-app.jar" basedir="build/classes">
    <fileset dir="src/main/resources"/>
    <manifest>
        <attribute name="Main-Class" value="com.example.inventory.Main"/>
    </manifest>
</jar>
```

Hãy bảo đảm các tài nguyên không ghi đè nhầm class hoặc resource khác trong archive. Có thể giới hạn fileset bằng `includes` và `excludes` nếu thư mục nguồn có nhiều loại tệp không cần đóng gói.

## 6. Thêm thư viện bên ngoài vào thư mục phát hành

Trước khi tạo manifest, cần sao chép các JAR dependency tới vị trí sẽ có trong gói phát hành. Ví dụ:

```xml
<property name="dist.dir" location="dist"/>
<property name="lib.dir" location="lib"/>

<target name="prepare-distribution">
    <mkdir dir="${dist.dir}/lib"/>
    <copy todir="${dist.dir}/lib">
        <fileset dir="${lib.dir}">
            <include name="jackson-core-2.17.2.jar"/>
            <include name="jackson-databind-2.17.2.jar"/>
            <include name="jackson-annotations-2.17.2.jar"/>
            <include name="slf4j-api-2.0.16.jar"/>
        </fileset>
    </copy>
</target>
```

Nếu dự án quản lý JAR trong các nhóm compile/runtime riêng, chỉ sao chép những dependency cần cho runtime vào gói phát hành. Không nên sao chép JUnit, compiler plugin hoặc công cụ build vào runtime nếu ứng dụng không cần chúng.

## 7. Tự tính đường dẫn manifest bằng `<manifestclasspath>`

Viết thủ công một danh sách `Class-Path` dài dễ sai khi thay đổi thư viện hoặc di chuyển thư mục. Ant cung cấp task `<manifestclasspath>` để chuyển một `Path` thành danh sách URL tương đối với vị trí JAR.

Ví dụ, sau khi copy dependency vào `dist/lib`, tạo path từ đúng vị trí triển khai:

```xml
<path id="runtime.dependencies">
    <fileset dir="dist/lib" includes="*.jar"/>
</path>

<manifestclasspath property="manifest.classpath"
                   jarfile="dist/inventory-app.jar">
    <classpath refid="runtime.dependencies"/>
</manifestclasspath>
```

Property `manifest.classpath` chứa danh sách entry được tính tương đối từ `dist/inventory-app.jar` tới các JAR trong `dist/lib`. Dùng property này khi tạo manifest:

```xml
<jar destfile="dist/inventory-app.jar" basedir="build/classes">
    <manifest>
        <attribute name="Main-Class" value="com.example.inventory.Main"/>
        <attribute name="Class-Path" value="${manifest.classpath}"/>
    </manifest>
</jar>
```

Điểm quan trọng là path đầu vào của `<manifestclasspath>` phải mô tả vị trí cuối cùng của các thư viện trong gói. Nếu tính path dựa trên `lib/` ở thư mục dự án nhưng khi phát hành lại copy chúng sang `dist/lib`, đường dẫn tương đối có thể không trỏ đúng vị trí sau khi triển khai.

`<manifestclasspath>` cũng giúp xử lý việc tạo URL tương đối và các chi tiết path thay vì tự nối chuỗi. Nếu dependency nằm quá xa bên ngoài thư mục phát hành hoặc ở ổ đĩa khác, task có thể không tạo được một đường dẫn tương đối phù hợp theo cấu hình giới hạn cấp thư mục. Nên tổ chức gói để JAR chính và dependency nằm trong một cây thư mục ổn định.

## 8. Buildfile hoàn chỉnh: JAR chính và thư mục `lib`

Ví dụ sau biên dịch ứng dụng, copy dependency runtime, tính `Class-Path` và tạo executable JAR:

```xml
<project name="inventory-app" default="package" basedir=".">

    <property name="src.dir" location="src/main/java"/>
    <property name="resources.dir" location="src/main/resources"/>
    <property name="classes.dir" location="build/classes"/>
    <property name="lib.dir" location="lib"/>
    <property name="dist.dir" location="dist"/>
    <property name="dist.jar" location="${dist.dir}/inventory-app.jar"/>
    <property name="main.class" value="com.example.inventory.Main"/>

    <path id="compile.classpath">
        <fileset dir="${lib.dir}" includes="*.jar"/>
    </path>

    <target name="clean">
        <delete dir="build"/>
        <delete dir="${dist.dir}"/>
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}"/>
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath"/>
        </javac>
        <copy todir="${classes.dir}">
            <fileset dir="${resources.dir}"/>
        </copy>
    </target>

    <target name="copy-runtime-libraries" depends="compile">
        <mkdir dir="${dist.dir}/lib"/>
        <copy todir="${dist.dir}/lib">
            <fileset dir="${lib.dir}" includes="*.jar"/>
        </copy>
    </target>

    <target name="package" depends="copy-runtime-libraries">
        <path id="runtime.dependencies">
            <fileset dir="${dist.dir}/lib" includes="*.jar"/>
        </path>

        <manifestclasspath property="manifest.classpath"
                           jarfile="${dist.jar}">
            <classpath refid="runtime.dependencies"/>
        </manifestclasspath>

        <jar destfile="${dist.jar}" basedir="${classes.dir}">
            <manifest>
                <attribute name="Main-Class" value="${main.class}"/>
                <attribute name="Class-Path" value="${manifest.classpath}"/>
            </manifest>
        </jar>
    </target>

</project>
```

Chạy build:

```sh
ant clean package
```

Sau khi build, cấu trúc phát hành dự kiến:

```text
dist/
├── inventory-app.jar
└── lib/
    ├── jackson-core-2.17.2.jar
    ├── jackson-databind-2.17.2.jar
    ├── jackson-annotations-2.17.2.jar
    └── slf4j-api-2.0.16.jar
```

Chạy từ thư mục `dist`:

```sh
java -jar inventory-app.jar
```

Hoặc từ thư mục gốc dự án:

```sh
java -jar dist/inventory-app.jar
```

JVM đọc manifest trong JAR và phân giải các entry tương đối từ vị trí của `inventory-app.jar`, nên thư mục `lib` phải nằm cạnh JAR theo layout đã đóng gói.

Ví dụ trên dùng tất cả JAR trong thư mục `lib`. Nếu thư mục có dependency chỉ dành cho test hoặc build, hãy thu hẹp FileSet để chỉ copy các JAR runtime.

## 9. Giới hạn độ dài dòng trong manifest

Manifest JAR có quy tắc định dạng riêng: mỗi dòng vật lý được giới hạn tối đa 72 byte. Nếu giá trị của một thuộc tính dài hơn, dòng cần được gấp (fold) thành nhiều dòng. Dòng tiếp nối bắt đầu bằng một dấu cách ở đầu dòng.

Ví dụ minh họa cách gấp dòng:

```text
Class-Path: lib/very-long-library-name-1.0.0.jar lib/another-library-2.0.
 0.jar lib/third-library-3.1.4.jar
```

Dấu cách ở đầu dòng thứ hai là ký hiệu continuation. Khi đọc manifest, parser nối dòng tiếp nối vào giá trị của thuộc tính. Dấu cách đó không phải một phần của tên file theo cách thông thường.

Giới hạn 72 byte áp dụng cho dòng vật lý, không phải giới hạn tổng chiều dài của toàn bộ thuộc tính `Class-Path`. Một classpath có nhiều dependency vẫn có thể biểu diễn bằng nhiều dòng tiếp nối hợp lệ.

Không nên tự cắt chuỗi `Class-Path` ở một vị trí bất kỳ hoặc xuống dòng mà không thêm dấu cách continuation. Cách làm đó có thể khiến manifest sai cú pháp hoặc tên JAR bị tách không đúng.

Khi dùng nested `<manifest>` trong Ant, task `<jar>` tạo manifest và xử lý việc gấp dòng theo định dạng manifest. Khi cần tự tạo manifest file, hãy tuân theo đặc tả manifest và kiểm tra kết quả bằng cách giải nén `META-INF/MANIFEST.MF` từ JAR.

## 10. Giới hạn của URL và tên đường dẫn

Manifest `Class-Path` chứa URL, không phải chuỗi đường dẫn tùy ý. Một số lưu ý quan trọng:

- Dùng dấu `/` trong URL path, kể cả khi gói được tạo trên Windows.
- Khoảng trắng trong URL cần được mã hóa thành `%20`; không để khoảng trắng thô làm tách entry.
- Ký tự đặc biệt trong URL cần được percent-encode theo quy tắc URL.
- Entry thư mục phải kết thúc bằng `/` để biểu thị URL tới thư mục.
- Entry JAR cần trỏ tới đúng file và đúng vị trí tương đối.
- Tránh đường dẫn tuyệt đối gắn với máy phát triển.
- Tránh `../` vượt ra ngoài cấu trúc gói phát hành nếu có thể tổ chức dependency bên dưới `dist/lib`.

Ví dụ nếu JAR được đặt tại `dist/inventory-app.jar`, URL `lib/logging%20api.jar` trỏ tới tệp `dist/lib/logging api.jar`. Nếu tự tạo manifest, hãy kiểm tra cách mã hóa đường dẫn và tên file; `<manifestclasspath>` giúp giảm nguy cơ tạo URL sai.

Một đường dẫn tương đối chỉ hoạt động khi cấu trúc triển khai được giữ nguyên. Vì thế, nên xem JAR chính và thư mục dependency như một đơn vị phát hành: copy hoặc giải nén cả cây `dist`, không chỉ lấy riêng file JAR.

## 11. Manifest `Class-Path` không nhúng JAR bên trong JAR

Một nhầm lẫn phổ biến là nghĩ rằng chỉ cần copy dependency vào thư mục `lib` rồi đặt thư mục đó bên trong `inventory-app.jar` là JVM tự tìm được các JAR con.

Manifest `Class-Path` tham chiếu tới URL của tài nguyên bên ngoài theo vị trí được khai báo. Nó không tự mở một JAR bên trong archive khác để nạp những JAR lồng đó.

Ví dụ cấu trúc không đủ để chạy dependency:

```text
inventory-app.jar
└── lib/
    └── jackson-databind.jar
```

JVM không tự coi `lib/jackson-databind.jar` bên trong archive là một classpath entry độc lập. Nếu muốn phân phối dependency bên ngoài, hãy giữ chúng thành file thật trong `dist/lib`. Nếu muốn tạo một fat JAR (JAR gộp class/resource của dependency), cần một quy trình đóng gói riêng để hợp nhất nội dung và xử lý metadata, service descriptors, license, chữ ký và các file trùng tên.

## 12. `java -jar` và các tham số classpath khác

Khi khởi chạy executable JAR:

```sh
java -jar dist/inventory-app.jar
```

JVM dùng `Main-Class` để tìm entry point và manifest `Class-Path` để bổ sung các URL dependency. Không thể dùng đồng thời `-jar` và kỳ vọng `-cp` hoặc biến môi trường `CLASSPATH` ghi đè danh sách đó cho user classpath.

Nếu muốn tự chỉ định classpath từ dòng lệnh, hãy gọi tên lớp trực tiếp:

```sh
java -cp "dist/inventory-app.jar;dist/lib/*" com.example.inventory.Main
```

Trên Linux/macOS:

```sh
java -cp "dist/inventory-app.jar:dist/lib/*" com.example.inventory.Main
```

Đây là một cách chạy khác với `java -jar`. Nó hữu ích khi cần dùng wildcard hoặc điều khiển classpath từ script, nhưng người chạy phải biết tên lớp main và cú pháp path của hệ điều hành.

## 13. Manifest và modulepath

Manifest `Class-Path` phục vụ cơ chế classpath truyền thống. Nó không thay thế `--module-path` và không khai báo quan hệ `requires`, `exports` hoặc `opens` của JPMS.

Nếu ứng dụng là module Java có `module-info.class`, cần phân biệt cách chạy module bằng `java -m`/`--module-path` với cách chạy executable JAR trên classpath. Không nên kỳ vọng `Class-Path` giải quyết các module dependency hoặc ranh giới truy cập của module system.

Khi đóng gói ứng dụng modular, hãy chọn chiến lược phát hành phù hợp: module path với module descriptor, runtime image bằng `jlink` nếu cần, hoặc một dạng đóng gói classpath truyền thống nếu ứng dụng được thiết kế theo cách đó.

## 14. Kiểm tra manifest và cấu trúc gói

Sau khi tạo JAR, có thể kiểm tra nội dung archive:

```sh
jar tf dist/inventory-app.jar
```

Để xem manifest, có thể dùng:

```sh
jar xf dist/inventory-app.jar META-INF/MANIFEST.MF
```

Lệnh này giải nén riêng manifest vào thư mục làm việc hiện tại. Mở `META-INF/MANIFEST.MF` và xác nhận:

- Có `Main-Class` đúng tên lớp.
- Có `Class-Path` nếu ứng dụng dùng dependency bên ngoài.
- Các entry trong `Class-Path` dùng dấu cách phân cách, không dùng dấu phân cách hệ điều hành.
- Các dòng dài được gấp đúng định dạng continuation.
- Mỗi entry trỏ tới một file hoặc thư mục thực sự tồn tại trong gói phát hành.

Kiểm tra trực tiếp bằng cách chạy:

```sh
java -jar dist/inventory-app.jar
```

Nên thử sau khi copy toàn bộ thư mục `dist` sang một vị trí khác hoặc máy sạch. Nếu chỉ chạy trong workspace của developer, ứng dụng có thể vô tình tìm thấy thư viện từ classpath hoặc thư mục khác ngoài gói phát hành.

## 15. Lỗi thường gặp và cách xử lý

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| `no main manifest attribute` | Manifest thiếu `Main-Class` | Thêm `Main-Class` trong nested `<manifest>` của task `<jar>` |
| Không tìm thấy lớp main | Tên lớp sai hoặc lớp không được đưa vào JAR | Kiểm tra fully qualified class name và nội dung archive |
| `ClassNotFoundException` hoặc `NoClassDefFoundError` | Dependency chưa có trong `Class-Path` hoặc JAR không nằm đúng vị trí | Kiểm tra manifest và layout `dist/lib` |
| Chạy bằng `java -cp` được nhưng `java -jar` lỗi | Classpath dòng lệnh có thêm dependency mà manifest chưa khai báo | Bổ sung entry tương ứng vào manifest hoặc dùng `<manifestclasspath>` |
| Dependency không được tìm thấy sau khi di chuyển gói | Entry tương đối được tính từ vị trí JAR nhưng layout đã thay đổi | Phân phối nguyên cây thư mục và giữ `lib` cạnh JAR |
| Manifest có nhiều dependency nhưng chỉ một số được nạp | Entry sai URL, file thiếu hoặc tên có khoảng trắng chưa được mã hóa | Kiểm tra từng URL, percent-encode ký tự đặc biệt và xác minh file tồn tại |
| Manifest bị lỗi khi classpath dài | Tự xuống dòng hoặc tạo dòng vượt quy tắc manifest | Dùng Ant `<manifest>`/`<manifestclasspath>` để tạo và gấp dòng đúng định dạng |
| Wildcard `lib/*` không hoạt động trong manifest | Manifest `Class-Path` không dùng wildcard classpath của Java launcher | Liệt kê từng JAR bằng `<manifestclasspath>` hoặc tạo danh sách cụ thể |
| JAR trong `lib` đã được nhúng vào JAR chính nhưng JVM vẫn không tìm thấy | JVM không tự nạp JAR lồng bên trong archive | Giữ dependency thành file ngoài hoặc dùng quy trình tạo fat JAR phù hợp |
| Đường dẫn hoạt động trên máy build nhưng không hoạt động ở máy khác | Manifest chứa đường dẫn tuyệt đối hoặc dependency ngoài cây phát hành | Dùng layout tương đối và kiểm thử gói trên máy sạch |

## 16. Checklist tạo executable JAR có dependency ngoài

- [ ] Lớp main tồn tại và có phương thức `public static void main(String[] args)`.
- [ ] Manifest khai báo `Main-Class` bằng tên đầy đủ của lớp.
- [ ] Các dependency runtime được copy vào thư mục phát hành, ví dụ `dist/lib`.
- [ ] Manifest `Class-Path` liệt kê từng JAR bên ngoài bằng URL hợp lệ.
- [ ] Các đường dẫn được tính tương đối từ vị trí của JAR chính.
- [ ] Không dùng wildcard `lib/*` trong manifest.
- [ ] Không nhầm classpath manifest với dấu phân cách path của hệ điều hành.
- [ ] Các đường dẫn có khoảng trắng và ký tự đặc biệt được mã hóa đúng.
- [ ] Dòng manifest dài được gấp đúng quy tắc 72 byte và continuation.
- [ ] JAR chính không được kỳ vọng tự nạp JAR lồng bên trong.
- [ ] Đã kiểm tra `META-INF/MANIFEST.MF` và chạy thử bằng `java -jar`.
- [ ] Đã kiểm thử toàn bộ cây phát hành sau khi di chuyển sang vị trí hoặc máy khác.

## 17. Kết luận

Một executable JAR có thể chạy cùng các thư viện bên ngoài bằng cách khai báo `Main-Class` và `Class-Path` trong manifest. Ant task `<jar>` tạo archive và manifest; `<manifestclasspath>` tính danh sách URL tương đối tới dependency. Để gói phát hành hoạt động ổn định, hãy đặt JAR chính và thư mục `lib` trong một cấu trúc cố định, liệt kê từng dependency, tuân thủ định dạng URL và giới hạn dòng manifest, rồi kiểm tra bằng chính lệnh `java -jar` trên gói đã triển khai.
