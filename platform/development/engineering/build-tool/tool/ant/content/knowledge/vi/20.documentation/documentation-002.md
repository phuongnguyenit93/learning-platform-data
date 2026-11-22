# Cấu hình nguồn, classpath, encoding và liên kết Javadoc trong Apache Ant

Apache Ant có task `javadoc` để tạo tài liệu API từ comment Javadoc trong mã nguồn Java. Một lần tạo tài liệu thành công cần tìm đúng source package, phân giải các kiểu dữ liệu mà source tham chiếu, đọc file `.java` bằng đúng encoding và tạo liên kết đến API bên ngoài. Nếu một trong các phần này cấu hình sai, tài liệu có thể thiếu package, báo không tìm thấy class, hiển thị sai tiếng Việt hoặc chứa liên kết không hoạt động.

Bốn phần cấu hình cần phân biệt là:

- `sourcepath`: nơi chứa mã nguồn Java cần tạo tài liệu.
- `classpath`: nơi chứa class và thư viện mà source tham chiếu đến.
- `encoding`, `docencoding`, `charset`: cách đọc source và cách ghi HTML Javadoc.
- `link` hoặc `linkoffline`: liên kết đến tài liệu API được tạo ở nơi khác, ví dụ Java SE API.

Task `javadoc` chỉ tạo tài liệu; nó không biên dịch source thành `.class`. Trong buildfile, thường chạy `compile` trước để có class output và dependency, rồi chạy `javadoc` với sourcepath và classpath tương ứng.

## 1. Javadoc lấy thông tin từ đâu?

Javadoc đọc source Java và các comment dạng `/** ... */` gắn với package, class, constructor, method hoặc field. Nó phân tích khai báo và kiểu dữ liệu để tạo trang HTML cho API.

Ví dụ:

```java
package com.example.inventory;

/**
 * Quản lý số lượng hàng trong kho.
 *
 * <p>Lớp này cung cấp các thao tác đọc và cập nhật tồn kho.</p>
 *
 * @since 1.0
 */
public class InventoryService {

    /**
     * Tính tổng số lượng sau khi nhập thêm hàng.
     *
     * @param current số lượng hiện tại
     * @param incoming số lượng nhập thêm
     * @return tổng số lượng sau khi nhập
     * @throws IllegalArgumentException nếu một trong hai số lượng âm
     */
    public int receive(int current, int incoming) {
        if (current < 0 || incoming < 0) {
            throw new IllegalArgumentException("Quantity must be non-negative");
        }
        return current + incoming;
    }
}
```

Javadoc lấy mô tả từ comment và thông tin cấu trúc từ source. Các tag như `@param`, `@return`, `@throws`, `@since`, `@deprecated` và inline tag `{@link ...}` giúp tài liệu có ngữ nghĩa và điều hướng rõ ràng.

## 2. Chọn source bằng `sourcepath` và package

`sourcepath` chỉ định một hoặc nhiều thư mục gốc chứa cây package Java. Nếu package là `com.example.inventory`, file thường nằm dưới:

```text
src/main/java/
└── com/
    └── example/
        └── inventory/
            └── InventoryService.java
```

Trong Ant, có thể khai báo `sourcepath` và danh sách package bằng thuộc tính `packagenames`:

```xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.inventory,com.example.catalog"/>
```

- `sourcepath` là thư mục gốc của cây source.
- `packagenames` là danh sách package cần tạo tài liệu, phân cách bằng dấu phẩy.
- `destdir` là thư mục nhận HTML được sinh ra.

Đường dẫn package phải khớp với cấu trúc thư mục và khai báo `package` trong source. Nếu source nằm ở `src/main/java` nhưng `sourcepath` lại trỏ thẳng vào `src/main/java/com/example`, Javadoc có thể không tìm thấy package theo tên đầy đủ như mong đợi.

### Chỉ định package hoặc file nguồn

Có hai cách chọn đầu vào thường gặp:

