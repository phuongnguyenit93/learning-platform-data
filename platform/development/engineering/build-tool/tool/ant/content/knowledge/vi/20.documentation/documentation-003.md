# Đóng gói source JAR và Javadoc JAR

Một thư viện Java thường phát hành nhiều hơn một file JAR. Bên cạnh JAR chứa bytecode để ứng dụng khác sử dụng, dự án có thể phát hành thêm **source JAR** chứa mã nguồn `.java` và **Javadoc JAR** chứa tài liệu API đã sinh thành HTML.

Hai artifact bổ sung này phục vụ những nhu cầu khác nhau:

- Source JAR giúp lập trình viên xem mã nguồn thư viện ngay trong IDE, lần theo cách triển khai và debug.
- Javadoc JAR cung cấp tài liệu API đã render, giúp người dùng tra cứu lớp, phương thức, tham số, giá trị trả về và ngoại lệ mà không cần tự chạy Javadoc.

Apache Ant có thể tạo source JAR bằng task `<jar>` với một `fileset`, sinh tài liệu HTML bằng task `<javadoc>`, rồi đóng gói thư mục tài liệu thành Javadoc JAR bằng một task `<jar>` khác.

## 1. Phân biệt ba artifact

Giả sử dự án phát hành thư viện `catalog-core` phiên bản `1.4.0`. Ba artifact thường có tên:

```text
catalog-core-1.4.0.jar
catalog-core-1.4.0-sources.jar
catalog-core-1.4.0-javadoc.jar
```

| Artifact | Nội dung | Mục đích |
|---|---|---|
| Binary JAR | File `.class`, resource runtime và manifest | Được JVM nạp khi ứng dụng chạy |
| Source JAR | File `.java`, có thể kèm resource liên quan | Xem source, debug và điều hướng từ IDE |
| Javadoc JAR | HTML, CSS, JavaScript và các file hỗ trợ do Javadoc tạo | Tra cứu tài liệu API đã render |

Source JAR không phải Javadoc JAR. Source JAR giữ nguyên mã nguồn và comment trong file Java. Javadoc JAR chứa trang HTML được tạo từ các comment có cấu trúc và thông tin kiểu dữ liệu của mã nguồn.

Ant không bắt buộc quy ước tên `-sources.jar` hoặc `-javadoc.jar`; đây là quy ước phổ biến của hệ sinh thái Java và repository Maven. Nếu phát hành thủ công, nên dùng tên nhất quán để người dùng và IDE dễ nhận biết.

## 2. Chuẩn bị cấu trúc source

Ví dụ dùng cấu trúc dự án:

```text
catalog-core/
├── build.xml
├── src/
│   └── main/
│       ├── java/
│       │   └── com/example/catalog/
│       │       ├── Catalog.java
│       │       └── CatalogEntry.java
│       └── resources/
│           └── catalog-defaults.properties
├── lib/
├── build/
│   ├── classes/
│   └── javadoc/
└── dist/
```

`src/main/java` chứa source Java. `src/main/resources` chứa tài nguyên ứng dụng. `build/classes` là output biên dịch. `build/javadoc` là nơi task Javadoc tạo HTML. `dist` chứa các artifact phát hành.

Tách output khỏi source giúp target `clean` xóa được sản phẩm sinh ra mà không ảnh hưởng mã nguồn. Khi tạo source JAR, hãy lấy file từ thư mục source, không lấy file `.class` trong `build/classes`.

## 3. Viết JavaDoc comment trong mã nguồn

Task `<javadoc>` dùng công cụ Javadoc của JDK để đọc source và tạo tài liệu API. Các comment thông thường bắt đầu bằng `//` hoặc `/* ... */` không tự động trở thành tài liệu API. JavaDoc comment có dạng `/** ... */` và thường đặt ngay trước khai báo package, class, constructor hoặc method cần mô tả.

Ví dụ `CatalogEntry.java`:

```java
package com.example.catalog;

/**
 * Represents an item stored in a catalog.
 *
 * <p>An entry has a stable identifier and a display name.</p>
 *
 * @since 1.0
 */
public class CatalogEntry {

    private final String id;
    private final String name;

    /**
     * Creates a catalog entry.
     *
     * @param id stable identifier; must not be {@code null}
     * @param name display name; must not be {@code null}
     */
    public CatalogEntry(String id, String name) {
        this.id = id;
        this.name = name;
    }

    /**
     * Returns the stable identifier.
     *
     * @return the entry identifier
     */
    public String getId() {
        return id;
    }

    /**
     * Returns the display name.
     *
     * @return the display name
     */
    public String getName() {
        return name;
    }
}
```

