# Sinh tài liệu API bằng task javadoc trong Apache Ant

Javadoc là công cụ của JDK dùng để đọc comment có cấu trúc trong mã nguồn Java và tạo tài liệu API dưới dạng HTML. Apache Ant tích hợp công cụ này qua task <javadoc>, nhờ đó quá trình sinh tài liệu có thể trở thành một bước chính thức trong build: biên dịch mã nguồn, tạo API docs, rồi lưu tài liệu vào thư mục phát hành hoặc đưa lên hệ thống tài liệu nội bộ.

Task <javadoc> có thể chọn package hoặc file nguồn, cấu hình classpath, đặt thư mục đầu ra, tạo liên kết đến API bên ngoài, bổ sung tag tùy chỉnh và điều khiển cách build phản ứng khi Javadoc gặp lỗi. Để tài liệu hữu ích, phần cấu hình Ant cần đi cùng comment Javadoc rõ ràng trong mã nguồn.

## 1. Javadoc tạo ra tài liệu từ comment trong mã nguồn

Javadoc không tự suy luận mục đích của lớp hay phương thức chỉ từ tên. Nó đọc các comment được viết theo cú pháp Javadoc, thường bắt đầu bằng /** và kết thúc bằng */.

Ví dụ:

~~~java
package com.example.calculator;

/**
 * Provides basic arithmetic operations.
 *
 * <p>The class contains stateless methods that can be reused by
 * application services and command-line tools.</p>
 *
 * @author Development Team
 * @since 1.0
 */
public class Calculator {

    /**
     * Adds two integers.
     *
     * @param left first operand
     * @param right second operand
     * @return the sum of the two operands
     */
    public int add(int left, int right) {
        return left + right;
    }

    /**
     * Divides one number by another.
     *
     * @param dividend number to be divided
     * @param divisor number used as the divisor
     * @return the quotient
     * @throws IllegalArgumentException if divisor is zero
     */
    public int divide(int dividend, int divisor) {
        if (divisor == 0) {
            throw new IllegalArgumentException("divisor must not be zero");
        }
        return dividend / divisor;
    }
}
~~~

Comment Javadoc có thể mô tả:

- Lớp hoặc interface dùng để làm gì.
- Phương thức thực hiện công việc nào.
- Ý nghĩa và giới hạn của từng tham số.
- Giá trị trả về.
- Exception có thể được ném ra.
- Phiên bản API, trạng thái deprecated và liên kết đến thành phần liên quan.

Một số block tag thường dùng:

| Tag | Mục đích |
|---|---|
| @param | Mô tả tham số của phương thức hoặc kiểu generic |
| @return | Mô tả giá trị trả về |
| @throws hoặc @exception | Mô tả exception có thể phát sinh |
| @since | Ghi phiên bản API được giới thiệu |
| @deprecated | Đánh dấu API đã lỗi thời và hướng người dùng đến lựa chọn thay thế |
| @see | Thêm tham chiếu đến lớp, phương thức hoặc tài liệu khác |
| @author | Ghi tác giả khi bật tùy chọn author |
| @version | Ghi phiên bản khi bật tùy chọn version |
| @serial | Mô tả trường được tuần tự hóa trong các lớp Serializable |

Các inline tag thường gặp:

- {@link Type#method()} tạo liên kết đến API khác.
- {@linkplain Type} tạo liên kết với văn bản hiển thị thông thường.
- {@code expression} hiển thị mã hoặc tên API dưới dạng code.
- {@literal text} hiển thị nội dung nguyên văn mà không diễn giải HTML hoặc Javadoc tag.
- {@inheritDoc} kế thừa phần mô tả từ phương thức cha hoặc interface khi phù hợp.
- {@value} hiển thị giá trị của hằng số static final.

Ví dụ:

~~~java
/**
 * Returns the default timeout in milliseconds.
 *
 * <p>Use {@link #setTimeout(long)} to override this value.
 * The default is {@value #DEFAULT_TIMEOUT_MS}.</p>
 */
public static final long DEFAULT_TIMEOUT_MS = 5000L;
~~~

Chỉ những comment Javadoc được đặt đúng vị trí và đúng cú pháp mới được đưa vào tài liệu. Comment thông thường dạng // hoặc /* ... */ không thay thế comment /** ... */.

## 2. Chuẩn bị JDK và task javadoc của Ant

Công cụ Javadoc đi kèm JDK. Máy build cần có JDK chứa executable javadoc, không chỉ một runtime Java tối giản.

Kiểm tra môi trường bằng:

~~~bash
java -version
javadoc --version
ant -version
~~~

Trên một số phiên bản JDK cũ, tùy chọn hiển thị phiên bản có thể khác; nếu javadoc --version không được hỗ trợ, hãy dùng javadoc -version.

Task <javadoc> là task lõi của Ant. Khác với task JUnit tùy chọn, thông thường không cần cài một JAR task riêng chỉ để Ant nhận diện javadoc. Tuy vậy, Ant vẫn phải tìm được công cụ Javadoc tương thích với JDK đang dùng.

Nếu cần chọn chính xác executable, có thể cấu hình task chạy Javadoc ở tiến trình riêng bằng fork và executable. Cách này hữu ích khi máy có nhiều JDK hoặc khi CI cần dùng một phiên bản Javadoc cố định.

## 3. Ví dụ tối giản: sinh tài liệu cho một package

Giả sử dự án có cấu trúc:

~~~text
calculator/
├── build.xml
├── src/
│   └── main/
│       └── java/
│           └── com/example/calculator/
│               ├── Calculator.java
│               └── CalculatorService.java
└── build/
~~~

Một target cơ bản:

~~~xml
<project name="calculator" default="javadoc" basedir=".">
    <property name="src.dir" location="src/main/java" />
    <property name="docs.dir" location="build/docs/api" />

    <target name="javadoc">
        <mkdir dir="${docs.dir}" />

        <javadoc sourcepath="${src.dir}"
                 destdir="${docs.dir}"
                 packagenames="com.example.calculator"
                 author="true"
                 version="true"
                 use="true"
                 windowtitle="Calculator API"
                 doctitle="Calculator API">
        </javadoc>
    </target>
</project>
~~~

Chạy:

~~~bash
ant javadoc
~~~

Ant gọi công cụ Javadoc với package được chỉ định, đọc các file nguồn từ sourcepath và ghi trang HTML vào build/docs/api.

Các thuộc tính quan trọng trong ví dụ:

- sourcepath xác định thư mục gốc chứa mã nguồn Java.
- destdir xác định thư mục tạo tài liệu.
- packagenames chỉ định package cần sinh docs.
- author và version yêu cầu đưa các tag tương ứng vào tài liệu.
- use tạo các trang tra cứu nơi một API được sử dụng.
- windowtitle đặt tiêu đề cửa sổ/trình duyệt.
- doctitle đặt tiêu đề chính trên trang tổng quan.

Nếu thư mục đích chưa tồn tại, nên tạo bằng mkdir trước khi gọi task. Các thư mục package phải nằm đúng dưới sourcepath để Javadoc tìm được nguồn.

## 4. Chọn package bằng packagenames hoặc packageset

Có hai cách thường dùng để xác định phạm vi package.

### 4.1. Dùng packagenames

Thuộc tính packagenames nhận danh sách package, phân tách bằng dấu phẩy:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.model,com.example.service" />
~~~

Cách này phù hợp khi số package ít và danh sách tương đối ổn định. Có thể dùng mẫu package như com.example.* theo quy tắc của Javadoc, nhưng nếu muốn kiểm soát cây thư mục cụ thể hoặc chọn nhiều package theo pattern, packageset thường linh hoạt hơn.

### 4.2. Dùng packageset để chọn theo cấu trúc thư mục

Nested element packageset cho phép chọn package từ thư mục nguồn bằng include/exclude:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api">
    <packageset dir="src/main/java">
        <include name="com/example/**" />
        <exclude name="com/example/internal/**" />
    </packageset>
</javadoc>
~~~

Trong ví dụ, Ant chọn các package nằm dưới com/example và loại cây package internal.

Các mẫu trong packageset được viết theo đường dẫn tương đối với thư mục dir. Dùng dấu gạch chéo xuôi / trong pattern, kể cả khi build chạy trên Windows.

Có thể khai báo nhiều packageset nếu mã nguồn được chia thành nhiều source root:

~~~xml
<javadoc destdir="build/docs/api">
    <packageset dir="src/main/java">
        <include name="com/example/**" />
    </packageset>
    <packageset dir="modules/shared/src/main/java">
        <include name="com/example/shared/**" />
    </packageset>
</javadoc>
~~~

Mỗi packageset xác định một vùng package riêng. Hãy bảo đảm source root không bị lặp hoặc tạo ra các package trùng nhau gây khó hiểu khi sinh tài liệu.

### 4.3. Chọn file nguồn cụ thể

Khi chỉ cần sinh docs cho một nhóm file nhỏ, có thể dùng nested fileset:

~~~xml
<javadoc destdir="build/docs/api">
    <fileset dir="src/main/java">
        <include name="com/example/api/**/*.java" />
        <exclude name="**/internal/**" />
    </fileset>
</javadoc>
~~~

FileSet phù hợp khi muốn chọn file theo mẫu. Packageset phù hợp khi muốn Javadoc xử lý các package. Không nên trộn nhiều cơ chế chọn nguồn nếu chưa rõ phạm vi cuối cùng cần tạo.

## 5. Cung cấp classpath cho Javadoc

Khi mã nguồn tham chiếu đến các lớp từ thư viện ngoài hoặc module khác, Javadoc có thể cần classpath để phân giải kiểu dữ liệu và tạo liên kết đúng.

Ví dụ:

~~~xml
<path id="api.classpath">
    <pathelement location="lib/shared-model.jar" />
    <pathelement location="lib/validation-api.jar" />
</path>

<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*">
    <classpath refid="api.classpath" />
</javadoc>
~~~

Classpath nên chứa:

- Các JAR mà public API sử dụng trong kiểu tham số hoặc kiểu trả về.
- Output classes của module phụ thuộc nếu API tham chiếu trực tiếp đến chúng.
- Những dependency cần thiết để Javadoc phân giải kiểu.

Nếu thiếu dependency, Javadoc có thể báo không tìm thấy package hoặc class. Trong một số trường hợp, tài liệu vẫn có thể sinh nhưng liên kết kiểu bị thiếu hoặc cảnh báo xuất hiện. Hãy thêm đúng dependency vào classpath thay vì bỏ qua mọi cảnh báo.

Nếu muốn tạo docs cho nhiều module, có thể tạo một Path chung cho dependency và tái sử dụng bằng refid.

## 6. Cấu hình phạm vi API bằng access

Thuộc tính access quyết định mức hiển thị thành phần trong tài liệu. Các giá trị thường dùng:

| Giá trị | Phạm vi |
|---|---|
| public | Chỉ thành phần public |
| protected | Public và protected |
| package | Public, protected và package-private |
| private | Bao gồm cả thành phần private |

Mặc định của công cụ Javadoc là mức protected. Với tài liệu API công khai, thường nên chọn public hoặc protected tùy chính sách dự án.

Ví dụ chỉ tạo tài liệu cho API public:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*"
         access="public" />
~~~

Nếu tạo tài liệu nội bộ để phục vụ bảo trì, có thể dùng package hoặc private. Không nên đưa API private vào tài liệu công khai nếu chúng không phải hợp đồng mà người dùng thư viện được phép dựa vào.

Ngoài access, một số tùy chọn giúp kiểm soát nội dung:

- author="true": đưa thông tin @author vào docs.
- version="true": đưa thông tin @version vào docs.
- use="true": tạo các trang sử dụng API.
- nodeprecated="true": loại thành phần deprecated khỏi tài liệu.
- noindex="true": không tạo chỉ mục.
- notree="true": không tạo cây phân cấp.
- splitindex="true": chia chỉ mục thành nhiều trang.
- linksource="true": tạo trang xem mã nguồn và liên kết từ docs nếu Javadoc hỗ trợ trong môi trường đang dùng.

Hãy bật các tùy chọn theo mục tiêu tài liệu. Với API lớn, tạo trang usage và source có thể làm tài liệu nặng hơn đáng kể.

## 7. Đặt tiêu đề, header, footer và stylesheet

Tài liệu API cần có nhận diện và thông tin ngữ cảnh. Task javadoc cung cấp các thuộc tính để đặt tiêu đề và nội dung đầu/cuối trang.

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*"
         windowtitle="Inventory API"
         doctitle="Inventory Service API"
         header="Inventory"
         footer="Internal API Reference"
         bottom="Copyright 2026 Example Team"
         stylesheetfile="docs/api-styles.css" />
~~~

Ý nghĩa:

- windowtitle: tiêu đề cửa sổ hoặc tab trình duyệt.
- doctitle: tiêu đề trang tổng quan.
- header và footer: nội dung ở vùng đầu và cuối trang.
- bottom: nội dung ở phần cuối trang.
- stylesheetfile: file CSS tùy chỉnh giao diện tài liệu.

Đường dẫn stylesheetfile phải trỏ đến file CSS tồn tại. Hãy giữ file stylesheet cùng repository hoặc tạo nó trước khi chạy Javadoc.

Nếu dùng HTML trong các tiêu đề, cần escape ký tự đặc biệt đúng với XML. Không đặt ký tự < hoặc & trực tiếp trong thuộc tính XML mà không escape hoặc dùng cách khai báo phù hợp.

## 8. Đặt encoding và locale

Encoding ảnh hưởng đến việc đọc comment trong mã nguồn và hiển thị nội dung HTML được tạo ra. Với dự án có comment tiếng Việt, cần cấu hình rõ encoding để tránh lỗi ký tự.

Ba thuộc tính thường gặp:

- encoding: encoding của file nguồn mà Javadoc đọc.
- docencoding: encoding của file HTML được tạo.
- charset: khai báo charset trong HTML để trình duyệt đọc đúng nội dung.

Ví dụ:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*"
         encoding="UTF-8"
         docencoding="UTF-8"
         charset="UTF-8"
         locale="vi_VN" />
~~~

Hãy bảo đảm file Java thực sự được lưu bằng UTF-8. Chỉ đặt encoding trong buildfile không thể sửa nội dung đã bị lưu sai encoding.

Locale có thể ảnh hưởng ngôn ngữ và định dạng mà công cụ Javadoc sử dụng cho nội dung được sinh. Nếu JDK hoặc locale tương ứng không có sẵn, kết quả có thể không như mong muốn. Hãy kiểm tra tài liệu được sinh trên môi trường CI giống môi trường phát hành.

## 9. Liên kết đến tài liệu API bên ngoài bằng link

Khi API công khai sử dụng kiểu dữ liệu từ JDK hoặc thư viện khác, liên kết đến tài liệu chính thức giúp người đọc tra cứu nhanh.

Nested element link khai báo URL của bộ API docs bên ngoài:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*">
    <link href="https://docs.oracle.com/en/java/javase/21/docs/api/" />
</javadoc>
~~~

Khi Javadoc gặp tham chiếu đến kiểu có trong tài liệu được liên kết, nó có thể tạo hyperlink sang trang API bên ngoài.

Có thể thêm nhiều link:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*">
    <link href="https://docs.oracle.com/en/java/javase/21/docs/api/" />
    <link href="https://junit.org/junit4/javadoc/4.13.2/" />
</javadoc>
~~~

Chỉ thêm URL đúng với tài liệu API thực tế. Nếu phiên bản thư viện thay đổi, cần cập nhật link để người đọc không bị chuyển đến tài liệu không tương thích.

### 9.1. Liên kết offline

Trong môi trường build không có internet, có thể dùng chế độ offline với danh sách package được tải sẵn:

~~~xml
<link href="https://example.org/shared-api/"
      offline="true"
      packagelistLoc="docs/linkdata/shared-api" />
~~~

Thư mục packagelistLoc cần chứa file package-list hoặc element-list tương ứng với bộ tài liệu được liên kết. Nếu không có danh sách package, Javadoc không thể tạo liên kết offline đúng cách.

Offline link hữu ích khi build trong mạng nội bộ hoặc CI bị giới hạn truy cập. Hãy lưu metadata liên kết trong repository hoặc cung cấp nó qua artifact nội bộ.

## 10. Nhóm package và bổ sung tag tùy chỉnh

Với API lớn, có thể nhóm package theo chức năng bằng nested element group:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*">
    <group title="Core API"
           packages="com.example.core,com.example.model" />
    <group title="Integration API"
           packages="com.example.integration,com.example.client" />
</javadoc>
~~~

Nhóm package giúp người đọc tìm phần API theo chủ đề thay vì xem một danh sách package dài.

Nếu dự án dùng tag riêng, khai báo tag trong task:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*">
    <tag name="implNote"
         scope="all"
         description="Implementation note:" />
</javadoc>
~~~

Trong mã nguồn có thể viết:

~~~java
/**
 * Loads a configuration value.
 *
 * @implNote Values are cached for the lifetime of the service.
 */
public String loadValue(String key) {
    // implementation
    return null;
}
~~~

Thuộc tính scope xác định nơi tag có thể xuất hiện, ví dụ all, overview, packages, types, constructors, methods hoặc fields. Hãy dùng tên tag có ý nghĩa và mô tả ngắn gọn để tài liệu sinh ra dễ đọc.

Nếu cần cách sinh tài liệu hoàn toàn khác, Javadoc hỗ trợ doclet tùy chỉnh. Ant cho phép khai báo doclet và đường dẫn thư viện của doclet:

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/custom">
    <doclet name="com.example.docs.CustomDoclet"
            path="lib/custom-doclet.jar">
        <param name="-format" value="html" />
    </doclet>
</javadoc>
~~~

Doclet là cơ chế mở rộng nâng cao. Chỉ dùng khi công cụ mặc định và tag tùy chỉnh không đáp ứng được định dạng đầu ra cần thiết.

## 11. Chọn Javadoc executable và fork

Task javadoc có thể chạy công cụ Javadoc theo cách tích hợp với Ant hoặc khởi chạy một tiến trình riêng. Khi cần xác định rõ JDK dùng để sinh docs, đặt fork="true" và executable trỏ đến chương trình javadoc.

Ví dụ trên Linux/macOS:

~~~xml
<property name="jdk.home" location="/opt/jdk-21" />
<property name="javadoc.executable"
          location="${jdk.home}/bin/javadoc" />

<target name="javadoc">
    <javadoc sourcepath="src/main/java"
             destdir="build/docs/api"
             packagenames="com.example.*"
             fork="true"
             executable="${javadoc.executable}"
             maxmemory="1g"
             failonerror="true" />
</target>
~~~

Trên Windows, executable thường là:

~~~xml
<property name="javadoc.executable"
          location="${jdk.home}/bin/javadoc.exe" />
~~~

Thuộc tính maxmemory đặt giới hạn bộ nhớ cho tiến trình Javadoc được fork. Nó không điều chỉnh heap của JVM chạy Ant.

Bật fork hữu ích khi:

- Máy có nhiều JDK và cần chọn bản cụ thể.
- JDK đang dùng không hỗ trợ chế độ chạy tích hợp mà Ant yêu cầu.
- Muốn tách bộ nhớ và tiến trình Javadoc khỏi Ant.
- Cần truyền các tùy chọn JVM riêng cho tiến trình tài liệu.

Không nên mặc định rằng fork làm tài liệu sinh nhanh hơn. Tiến trình riêng có chi phí khởi động; lựa chọn nên dựa trên yêu cầu tương thích và quản lý môi trường.

## 12. Kiểm soát cảnh báo và lỗi

Task javadoc có thuộc tính failonerror để quyết định build có dừng khi công cụ Javadoc kết thúc với lỗi hay không. Với pipeline CI, nên để lỗi tài liệu API làm build thất bại nếu tài liệu là artifact bắt buộc.

~~~xml
<javadoc sourcepath="src/main/java"
         destdir="build/docs/api"
         packagenames="com.example.*"
         failonerror="true"
         verbose="false" />
~~~

Nếu muốn tiếp tục build để thực hiện bước thu thập log hoặc xử lý khác, có thể đặt failonerror="false", nhưng cần có cách theo dõi kết quả và không coi tài liệu sinh dở là thành công.

Một số nguyên nhân Javadoc thất bại:

- Sourcepath sai hoặc không tìm thấy source.
- Package được chỉ định không tồn tại.
- Classpath thiếu dependency.
- Comment chứa cú pháp Javadoc không hợp lệ.
- Link đến tài liệu bên ngoài không truy cập được trong môi trường build.
- JDK hoặc phiên bản Javadoc không tương thích với tùy chọn đang dùng.

JDK mới có thể bật thêm các kiểm tra doclint và đưa ra cảnh báo về comment hoặc HTML. Hãy sửa comment không hợp lệ thay vì chỉ tắt kiểm tra để che cảnh báo. Nếu dự án cần tùy chọn Javadoc đặc biệt, hãy truyền chúng bằng các cơ chế bổ sung mà phiên bản Ant đang dùng hỗ trợ và kiểm tra trên đúng JDK của CI.

## 13. Ví dụ buildfile hoàn chỉnh

Ví dụ sau kết hợp biên dịch, classpath, chọn package, link đến JDK API, encoding, tiêu đề và tạo tài liệu:

~~~xml
<project name="inventory" default="api-docs" basedir=".">
    <property name="src.dir" location="src/main/java" />
    <property name="build.dir" location="build" />
    <property name="classes.dir" location="${build.dir}/classes" />
    <property name="docs.dir" location="${build.dir}/docs/api" />
    <property name="lib.dir" location="lib" />

    <path id="compile.classpath">
        <fileset dir="${lib.dir}">
            <include name="**/*.jar" />
        </fileset>
    </path>

    <target name="clean">
        <delete dir="${build.dir}" />
    </target>

    <target name="compile">
        <mkdir dir="${classes.dir}" />
        <javac srcdir="${src.dir}"
               destdir="${classes.dir}"
               includeantruntime="false"
               encoding="UTF-8">
            <classpath refid="compile.classpath" />
        </javac>
    </target>

    <target name="api-docs" depends="compile">
        <mkdir dir="${docs.dir}" />

        <javadoc sourcepath="${src.dir}"
                 destdir="${docs.dir}"
                 packagenames="com.example.*"
                 access="protected"
                 author="true"
                 version="true"
                 use="true"
                 encoding="UTF-8"
                 docencoding="UTF-8"
                 charset="UTF-8"
                 windowtitle="Inventory API"
                 doctitle="Inventory API Reference"
                 failonerror="true">
            <classpath>
                <pathelement location="${classes.dir}" />
                <path refid="compile.classpath" />
            </classpath>

            <link href="https://docs.oracle.com/en/java/javase/21/docs/api/" />

            <group title="Core API"
                   packages="com.example.model,com.example.service" />
            <group title="Integration API"
                   packages="com.example.integration,com.example.client" />

            <tag name="implNote"
                 scope="all"
                 description="Implementation note:" />
        </javadoc>
    </target>
</project>
~~~

Chạy:

~~~bash
ant clean api-docs
~~~

Target compile tạo lớp ứng dụng trước. Target api-docs phụ thuộc compile, sau đó Javadoc đọc source, classpath và các comment để tạo HTML trong build/docs/api.

Nếu dự án có package khác, hãy sửa packagenames và group tương ứng. Nếu source code không cần biên dịch trước để sinh docs, có thể bỏ dependency compile; tuy nhiên, classpath vẫn cần đủ để phân giải các kiểu tham chiếu.

## 14. Tích hợp Javadoc vào quy trình phát hành

Tài liệu API nên được tạo tự động và lưu cùng phiên bản phát hành. Một quy trình có thể gồm:

1. clean: xóa output cũ.
2. compile: biên dịch mã nguồn.
3. test: chạy kiểm thử.
4. api-docs: sinh tài liệu Javadoc.
5. package: đóng gói artifact và tài liệu.
6. publish-docs: chuyển tài liệu đến nơi lưu trữ nội bộ hoặc website tài liệu.

Ví dụ target package có thể đưa thư mục docs vào gói phân phối:

~~~xml
<target name="package" depends="test,api-docs">
    <zip destfile="dist/inventory-release.zip">
        <fileset dir="build/classes" />
        <zipfileset dir="build/docs/api" prefix="docs/api" />
    </zip>
</target>
~~~

Tài liệu nên được gắn với đúng commit hoặc version của mã nguồn. Nếu chỉ xuất bản tài liệu mới nhất mà không lưu phiên bản, người dùng có thể đọc API docs không tương ứng với thư viện đang sử dụng.

Đối với thư viện công khai, có thể xuất bản Javadoc cùng artifact binary và source JAR. Với hệ thống nội bộ, lưu docs trong artifact repository hoặc website có kiểm soát phiên bản.

## 15. Những lỗi thường gặp

### 15.1. Không tìm thấy package

Kiểm tra sourcepath, packagenames và packageset. Package com.example.service phải nằm trong cây thư mục tương ứng dưới source root.

### 15.2. Không tìm thấy kiểu dữ liệu phụ thuộc

Thêm JAR hoặc output module vào nested classpath. Javadoc cần phân giải kiểu tham số, kiểu trả về và các liên kết đến lớp ngoài.

### 15.3. Tài liệu không có mô tả như mong muốn

Kiểm tra mã nguồn có comment dạng /** ... */ hay chỉ có // hoặc /* ... */. Bảo đảm tag @param, @return và @throws được đặt đúng phương thức.

### 15.4. Tiếng Việt bị lỗi font hoặc ký tự

Kiểm tra file nguồn thực sự lưu bằng UTF-8, sau đó đặt encoding, docencoding và charset nhất quán. Mở file HTML sinh ra để xác nhận charset meta và nội dung.

### 15.5. Không tạo liên kết đến API bên ngoài

Kiểm tra URL link có trỏ đến root của Javadoc và môi trường build có truy cập được không. Với link offline, kiểm tra packagelistLoc chứa danh sách package tương ứng.

### 15.6. Không tìm thấy executable javadoc

Kiểm tra JDK có được cài đặt và executable nằm trong thư mục bin. Nếu dùng fork, kiểm tra đường dẫn executable và quyền thực thi. JAVA_HOME cần trỏ đến JDK phù hợp.

### 15.7. Build vẫn thành công dù docs bị thiếu

Kiểm tra failonerror và log của task. Với pipeline yêu cầu API docs là artifact bắt buộc, hãy để failonerror=true và không bỏ qua lỗi Javadoc.

### 15.8. Quét nhầm package nội bộ

Dùng include/exclude trong packageset để loại package implementation hoặc internal. Không nên đưa mọi package vào tài liệu công khai nếu dự án chỉ cam kết một API nhỏ.

## 16. Thực hành tốt

- **Viết comment cho API công khai.** Mô tả mục đích, tham số, giá trị trả về, exception và ví dụ khi cần.
- **Tổ chức source root nhất quán.** Giữ package nằm dưới thư mục nguồn mà task javadoc sử dụng.
- **Chọn package có chủ đích.** Dùng packagenames cho danh sách nhỏ hoặc packageset khi cần lọc theo cây thư mục.
- **Cung cấp classpath đầy đủ.** Thêm module và JAR mà public API tham chiếu.
- **Giữ encoding thống nhất.** Dùng UTF-8 cho mã nguồn và HTML nếu dự án có nội dung tiếng Việt.
- **Liên kết tài liệu đúng phiên bản.** API docs bên ngoài phải tương thích với dependency mà mã nguồn sử dụng.
- **Đặt tiêu đề và nhóm package rõ ràng.** Giúp người đọc hiểu phạm vi tài liệu ngay khi mở trang.
- **Kiểm soát warning.** Sửa Javadoc comment sai và kiểm tra trên JDK được CI sử dụng.
- **Lưu tài liệu theo phiên bản.** Không ghi đè tài liệu của các bản phát hành cũ nếu người dùng cần tra cứu lịch sử.
- **Để lỗi docs ảnh hưởng build khi cần.** Với thư viện phát hành công khai, tài liệu API thường là một phần của artifact và phải được tạo thành công.

## 17. Kết luận

Task <javadoc> của Apache Ant tự động gọi công cụ Javadoc của JDK để tạo tài liệu HTML từ comment trong mã nguồn Java. Các thuộc tính như sourcepath, destdir, packagenames, access, encoding và failonerror xác định nguồn, phạm vi, đầu ra và chính sách lỗi. Nested element như packageset, classpath, link, group, tag và doclet mở rộng khả năng chọn package, phân giải dependency, liên kết API và tùy chỉnh nội dung.

Một quy trình tốt bắt đầu từ comment Javadoc rõ ràng, chọn đúng source root và package, cung cấp classpath đầy đủ, giữ encoding thống nhất và tạo docs như một bước của build/release. Khi tài liệu được sinh tự động cho từng phiên bản, người dùng có thể tra cứu API chính xác và đội ngũ phát triển giảm công việc cập nhật tài liệu thủ công.

## Tài liệu tham khảo

- [Apache Ant Javadoc Task](https://ant.apache.org/manual/Tasks/javadoc.html)
- [JDK Javadoc Tool](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html)
- [Javadoc Documentation Comment Specification](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)