1. Dùng `sourcepath` cùng `packagenames` khi muốn tài liệu hóa một hoặc nhiều package.
2. Dùng danh sách `sourcefiles` khi muốn chỉ định trực tiếp các file Java cụ thể.

Ví dụ chọn package:

```xml
<javadoc sourcepath="${src.main.java}"
         destdir="${javadoc.dir}"
         packagenames="com.example.api,com.example.model"/>
```

Ví dụ chọn một số file nguồn:

```xml
<javadoc destdir="${javadoc.dir}"
         sourcefiles="src/main/java/com/example/api/InventoryService.java,src/main/java/com/example/api/ProductService.java"/>
```

Không nên cấu hình cả `packagenames` và `sourcefiles` nếu không có chủ đích rõ ràng về phạm vi tài liệu. Với dự án lớn, chọn package thường dễ bảo trì hơn vì thêm class mới trong package không đòi hỏi sửa danh sách từng file.

### Loại trừ package

Có thể loại các package nội bộ khỏi tài liệu công khai bằng thuộc tính `excludepackagenames`:

```xml
<javadoc sourcepath="${src.main.java}"
         destdir="${javadoc.dir}"
         packagenames="com.example.*"
         excludepackagenames="com.example.internal,com.example.generated"/>
```

Đảm bảo pattern package bao phủ đúng các package cần tạo tài liệu. Nếu dự án cần kiểm soát chính xác theo cây thư mục, có thể dùng nested `packageset` với include/exclude thay cho danh sách rộng.

## 3. Phân biệt `sourcepath` và `classpath`

Hai thuộc tính này thường bị nhầm lẫn nhưng có trách nhiệm khác nhau:

| Thuộc tính | Chứa gì? | Mục đích |
|---|---|---|
| `sourcepath` | Thư mục gốc của file `.java` | Tìm source package và các source liên quan |
| `classpath` | Thư mục `.class` và file JAR | Phân giải kiểu dữ liệu mà source tham chiếu |
| `bootclasspath` | Class thư viện nền tảng khi dùng JDK cũ | Thay đổi tập class nền tảng trong các môi trường Java cũ; không phải cấu hình thường dùng cho JDK hiện đại |

Ví dụ source có khai báo:

```java
import com.example.shared.Money;
import org.apache.commons.lang3.StringUtils;
```

Javadoc cần tìm được `Money` và `StringUtils` để phân tích API và tạo liên kết kiểu dữ liệu. Nếu `Money` đã được biên dịch vào `build/classes/main` và `StringUtils` nằm trong JAR của Commons Lang, hãy đưa cả hai vào classpath.

```xml
<path id="api.classpath">
    <pathelement location="build/classes/main"/>
    <fileset dir="lib/main" includes="**/*.jar"/>
</path>

<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.api,com.example.model">
    <classpath refid="api.classpath"/>
</javadoc>
```

`sourcepath` vẫn cần trỏ đến source cần tài liệu hóa; classpath không thay thế sourcepath. Ngược lại, sourcepath không tự chứa các JAR bên ngoài mà source đang import.

### Tái sử dụng classpath từ bước compile

Để tránh Javadoc dùng một tập dependency khác với `javac`, hãy khai báo một path dùng chung:

```xml
<path id="main.compile.classpath">
    <fileset dir="lib/main" includes="**/*.jar"/>
</path>

<target name="compile">
    <mkdir dir="build/classes/main"/>
    <javac srcdir="src/main/java"
           destdir="build/classes/main"
           encoding="UTF-8"
           includeantruntime="false">
        <classpath refid="main.compile.classpath"/>
    </javac>
</target>

<target name="javadoc" depends="compile">
    <javadoc sourcepath="src/main/java"
             destdir="build/docs/api"
             packagenames="com.example.api,com.example.model">
        <classpath>
            <pathelement location="build/classes/main"/>
            <path refid="main.compile.classpath"/>
        </classpath>
    </javadoc>
</target>
```