Ví dụ `Catalog.java`:

```java
package com.example.catalog;

import java.util.Collection;
import java.util.Optional;

/**
 * Provides lookup operations for catalog entries.
 *
 * @since 1.0
 */
public interface Catalog {

    /**
     * Finds an entry by its identifier.
     *
     * @param id identifier to search for
     * @return an optional entry; empty when no entry matches
     */
    Optional<CatalogEntry> findById(String id);

    /**
     * Returns all entries currently available in this catalog.
     *
     * @return the catalog entries
     */
    Collection<CatalogEntry> findAll();
}
```

Một số tag JavaDoc quan trọng:

| Tag | Dùng để mô tả |
|---|---|
| `@param` | Tham số của constructor hoặc method |
| `@return` | Giá trị trả về của method |
| `@throws` hoặc `@exception` | Ngoại lệ mà method có thể ném |
| `@since` | Phiên bản API bắt đầu có thành phần này |
| `@deprecated` | API không còn được khuyến nghị sử dụng |
| `@see` | Tham chiếu đến API hoặc tài liệu liên quan |
| `{@link ...}` | Liên kết đến kiểu hoặc thành phần API khác |
| `{@code ...}` | Hiển thị đoạn mã inline |

Comment nên mô tả hợp đồng mà người dùng API cần hiểu: ý nghĩa tham số, điều kiện đầu vào, giá trị trả về và ngoại lệ. Không nên chỉ lặp lại tên method bằng một câu khác.

## 4. Tạo source JAR bằng task jar

Source JAR là một archive chứa source file theo đúng cấu trúc package. Có thể dùng task `<jar>` và một `fileset` trỏ đến `src/main/java`:

```xml
<target name="sources-jar">
    <mkdir dir="dist"/>

    <jar destfile="dist/catalog-core-1.4.0-sources.jar">
        <fileset dir="src/main/java">
            <include name="**/*.java"/>
        </fileset>
    </jar>
</target>
```

Nếu source tree có:

```text
src/main/java/
└── com/example/catalog/
    ├── Catalog.java
    └── CatalogEntry.java
```

thì nội dung source JAR có đường dẫn tương ứng:

```text
com/example/catalog/Catalog.java
com/example/catalog/CatalogEntry.java
```

Giữ nguyên đường dẫn package là quan trọng. Không flatten tất cả file Java vào cùng thư mục, vì có thể có nhiều lớp cùng tên ở các package khác nhau và IDE cần cấu trúc đúng để liên kết source với binary JAR.

### 4.1. Đưa resource vào source JAR khi cần

Tùy quy ước dự án, source JAR có thể chứa resource đi cùng source:

```xml
<jar destfile="dist/catalog-core-1.4.0-sources.jar">
    <fileset dir="src/main/java">
        <include name="**/*.java"/>
    </fileset>
    <fileset dir="src/main/resources">
        <include name="**/*"/>
    </fileset>
</jar>
```

Không nhất thiết phải đưa mọi file trong `src/main/resources` vào source JAR. Chỉ thêm các file cần thiết để hiểu hoặc build source. Tránh đưa file cấu hình chứa mật khẩu, token hoặc thông tin môi trường riêng vào artifact phát hành.

## 5. Sinh tài liệu HTML bằng task javadoc

Task `<javadoc>` gọi công cụ Javadoc của JDK để tạo tài liệu HTML. Với package `com.example.catalog`, có thể viết:

```xml
<target name="javadoc">
    <mkdir dir="build/javadoc"/>

    <javadoc sourcepath="src/main/java"
             packagenames="com.example.catalog"
             destdir="build/javadoc"
             encoding="UTF-8"
             docencoding="UTF-8"
             charset="UTF-8"
             author="true"
             version="true"
             use="true"
             windowtitle="Catalog Core API"
             doctitle="Catalog Core API"
             failonerror="true">
        <link href="https://docs.oracle.com/en/java/javase/17/docs/api/"/>
    </javadoc>
</target>
```

Các thuộc tính chính:

| Thuộc tính | Vai trò |
|---|---|
| `sourcepath` | Thư mục gốc chứa cây package source |
| `packagenames` | Các package cần tạo tài liệu |
| `destdir` | Thư mục nhận HTML được tạo |
| `encoding` | Encoding của source file |
| `docencoding` | Encoding của file HTML được sinh |
| `charset` | Charset được khai báo trong HTML |
| `author` | Đưa thông tin `@author` vào tài liệu |
| `version` | Đưa thông tin `@version` vào tài liệu |
| `use` | Tạo trang sử dụng/API index bổ sung |
| `windowtitle` | Tiêu đề cửa sổ/trang trình duyệt |
| `doctitle` | Tiêu đề chính trên trang tài liệu |
| `failonerror` | Làm build thất bại khi Javadoc task báo lỗi |

Ví dụ chỉ định một package cụ thể để dễ hiểu. Với thư viện có nhiều package, hãy liệt kê các package cần tài liệu hoặc dùng wildcard theo cú pháp package pattern của Javadoc/Ant, ví dụ `com.example.catalog.*`. Có thể dùng nested `packageset` hoặc `fileset` nếu muốn chọn source linh hoạt hơn; kiểm tra cú pháp tương ứng với phiên bản Ant đang dùng.

### 5.1. Tham chiếu Javadoc của Java SE

Nested element `<link>` thêm liên kết đến tài liệu API bên ngoài. Ví dụ liên kết Java SE 17 giúp các kiểu như `String`, `List` hoặc `Optional` trở thành liên kết trong tài liệu được tạo.

```xml
<link href="https://docs.oracle.com/en/java/javase/17/docs/api/"/>
```

Liên kết ngoài hữu ích khi người đọc có kết nối mạng. Nếu build phải chạy hoàn toàn offline, hãy bỏ link ngoài hoặc dùng tài liệu API được lưu sẵn và cấu hình vị trí phù hợp. Không nên để một bước Javadoc phát hành phụ thuộc vào mạng nếu CI của dự án không bảo đảm truy cập Internet.

### 5.2. Thêm header, footer và nội dung tài liệu

Có thể thêm nội dung trình bày vào trang Javadoc:

```xml
<javadoc sourcepath="src/main/java"
         packagenames="com.example.catalog"
         destdir="build/javadoc"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8"
         failonerror="true">
    <doctitle><![CDATA[<h1>Catalog Core API</h1>]]></doctitle>
    <header><![CDATA[Catalog Core 1.4.0]]></header>
    <bottom><![CDATA[Copyright &copy; Example Organization]]></bottom>
</javadoc>
```

Các nội dung HTML được đưa vào tài liệu nên đơn giản, hợp lệ và không chứa script không đáng tin cậy. Với dự án cần branding hoặc layout phức tạp, có thể dùng stylesheet hoặc doclet tùy chỉnh, nhưng nên giữ tài liệu API dễ đọc và tương thích với công cụ xem Javadoc.

## 6. Đóng gói Javadoc JAR

Sau khi task `<javadoc>` tạo HTML trong `build/javadoc`, dùng `<jar>` đóng gói toàn bộ nội dung thư mục đó:

```xml
<target name="javadoc-jar" depends="javadoc">
    <mkdir dir="dist"/>

    <jar destfile="dist/catalog-core-1.4.0-javadoc.jar"
         basedir="build/javadoc"/>
</target>
```

Javadoc JAR cần giữ nguyên cấu trúc output do Javadoc tạo, bao gồm trang index, trang package/class, stylesheet, script và các file điều hướng mà phiên bản JDK sử dụng. Không chỉ đóng gói riêng `index.html`; nếu thiếu file hỗ trợ, tài liệu có thể mở được trang đầu nhưng các liên kết hoặc giao diện không hoạt động.

Có thể kiểm tra nội dung bằng lệnh JDK:

```bash
jar tf dist/catalog-core-1.4.0-javadoc.jar
```

Trong archive thường có `index.html`, các file CSS/JavaScript và thư mục package chứa trang class. Cấu trúc chính xác phụ thuộc phiên bản Javadoc.

## 7. Kết hợp source JAR và Javadoc JAR trong một build

Một build thường có target riêng cho binary JAR, source JAR và Javadoc JAR. Ví dụ dưới đây minh họa cách tổ chức các bước và tên artifact theo phiên bản.