Ở đây, Javadoc thấy class output đã biên dịch và cùng thư viện ngoài mà compile sử dụng. Nếu source tham chiếu một module khác được cung cấp dưới dạng JAR, JAR đó phải có trên classpath. Nếu dự án dùng module path của Java Platform Module System, cần xem xét cấu hình tương ứng của Javadoc/JDK thay vì giả định classpath truyền thống luôn đủ.

## 4. Cấu hình encoding cho source và HTML đầu ra

Với dự án có comment tiếng Việt, hãy khai báo encoding rõ ràng. Task `javadoc` có ba thuộc tính liên quan:

| Thuộc tính | Tác dụng |
|---|---|
| `encoding` | Charset dùng để đọc file source Java |
| `docencoding` | Charset dùng để ghi các file HTML được tạo |
| `charset` | Charset được ghi trong metadata HTML để trình duyệt giải mã nội dung |

Ví dụ:

```xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.api"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8"/>
```

Ba thuộc tính này giải quyết các giai đoạn khác nhau. Nếu source Java được lưu bằng UTF-8, `encoding` phải là UTF-8 để Javadoc đọc comment đúng. `docencoding` điều khiển byte HTML đầu ra. `charset` giúp trình duyệt hiểu đúng encoding của HTML.

Buildfile `build.xml` cũng cần được lưu đúng encoding với khai báo XML tương ứng:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="api-docs" default="javadoc">
    <property name="javadoc.title" value="Tài liệu API ứng dụng"/>
</project>
```

Không sửa riêng `charset` thành UTF-8 nếu byte HTML vẫn được ghi bằng charset khác. Metadata và byte thực tế phải nhất quán.

### Dấu tiếng Việt trong Javadoc comment

Ví dụ comment:

```java
/**
 * Trả về thông tin khách hàng đã đăng ký.
 *
 * @param customerId mã khách hàng
 * @return thông tin khách hàng hoặc {@code null} nếu không tìm thấy
 */
Customer findCustomer(String customerId);
```

Nếu source được lưu UTF-8 và task dùng `encoding="UTF-8"`, các ký tự như `khách hàng`, `mã` và `không tìm thấy` sẽ được đọc đúng. Khi output dùng UTF-8 và HTML khai báo UTF-8, trình duyệt hiển thị đúng nội dung.

Nếu Javadoc hiển thị mojibake, kiểm tra byte file source, `encoding`, `docencoding`, `charset` và trình duyệt. Không nhầm lỗi font terminal với lỗi encoding của HTML.

## 5. Liên kết đến Javadoc bên ngoài bằng `link`

API của dự án thường tham chiếu kiểu từ JDK hoặc thư viện khác. Nếu muốn tên kiểu dữ liệu trong tài liệu trở thành liên kết đến Javadoc tương ứng, dùng nested element `<link>`.

Ví dụ liên kết đến Java SE 17 API:

```xml
<javadoc sourcepath="${src.main.java}"
         destdir="${javadoc.dir}"
         packagenames="com.example.api"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8">
    <link href="https://docs.oracle.com/en/java/javase/17/docs/api/"/>
</javadoc>
```

`href` là URL gốc của bộ Javadoc bên ngoài. Javadoc dùng danh sách package do tài liệu bên ngoài công bố (ví dụ `element-list` trên JDK hiện đại) để tạo liên kết tới class/package tương ứng.

Liên kết chỉ hoạt động đúng khi URL trỏ đến đúng phiên bản tài liệu và tài liệu bên ngoài có metadata package list phù hợp. Nếu project biên dịch với Java 17, liên kết tới Java SE 17 API giúp người đọc xem đúng API mà source đang hướng tới. Nếu source hỗ trợ nhiều phiên bản JDK, chọn tài liệu tham chiếu theo chính sách tương thích của dự án.

`link` thường cần truy cập URL khi Javadoc tạo tài liệu để đọc danh sách package. Build offline hoặc mạng bị giới hạn có thể làm bước này thất bại.

## 6. Liên kết offline bằng `linkoffline`

Khi môi trường build không có Internet, có thể dùng `linkoffline`. Cách này cung cấp URL tài liệu đích và vị trí cục bộ của file danh sách package mà Javadoc cần để tạo liên kết.

Ví dụ, giả sử đã lưu file `element-list` của Java SE 17 vào `tools/javadoc/java-se-17/element-list`:

```xml
<javadoc sourcepath="${src.main.java}"
         destdir="${javadoc.dir}"
         packagenames="com.example.api"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8">
    <linkoffline
        href="https://docs.oracle.com/en/java/javase/17/docs/api/"
        packagelistLoc="tools/javadoc/java-se-17/element-list"/>
</javadoc>
```

Ở đây:

- `href` vẫn là URL mà liên kết trong HTML sẽ trỏ đến.
- `packagelistLoc` là vị trí local của file danh sách package/element list được dùng để ánh xạ tên package và class.
- Javadoc không cần tải danh sách package từ mạng trong lúc tạo tài liệu.

`linkoffline` không tải toàn bộ Javadoc bên ngoài về local. Nó chỉ cung cấp dữ liệu package list để tạo URL liên kết; người đọc vẫn cần truy cập URL `href` khi mở liên kết. Nếu muốn tài liệu bên ngoài cũng có thể xem offline, cần lưu trữ riêng bộ HTML Javadoc và liên kết tới vị trí nội bộ phù hợp.

Với JDK cũ, danh sách có thể tên `package-list`; với JDK mới thường là `element-list`. Hãy dùng file tương ứng với bộ tài liệu đích và phiên bản Javadoc đang sử dụng.

## 7. Liên kết Javadoc của thư viện bên ngoài

Ngoài JDK, có thể tạo liên kết tới Javadoc của thư viện như Apache Commons Lang hoặc một thư viện nội bộ. Ví dụ:

```xml
<javadoc sourcepath="${src.main.java}"
         destdir="${javadoc.dir}"
         packagenames="com.example.api"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8">
    <link href="https://docs.oracle.com/en/java/javase/17/docs/api/"/>
    <link href="https://commons.apache.org/proper/commons-lang/javadocs/api-3.14.0/"/>
</javadoc>
```

Đường dẫn Javadoc bên ngoài thay đổi theo phiên bản thư viện. Hãy liên kết đến đúng phiên bản dependency được sử dụng, hoặc dùng một URL ổn định do nhóm quản lý. Nếu liên kết sai phiên bản, tài liệu có thể trỏ đến API không tồn tại hoặc chữ ký khác với code đang dùng.

Đối với thư viện nội bộ, nhóm có thể publish Javadoc lên site tài liệu chung và dùng `<link>` trỏ đến URL đó. Nếu build không truy cập được site khi tạo tài liệu, lưu package list phù hợp và dùng `linkoffline`.

## 8. Tổ chức nội dung tài liệu

Ngoài source, classpath và link, task `javadoc` có thể điều khiển phạm vi API và thông tin hiển thị trên trang:

```xml
<javadoc sourcepath="${src.main.java}"
         destdir="${javadoc.dir}"
         packagenames="com.example.api,com.example.model"
         access="protected"
         author="true"
         version="true"
         use="true"
         windowtitle="Inventory API"
         doctitle="Inventory Application API"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8"
         failonerror="true"/>