```xml
<project name="catalog-core" default="release-docs" basedir=".">
    <property name="app.name" value="catalog-core"/>
    <property name="app.version" value="1.4.0"/>

    <property name="src.main" location="${basedir}/src/main/java"/>
    <property name="src.resources" location="${basedir}/src/main/resources"/>
    <property name="build.dir" location="${basedir}/build"/>
    <property name="classes.dir" location="${build.dir}/classes"/>
    <property name="javadoc.dir" location="${build.dir}/javadoc"/>
    <property name="dist.dir" location="${basedir}/dist"/>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${dist.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.main}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false"/>
        <copy todir="${classes.dir}">
            <fileset dir="${src.resources}">
                <include name="**/*"/>
            </fileset>
        </copy>
    </target>

    <target name="binary-jar" depends="compile">
        <jar destfile="${dist.dir}/${app.name}-${app.version}.jar"
             basedir="${classes.dir}"/>
    </target>

    <target name="sources-jar" depends="init">
        <jar destfile="${dist.dir}/${app.name}-${app.version}-sources.jar">
            <fileset dir="${src.main}">
                <include name="**/*.java"/>
            </fileset>
            <fileset dir="${src.resources}">
                <include name="**/*"/>
            </fileset>
        </jar>
    </target>

    <target name="javadoc" depends="compile">
        <mkdir dir="${javadoc.dir}"/>
        <javadoc sourcepath="${src.main}"
                 packagenames="com.example.catalog"
                 destdir="${javadoc.dir}"
                 encoding="UTF-8"
                 docencoding="UTF-8"
                 charset="UTF-8"
                 author="true"
                 version="true"
                 use="true"
                 windowtitle="Catalog Core API"
                 doctitle="Catalog Core API"
                 failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}"/>
            </classpath>
            <link href="https://docs.oracle.com/en/java/javase/17/docs/api/"/>
        </javadoc>
    </target>

    <target name="javadoc-jar" depends="javadoc">
        <jar destfile="${dist.dir}/${app.name}-${app.version}-javadoc.jar"
             basedir="${javadoc.dir}"/>
    </target>

    <target name="release-docs" depends="binary-jar,sources-jar,javadoc-jar">
        <echo message="Binary, source and Javadoc artifacts are ready in ${dist.dir}."/>
    </target>

    <target name="clean">
        <delete dir="${build.dir}"/>
        <delete dir="${dist.dir}"/>
    </target>
</project>
```

Ví dụ giả định source có package `com.example.catalog` và các thư mục resource đã tồn tại. Nếu dự án có thêm package con, cập nhật cấu hình `packagenames` hoặc chọn source package theo cấu trúc thực tế. Nếu không có resource, bỏ phần `<copy>` và fileset tương ứng.

### 7.1. Đọc đồ thị target

```text
release-docs
  ├── binary-jar
  │     └── compile
  │           └── init
  ├── sources-jar
  │     └── init
  └── javadoc-jar
        └── javadoc
              └── compile
                    └── init

clean
```

Khi gọi `ant release-docs`, Ant thực hiện các dependency trước. Target `init` và `compile` được chia sẻ nên không chạy lặp lại trong cùng một lần gọi target. Sau đó binary JAR, source JAR và Javadoc JAR được tạo trong `dist`.

Source JAR không cần dùng bytecode đã compile để lấy `.java`, nhưng target ví dụ vẫn phụ thuộc `init` để đảm bảo thư mục đầu ra tồn tại. Javadoc phụ thuộc `compile` trong ví dụ vì classpath có thể cần các class đã biên dịch hoặc dependency của dự án.

## 8. Kiểm tra nội dung hai archive

Sau khi chạy:

```bash
ant clean release-docs
```

thư mục `dist` dự kiến có:

```text
dist/
├── catalog-core-1.4.0.jar
├── catalog-core-1.4.0-sources.jar
└── catalog-core-1.4.0-javadoc.jar
```

Kiểm tra source JAR:

```bash
jar tf dist/catalog-core-1.4.0-sources.jar
```

Kết quả cần có các đường dẫn source như `com/example/catalog/Catalog.java`. Nếu chỉ thấy `.class`, có thể task đã trỏ nhầm sang thư mục build output.