```

- `access` xác định mức thành viên được đưa vào tài liệu, ví dụ `public`, `protected`, `package` hoặc `private`.
- `author` và `version` cho phép đưa tag `@author` và `@version` vào tài liệu.
- `use` tạo trang tham chiếu cách sử dụng API.
- `windowtitle` và `doctitle` đặt tiêu đề cửa sổ và tiêu đề chính của bộ tài liệu.
- `failonerror` yêu cầu Ant dừng build khi Javadoc trả lỗi.

Đối với thư viện public, `access="protected"` thường phù hợp vì nó bao gồm API public/protected mà consumer có thể kế thừa hoặc gọi. Nếu muốn tài liệu cả thành viên package/private cho mục đích nội bộ, hãy cân nhắc mức truy cập cao hơn và tránh công bố tài liệu nội bộ ra ngoài.

Có thể nhóm package trên trang overview bằng nested element `group`, giúp bộ tài liệu lớn dễ điều hướng. Hãy chọn nhóm theo miền chức năng, ví dụ API công khai, model và integration.

## 9. Kiểm tra chất lượng comment với DocLint

Javadoc có thể kiểm tra một số lỗi trong comment và tag. Với JDK hỗ trợ DocLint, có thể bật kiểm tra bằng tham số `-Xdoclint:all`:

```xml
<javadoc sourcepath="${src.main.java}"
         destdir="${javadoc.dir}"
         packagenames="com.example.api"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8"
         failonerror="true"
         additionalparam="-Xdoclint:all"/>
```

DocLint giúp phát hiện một số vấn đề như HTML/Javadoc tag không hợp lệ, thiếu nội dung ở các vị trí được kiểm tra và tham chiếu sai. Tùy JDK, tập kiểm tra và mức cảnh báo có thể khác nhau. Không nên tắt toàn bộ kiểm tra chỉ để build qua; hãy sửa comment hoặc cấu hình mức kiểm tra có chủ đích.

Các tag nên dùng đúng ngữ nghĩa:

| Tag | Dùng cho |
|---|---|
| `@param` | Mô tả tham số của method/constructor hoặc type parameter |
| `@return` | Mô tả giá trị trả về của method |
| `@throws` / `@exception` | Mô tả exception có thể được ném |
| `@since` | Phiên bản API được thêm vào |
| `@deprecated` | API đã lỗi thời; nên nêu lựa chọn thay thế |
| `{@link ...}` | Tạo liên kết đến class, method hoặc thành viên khác |
| `{@code ...}` | Hiển thị đoạn code inline mà không diễn giải HTML |
| `{@literal ...}` | Hiển thị văn bản literal mà không diễn giải HTML |

Ví dụ:

```java
/**
 * Chuyển một mã sản phẩm thành dạng chuẩn.
 *
 * @param rawCode mã đầu vào; không được {@code null}
 * @return mã đã chuẩn hóa
 * @throws IllegalArgumentException nếu mã rỗng
 * @see java.util.Locale
 * @since 2.0
 */
String normalize(String rawCode);
```

## 10. Ví dụ buildfile hoàn chỉnh

Giả sử dự án có cấu trúc:

```text
project/
├── build.xml
├── src/main/java/
│   └── com/example/api/InventoryService.java
├── lib/main/
│   └── commons-lang3-3.14.0.jar
└── tools/javadoc/java-se-17/
    └── element-list
```

Buildfile tạo Javadoc cho hai package, đọc source UTF-8, phân giải class bằng compile classpath và liên kết offline tới Java SE 17 API:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project name="inventory-api-docs" default="javadoc" basedir=".">

    <property name="src.main.java" location="src/main/java"/>
    <property name="build.dir" location="build"/>
    <property name="classes.dir" location="${build.dir}/classes/main"/>
    <property name="javadoc.dir" location="${build.dir}/docs/api"/>

    <path id="main.compile.classpath">
        <fileset dir="lib/main" includes="**/*.jar"/>
    </path>

    <target name="init">
        <mkdir dir="${classes.dir}"/>
        <mkdir dir="${javadoc.dir}"/>
    </target>

    <target name="compile" depends="init">
        <javac srcdir="${src.main.java}"
               destdir="${classes.dir}"
               encoding="UTF-8"
               includeantruntime="false">
            <classpath refid="main.compile.classpath"/>
        </javac>
    </target>

    <target name="javadoc" depends="compile">
        <javadoc sourcepath="${src.main.java}"
                 destdir="${javadoc.dir}"
                 packagenames="com.example.api,com.example.model"
                 access="protected"
                 encoding="UTF-8"
                 docencoding="UTF-8"
                 charset="UTF-8"
                 author="true"
                 version="true"
                 use="true"
                 windowtitle="Inventory API"
                 doctitle="Inventory Application API"
                 failonerror="true"
                 additionalparam="-Xdoclint:all">
            <classpath>
                <pathelement location="${classes.dir}"/>
                <path refid="main.compile.classpath"/>
            </classpath>
            <linkoffline
                href="https://docs.oracle.com/en/java/javase/17/docs/api/"
                packagelistLoc="tools/javadoc/java-se-17/element-list"/>
        </javadoc>
    </target>

</project>
```

Trong ví dụ này, target `compile` bảo đảm class output có sẵn. Target `javadoc` sử dụng sourcepath để tìm source package và classpath để phân giải các kiểu mà source tham chiếu. Ba thuộc tính encoding bảo đảm comment tiếng Việt được đọc và HTML được ghi đúng UTF-8. `linkoffline` sử dụng `element-list` local để tạo liên kết tới Java SE 17 mà không cần tải package list trong lúc build.

Chạy:

```bash
ant javadoc
```

Bộ tài liệu được tạo dưới `build/docs/api`. Trang bắt đầu thường là `index.html`; mở trang này trong trình duyệt để kiểm tra package, class, nội dung tiếng Việt và liên kết bên ngoài.

## 11. Tạo Javadoc trong CI và build offline

Để tài liệu có thể tạo ổn định trên máy lập trình viên và CI:

- Giữ cùng sourcepath và package selection trong mọi môi trường.
- Dùng classpath được chia sẻ với compile để tránh thiếu kiểu dữ liệu.
- Khai báo `encoding`, `docencoding` và `charset` tường minh.
- Pin URL tài liệu bên ngoài theo phiên bản dependency hoặc JDK.
- Dùng `linkoffline` và lưu package list tương ứng nếu build phải chạy không có Internet.
- Lưu thư mục Javadoc như một artifact riêng trong CI; không đưa tài liệu API vào JAR runtime trừ khi dự án có yêu cầu rõ ràng.
- Bật DocLint hoặc kiểm tra comment trong pipeline để lỗi tài liệu được phát hiện sớm.
- Chỉ publish tài liệu sau khi task Javadoc hoàn tất thành công.

`linkoffline` chỉ làm cho bước phân giải package list độc lập với mạng. Các hyperlink trong HTML vẫn trỏ đến URL khai báo ở `href`; người đọc cần có mạng hoặc một bản Javadoc được host nội bộ để mở chúng.

## 12. Lỗi thường gặp và cách xử lý

| Triệu chứng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| Không tìm thấy package | `sourcepath` trỏ sai thư mục gốc hoặc tên package sai | Trỏ đến source root và kiểm tra khai báo `package` |
| Javadoc báo không tìm thấy class được import | Thiếu class output hoặc JAR trên classpath | Thêm `build/classes` và dependency tương ứng vào nested `classpath` |
| Tài liệu thiếu package mới | Danh sách `packagenames` chưa cập nhật hoặc pattern không bao phủ package | Mở rộng package selection hoặc dùng `packageset` có include phù hợp |
| Comment tiếng Việt bị lỗi dấu | `encoding` không khớp source hoặc HTML output/meta không thống nhất | Dùng UTF-8 nhất quán cho source, `docencoding` và `charset` |
| Liên kết tới JDK API không được tạo | URL sai, package list không truy cập được hoặc sai phiên bản | Kiểm tra URL và dùng `linkoffline` với element-list/package-list tương ứng |
| Build offline thất bại ở bước link | `<link>` cần tải package list từ URL | Lưu package list local và chuyển sang `<linkoffline>` |
| Javadoc thất bại vì comment/tag | DocLint phát hiện HTML hoặc tag sai | Sửa comment và dùng tag theo đúng ngữ nghĩa |
| Trang HTML hiển thị thiếu kiểu liên kết | Dependency Javadoc bên ngoài chưa được khai báo link | Thêm `<link>` hoặc `<linkoffline>` cho thư viện tương ứng |
| Javadoc chứa API nội bộ không mong muốn | `access` quá rộng hoặc package selection bao gồm package nội bộ | Giới hạn `access`, loại package nội bộ hoặc dùng package set cụ thể |