Kiểm tra Javadoc JAR:

```bash
jar tf dist/catalog-core-1.4.0-javadoc.jar
```

Kết quả cần có `index.html` và các file tài liệu được tạo. Có thể giải nén archive vào thư mục tạm rồi mở `index.html` bằng trình duyệt để xem các liên kết class/package và stylesheet.

## 9. Kiểm tra chất lượng JavaDoc và xử lý warning

Javadoc chỉ tạo tài liệu có ích khi source có comment đủ ý nghĩa. Một số điểm nên chú ý:

- Public class và public/protected method cần mô tả rõ vai trò.
- Method có tham số cần mô tả từng tham số bằng `@param`.
- Method có giá trị trả về cần mô tả `@return`.
- Method khai báo checked exception nên mô tả `@throws`.
- Liên kết `{@link ...}` cần trỏ đến kiểu hoặc thành phần hợp lệ.
- Đoạn HTML trong comment phải hợp lệ theo phiên bản Javadoc đang dùng.
- Với generic, overload và package con, kiểm tra tài liệu sinh ra có thể điều hướng đúng.

JDK mới có thể chạy doclint để phát hiện một số lỗi trong JavaDoc, ví dụ tag thiếu hoặc HTML không hợp lệ. Warning không phải lúc nào cũng làm task thất bại; hành vi phụ thuộc tùy chọn Javadoc và `failonerror`. Nếu dự án muốn warning trở thành lỗi, có thể cấu hình thêm tùy chọn Javadoc phù hợp với JDK, chẳng hạn `-Werror` khi công cụ hỗ trợ.

Khi cần thêm tham số Javadoc không được task Ant biểu diễn trực tiếp bằng attribute, dùng nested `<arg>`:

```xml
<javadoc sourcepath="src/main/java"
         packagenames="com.example.catalog"
         destdir="build/javadoc"
         failonerror="true">
    <arg value="-Xdoclint:all"/>
</javadoc>
```

Các tùy chọn phụ thuộc phiên bản JDK. Trước khi bật trong CI, hãy chạy trên cùng JDK mục tiêu và xử lý warning hiện có để build không thất bại bất ngờ.

## 10. Chọn source và package cần tạo tài liệu

Với một thư viện lớn, không phải mọi source đều cần xuất hiện trong tài liệu công khai. Có thể giới hạn package được tạo Javadoc bằng `packagenames` hoặc cấu hình các tập package/source phù hợp.

Ví dụ chỉ tạo tài liệu cho API công khai trong hai package:

```xml
<javadoc sourcepath="src/main/java"
         packagenames="com.example.catalog,com.example.catalog.spi"
         destdir="build/javadoc"
         access="public"
         encoding="UTF-8"
         docencoding="UTF-8"
         failonerror="true"/>
```

Thuộc tính `access` giới hạn mức truy cập được đưa vào tài liệu, chẳng hạn `public`, `protected`, `package` hoặc `private`. Với thư viện phát hành, `public` thường là lựa chọn phù hợp để tài liệu phản ánh API người dùng được hỗ trợ. Nếu tài liệu nội bộ cần cả protected/package-private API, hãy cân nhắc phạm vi khác và kiểm soát quyền truy cập tài liệu.

Javadoc cũng có thể tạo tài liệu package từ `package-info.java`. File này hữu ích để mô tả mục đích, quy ước và trách nhiệm chung của package.

Ví dụ:

```java
/**
 * Public API for reading and querying catalog entries.
 *
 * <p>Types in this package are intended for application developers.</p>
 */
package com.example.catalog;
```

## 11. Gắn source và Javadoc JAR với binary artifact

Tên artifact nên dùng cùng tên module và version để công cụ phát triển có thể nhận diện đúng bộ file. Ví dụ:

```text
catalog-core-1.4.0.jar
catalog-core-1.4.0-sources.jar
catalog-core-1.4.0-javadoc.jar
```

Trong Maven repository, source JAR và Javadoc JAR thường được gắn với cùng tọa độ artifact bằng classifier `sources` và `javadoc`. Ant chỉ tạo file archive; nếu dự án publish lên Maven-compatible repository, bước upload/metadata phải khai báo classifier đúng theo quy ước repository hoặc công cụ phát hành đang dùng.