Khi debug, kiểm tra theo thứ tự: sourcepath và package selection; classpath; encoding của source; encoding của HTML; cuối cùng là link ngoài và DocLint. Cách này giúp xác định đúng lớp cấu hình gây lỗi.

## 13. Quy tắc tổ chức buildfile

- Dùng `sourcepath` cho thư mục gốc source Java và `packagenames`/`packageset` để chọn phạm vi API.
- Dùng `classpath` cho class đã biên dịch và thư viện mà source tham chiếu; không dùng classpath thay cho sourcepath.
- Tái sử dụng cùng dependency path giữa `javac` và `javadoc` để tránh khác biệt khi phân giải kiểu.
- Đặt `encoding`, `docencoding` và `charset` tường minh, thường là UTF-8 cho dự án mới.
- Liên kết tới Javadoc đúng phiên bản của JDK và dependency.
- Dùng `linkoffline` với package list local khi build cần độc lập khỏi mạng.
- Giữ tài liệu API trong output directory riêng như `build/docs/api`.
- Dùng `access` và package selection để tránh công bố API nội bộ.
- Bật DocLint và `failonerror` theo chính sách CI của dự án.
- Viết comment có mô tả, `@param`, `@return`, `@throws` và `@since` phù hợp.

## 14. Bài tập tự kiểm tra

**Bài 1.** `sourcepath` và `classpath` khác nhau thế nào?

**Đáp án:** `sourcepath` chỉ nơi Javadoc tìm source `.java`; `classpath` chỉ nơi tìm class và JAR mà source tham chiếu.

**Bài 2.** Muốn đọc comment tiếng Việt trong source UTF-8 và tạo HTML UTF-8, nên cấu hình các thuộc tính nào?

**Đáp án:** Dùng `encoding="UTF-8"`, `docencoding="UTF-8"` và `charset="UTF-8"`.

**Bài 3.** `link` và `linkoffline` khác nhau ở điểm nào?

**Đáp án:** `link` lấy package list từ tài liệu ở URL; `linkoffline` nhận URL đích và vị trí package list/element list đã có sẵn tại local.

**Bài 4.** Nếu source import `org.apache.commons.lang3.StringUtils`, cần làm gì để Javadoc phân giải kiểu?

**Đáp án:** Đưa JAR Commons Lang tương ứng vào classpath của task `javadoc`.

**Bài 5.** Vì sao Javadoc có thể tạo HTML thành công nhưng hyperlink đến Java API không hoạt động?

**Đáp án:** URL link có thể sai phiên bản, package list không khớp hoặc tài liệu đích không còn được host ở URL đó. Kiểm tra URL và metadata package list.

## Kết luận

Task `javadoc` trong Apache Ant tạo tài liệu API từ source Java. `sourcepath` và package selection xác định source cần xử lý; `classpath` giúp phân giải class và dependency; `encoding`, `docencoding` và `charset` giữ nội dung tiếng Việt chính xác; `link` và `linkoffline` tạo liên kết tới Javadoc bên ngoài. Khi dùng chung dependency path với bước compile, khóa phiên bản tài liệu tham chiếu và cấu hình encoding rõ ràng, tài liệu API có thể được tạo nhất quán trên máy phát triển và CI.