Nếu chỉ phát hành file ZIP thủ công, nên đặt cả ba file cạnh nhau và cung cấp mô tả rõ binary, source và Javadoc. Người nhận cần biết ba file thuộc cùng phiên bản; không ghép binary JAR phiên bản này với source/Javadoc của phiên bản khác.

Có thể tạo checksum sau khi cả ba archive đã hoàn tất để người nhận kiểm tra tính toàn vẹn. Checksum phải được tính sau mọi bước có thể sửa artifact.

## 12. Lỗi thường gặp

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
|---|---|---|
| Source JAR không có file `.java` | Fileset trỏ nhầm `build/classes` hoặc include không khớp | Trỏ đến `src/main/java` và include `**/*.java` |
| Source JAR mất cấu trúc package | Dùng mapper/flatten làm thay đổi đường dẫn | Giữ đường dẫn tương đối trong source tree |
| Javadoc không tìm thấy package | `sourcepath` hoặc `packagenames` không khớp cấu trúc source | Kiểm tra package declaration và thư mục gốc source |
| Javadoc không resolve được kiểu từ dependency | Thiếu classpath cho task Javadoc | Thêm nested `<classpath>` chứa dependency cần thiết |
| Javadoc tạo trang nhưng thiếu liên kết Java SE | Thiếu nested `<link>` hoặc URL tài liệu sai | Cấu hình link đúng phiên bản API hoặc bỏ liên kết ngoài |
| Javadoc JAR thiếu CSS/JavaScript | Chỉ đóng gói `index.html` thay vì toàn bộ output | Dùng `<jar basedir="${javadoc.dir}"/>` |
| Build thất bại vì doclint | JavaDoc tag hoặc HTML comment không hợp lệ | Sửa comment, kiểm tra tùy chọn Javadoc và JDK mục tiêu |
| IDE không hiển thị source | Source JAR sai tên/cấu trúc hoặc không khớp binary version | Kiểm tra classifier, package path và phiên bản artifact |
| Javadoc link hỏng khi build offline | Javadoc cố truy cập tài liệu ngoài | Bỏ external link hoặc cung cấp tài liệu tham chiếu cục bộ |

## 13. Bài tập thực hành

1. Tạo một thư viện Java có ít nhất hai class trong package `com.example.catalog`.
2. Viết JavaDoc comment cho class, constructor và method; thêm `@param`, `@return`, `@throws` khi phù hợp.
3. Tạo target `sources-jar` dùng `<jar>` và `<fileset>` để đóng gói toàn bộ `.java`.
4. Chạy `jar tf` và xác nhận đường dẫn package được giữ nguyên.
5. Tạo target `javadoc` dùng `<javadoc>` với sourcepath, package name, encoding và destdir.
6. Mở `build/javadoc/index.html` và kiểm tra trang package/class.
7. Tạo target `javadoc-jar` đóng gói toàn bộ thư mục Javadoc.
8. Chạy `jar tf` và xác nhận archive có index, CSS/JavaScript và các trang API.
9. Tạo target tổng hợp để sinh binary JAR, source JAR và Javadoc JAR trong cùng một lần build.
10. Thử xóa một tag JavaDoc hoặc thêm HTML sai để quan sát warning/doclint của JDK.

Khi hoàn thành, người học cần giải thích được source JAR lấy file từ đâu, Javadoc JAR lấy file từ đâu, vì sao hai archive không thể thay thế nhau và cách Ant sắp xếp target để tạo cả hai artifact.

## 14. Nguyên tắc áp dụng trong dự án

Hãy coi binary JAR, source JAR và Javadoc JAR là ba sản phẩm liên quan của cùng một phiên bản phát hành. Source JAR phải giữ nguyên package path và chứa source cần thiết cho người dùng debug. Javadoc JAR phải đóng gói toàn bộ output do task `<javadoc>` tạo ra, không chỉ trang index. Dùng comment JavaDoc mô tả hợp đồng API và cấu hình encoding nhất quán.

Trong build Ant, tách target `sources-jar`, `javadoc` và `javadoc-jar` để mỗi bước có trách nhiệm rõ ràng. Một target phát hành tổng hợp có thể phụ thuộc vào cả binary và hai archive tài liệu. Nhờ vậy, mỗi lần release đều tạo ra bộ artifact đồng bộ, thuận tiện cho IDE, lập trình viên tích hợp và người vận hành repository.
