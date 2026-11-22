# Package documentation với Javadoc

Package documentation là phần mô tả ở cấp package, giúp người đọc hiểu mục đích của một nhóm class/interface và cách các kiểu phối hợp với nhau. Nó trả lời những câu hỏi rộng hơn tài liệu của từng class: package cung cấp khả năng gì, nên bắt đầu từ đâu, các thành phần liên hệ thế nào và những quy tắc nào áp dụng chung.

Trong Java, cách chuẩn để đặt tài liệu này là viết documentation comment trong tệp `package-info.java`. Công cụ `javadoc` đọc comment đó và đưa vào trang `package-summary.html` của package.

## 1. Package documentation khác class documentation như thế nào?

Mỗi cấp tài liệu có một nhiệm vụ riêng:

| Cấp tài liệu | Nơi viết | Nội dung nên tập trung |
|---|---|---|
| Module | `module-info.java` | Mục tiêu module, dependency, package được export, service được dùng/cung cấp |
| Package | `package-info.java` | Mục đích package, mô hình khái niệm, quan hệ giữa các kiểu, quy tắc chung |
| Class/interface | Tệp `.java` của kiểu | Trách nhiệm của kiểu, trạng thái, cách tạo và sử dụng |
| Constructor/method/field | Comment ngay trước thành viên | Hành vi, tham số, giá trị trả về, ngoại lệ và điều kiện |

Ví dụ, trong package `com.example.orders`:

- Tài liệu package giải thích luồng tạo đơn hàng, trạng thái đơn và quan hệ giữa `Order`, `OrderItem`, `OrderService`.
- Tài liệu `OrderService` giải thích dịch vụ cụ thể và các phương thức công khai.
- Tài liệu `OrderService.submit(...)` mô tả tham số, kết quả và lỗi có thể phát sinh.

Package comment không nên chỉ lặp lại danh sách class. Nó cần giúp người đọc hình dung cách dùng cả package như một đơn vị.

## 2. Tệp package-info.java

Cấu trúc nguồn thường đặt tệp này trong thư mục tương ứng với package:

~~~text
src/
└── com/
    └── example/
        └── text/
            ├── package-info.java
            ├── TextNormalizer.java
            └── TextValidator.java
~~~

Tệp `package-info.java` chứa documentation comment ngay trước khai báo package:

~~~java
/**
 * Provides utilities for normalizing and validating user-visible text.
 *
 * <p>The package separates normalization from validation:
 * normalization produces a canonical representation, while validation
 * checks whether the resulting text satisfies application rules.
 *
 * <h2>Usage model</h2>
 * <p>Normalize input before comparing or storing it. Apply validation
 * after normalization when a canonical representation is required.
 *
 * <h2>Related types</h2>
 * <p>{@link com.example.text.TextNormalizer} performs normalization.
 * {@link com.example.text.TextValidator} checks application constraints.
 *
 * @since 1.0
 * @see java.text.Normalizer
 */
package com.example.text;
~~~

Những điểm quan trọng:

1. Dùng comment dạng `/** ... */`, không dùng `/* ... */` hoặc `//`. Javadoc chỉ nhận documentation comment.
2. Comment phải đặt ngay trước package declaration.
3. Tên package phải khớp với package chứa các source file.
4. Câu đầu tiên nên là câu tóm tắt ngắn, đầy đủ và mô tả chính xác package.
5. Có thể dùng HTML hợp lệ, inline tag như `{@link ...}` và block tag như `@since`.
6. `package-info.java` là nơi thích hợp để giữ package annotations cùng package documentation.

JLS khuyến nghị dùng `package-info.java` thay cho tệp legacy `package.html`. Tệp này thường chỉ chứa package declaration, annotation và documentation comment; không nên đặt class hoặc logic ứng dụng vào đây.

## 3. Viết nội dung package comment có ích

Một package comment tốt cho người đọc biết package làm gì và cách dùng nó. Có thể tổ chức nội dung theo các chủ đề sau, tùy độ phức tạp của package:

### 3.1. Câu tóm tắt và mục đích

Câu đầu tiên được Javadoc sử dụng làm summary trong trang package và các trang liệt kê. Viết câu này như một mô tả độc lập:

- Tốt: "Provides classes for parsing, validating, and formatting application configuration."
- Quá chung: "This package contains some useful classes."
- Quá hẹp: "Provides the ConfigParser class."

Không đặt tiêu đề, đoạn giới thiệu dài hoặc câu mở đầu không liên quan trước câu summary. Nếu package có nhiều chức năng, nêu chức năng cốt lõi trong câu đầu và giải thích phần còn lại ở các đoạn sau.

### 3.2. Khái niệm và mô hình sử dụng

Giải thích thuật ngữ và mô hình cần biết trước khi gọi API. Ví dụ:

- Đối tượng nào là đầu vào và đối tượng nào là kết quả?
- Các class có vai trò gì trong một quy trình?
- Thứ tự gọi API có quan trọng không?
- Có trạng thái hoặc vòng đời nào cần tuân thủ?
- Package có quy tắc chung về null, thread safety, resource ownership hoặc xử lý lỗi không?

Mô tả quan hệ giữa các kiểu quan trọng, thay vì chép lại method summary từ trang class.

### 3.3. Quy tắc và hợp đồng ở cấp package

Ghi những điều áp dụng cho nhiều kiểu trong package, chẳng hạn:

- Chuẩn hóa dữ liệu trước khi so sánh.
- Quy tắc encoding, locale hoặc timezone.
- Ai chịu trách nhiệm đóng resource.
- Những object có thể được chia sẻ giữa các thread.
- Cách biểu diễn lỗi hoặc dữ liệu không hợp lệ.
- Các giới hạn, giả định và điều kiện tương thích.

Chỉ ghi các quy tắc mà người dùng API cần biết. Chi tiết triển khai nội bộ nên để trong tài liệu thiết kế riêng.

### 3.4. Ví dụ và tài liệu liên quan

Đưa một luồng sử dụng ngắn nếu nó giúp người đọc hiểu package. Với package lớn, hãy liên kết tới tutorial, architecture guide hoặc specification bên ngoài thay vì nhồi toàn bộ tài liệu vào một trang.

Có thể dùng:

- `{@link com.example.text.TextNormalizer}` để liên kết kiểu trong cùng API.
- `@see java.text.Normalizer` để tạo mục See Also.
- `@since 1.0` để ghi phiên bản package được giới thiệu.

Tài liệu package là điểm bắt đầu; tài liệu class và method vẫn chịu trách nhiệm mô tả hợp đồng chi tiết của từng API.

## 4. Các Javadoc tag dùng ở cấp package

Không phải mọi tag của Javadoc đều dùng được trong package comment.

| Tag | Dùng cho package? | Mục đích |
|---|---|---|
| `@since` | Có | Ghi phiên bản package/API được giới thiệu |
| `@see` | Có | Liên kết tới kiểu, package hoặc tài liệu liên quan |
| `{@link ...}` | Có | Tạo liên kết ngay trong đoạn mô tả |
| `{@linkplain ...}` | Có | Tạo liên kết với nhãn văn bản thường |
| `{@code ...}` | Có | Hiển thị tên API hoặc đoạn code theo font code |
| `@author` | Có | Ghi tác giả/nhóm đóng góp nếu dự án có quy ước |
| `@serial include` / `@serial exclude` | Có | Điều khiển việc đưa class trong package vào trang serialized form |
| `@param` | Không | Dùng cho tham số của class, constructor hoặc method |
| `@return` | Không | Dùng cho method |
| `@throws` | Không | Dùng cho constructor hoặc method |
| `@provides` / `@uses` | Không | Dùng trong documentation comment của module |

### 4.1. Liên kết kiểu và thành viên

Ví dụ:

~~~java
/**
 * This package uses {@link java.util.Optional} to represent
 * values that may be absent.
 *
 * <p>See {@link java.util.Objects#requireNonNull(Object)}
 * when a non-null argument is required.
 *
 * @see java.util.function.Function
 * @since 2.0
 */
package com.example.mapping;
~~~

Khi tài liệu tham chiếu API bên ngoài không được tạo trong cùng lần chạy, có thể dùng tùy chọn `-link` hoặc `-linkoffline` để tạo external links tới bộ Javadoc đã phát hành.

### 4.2. Package serialization

Nếu package chứa class serializable, `@serial include` hoặc `@serial exclude` có thể điều khiển việc đưa class vào trang serialized form:

~~~java
/**
 * Provides internal implementation types for the persistence layer.
 *
 * @serial exclude
 */
package com.example.persistence.internal;
~~~

Tag ở cấp class có thể ghi đè quy tắc `@serial` ở cấp package. Chỉ dùng tag này khi dự án thực sự tạo và duy trì serialized-form documentation.

### 4.3. Không dùng tag sai vị trí

Ví dụ, `@param` và `@return` không có ý nghĩa trong package comment vì package không phải method hay constructor. Đặt tag sai ngữ cảnh có thể khiến DocLint báo lỗi hoặc tạo tài liệu không như mong đợi.

Các tag `@provides` và `@uses` mô tả service dependency của module, nên đặt trong comment của `module-info.java`.

## 5. Package annotations trong package-info.java

Ngoài tài liệu, `package-info.java` có thể khai báo annotation cho package. Đây là một trong những lý do quan trọng để ưu tiên file này thay cho `package.html`.

Annotation dùng trên package phải khai báo `@Target(ElementType.PACKAGE)`. Với một package, chỉ được có tối đa một annotated package declaration. Nếu cần đọc annotation khi chạy, annotation type phải dùng `@Retention(RetentionPolicy.RUNTIME)`.

Ví dụ annotation:

~~~java
package com.example.text;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Associates a package with a short descriptive label.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackageLabel {
    /**
     * Returns the label assigned to the package.
     *
     * @return the package label
     */
    String value();
}
~~~

Kết hợp annotation và documentation trong `package-info.java`:

~~~java
/**
 * Provides small utilities for normalizing application text.
 *
 * <p>Use these utilities before comparing or storing user input.
 *
 * @since 1.0
 * @see java.text.Normalizer
 */
@PackageLabel("text utilities")
package com.example.text;
~~~

### 5.1. Đọc package annotation ở runtime

Annotation có retention là `RUNTIME` được lưu trong `package-info.class`. Có thể truy cập thông qua `Package` của một class thuộc package:

~~~java
Package pkg = TextNormalizer.class.getPackage();
PackageLabel label = pkg.getAnnotation(PackageLabel.class);
~~~

Nếu package không có annotation tương ứng hoặc annotation không được giữ ở runtime, kết quả có thể là `null`. Hãy kiểm tra null trước khi sử dụng.

Ví dụ:

~~~java
if (label != null) {
    System.out.println(label.value());
}
~~~

Package annotation là metadata của package. Nó không thay thế Javadoc comment và không tự tạo nội dung mô tả package.

## 6. package.html và doc-files

### 6.1. package.html — cách cũ

Vì lý do tương thích lịch sử, Javadoc vẫn hỗ trợ `package.html` trong thư mục source của package. Nội dung tài liệu là phần nằm giữa thẻ `<body>` và `</body>`:

~~~html
<html>
<body>
<p>Provides utilities for parsing application configuration.</p>
<p>The package supports loading, validation, and conversion.</p>
</body>
</html>
~~~

Các điểm cần nhớ:

- `package.html` chỉ chứa nội dung HTML và Javadoc tags; không khai báo package annotation.
- Tham chiếu tới kiểu Java trong file này nên dùng tên fully qualified.
- Chọn `package-info.java` cho dự án mới hoặc khi cần package annotations.
- Khi chuyển từ `package.html` sang `package-info.java`, gom nội dung vào một nguồn tài liệu duy nhất để tránh trùng lặp và lệch nội dung.

### 6.2. doc-files — tài liệu bổ sung

Nếu package cần sơ đồ, ảnh, ví dụ HTML hoặc tài liệu bổ trợ, đặt chúng trong thư mục `doc-files` cạnh source file:

~~~text
src/
└── com/example/text/
    ├── package-info.java
    ├── TextNormalizer.java
    └── doc-files/
        ├── normalization-flow.svg
        └── usage-guide.html
~~~

Standard Doclet sao chép tài liệu trong `doc-files` sang thư mục output tương ứng của package. Có thể liên kết từ package comment bằng đường dẫn tương đối, ví dụ:

~~~html
<p><a href="doc-files/usage-guide.html">Usage guide</a></p>
<img src="doc-files/normalization-flow.svg"
     alt="Text normalization flow">
~~~

Nếu có các thư mục con bên trong `doc-files`, dùng `-docfilessubdirs` để yêu cầu Javadoc sao chép đệ quy. Với ảnh, luôn cung cấp `alt` text để tài liệu dễ truy cập.

## 7. Tạo package documentation bằng javadoc

Cú pháp tổng quát:

~~~text
javadoc [options] [packagenames] [sourcefiles] [@argfiles]
~~~

Một lệnh cơ bản để tạo tài liệu cho package `com.example.text`:

~~~bash
javadoc -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  -Xdoclint:all \
  com.example.text
~~~

Ý nghĩa:

- `-encoding UTF-8` chỉ định encoding của source files được đọc.
- `-d docs` chỉ định thư mục lưu HTML output.
- `-sourcepath src` chỉ định source root để Javadoc tìm package.
- `-Xdoclint:all` bật các nhóm kiểm tra tài liệu.
- `com.example.text` là package được tạo documentation.

Có thể tạo tài liệu cho toàn bộ package con bên dưới `com.example`:

~~~bash
javadoc -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  -subpackages com.example
~~~

`-subpackages` duyệt đệ quy package con. Nó hữu ích khi dự án có thêm package mới và muốn đưa chúng vào lần sinh tài liệu tiếp theo. Có thể kết hợp `-exclude` để bỏ các package không thuộc tài liệu công khai.

### 7.1. Điều chỉnh phạm vi API

Mặc định Javadoc tạo tài liệu cho public và protected API. Các lựa chọn thường gặp:

| Tùy chọn | Phạm vi |
|---|---|
| `-public` | Chỉ public |
| `-protected` | Public và protected; mặc định |
| `-package` | Thêm package-private |
| `-private` | Tất cả thành viên, kể cả private |

Đối với API phát hành cho người dùng thư viện, nên chọn phạm vi phù hợp với hợp đồng công khai. Tài liệu nội bộ có thể dùng `-private` nếu thực sự cần, nhưng phải phân biệt rõ với API cam kết hỗ trợ.

### 7.2. Tạo tài liệu cho module

Với dự án modular, module có thể có comment riêng trong `module-info.java` và từng package có comment trong `package-info.java`.

Ví dụ:

~~~bash
javadoc --module-source-path src \
  -d docs \
  --module com.example.library
~~~

Trong đó `src` là module source path. Javadoc tạo trang module summary và trang package summary riêng. Tài liệu module mô tả dependency/service/export; tài liệu package mô tả cách sử dụng các kiểu trong từng package.

## 8. Kết quả được tạo ra

Với package không nằm trong named module, cấu trúc output có thể như sau:

~~~text
docs/
├── index.html
├── allpackages-index.html
├── help-doc.html
└── com/
    └── example/
        └── text/
            ├── package-summary.html
            ├── PackageLabel.html
            ├── TextNormalizer.html
            └── doc-files/
                ├── normalization-flow.svg
                └── usage-guide.html
~~~

`package-summary.html` là trang tổng quan của package. Nó chứa danh sách các kiểu được tài liệu hóa và phần mô tả package lấy từ `package-info.java`.

Nếu package thuộc named module, cây thư mục output được đặt dưới thư mục của module, ví dụ:

~~~text
docs/
└── com.example.library/
    └── com/
        └── example/
            └── text/
                └── package-summary.html
~~~

Không nhầm trang package summary với trang class: package summary giúp chọn kiểu và hiểu mô hình chung; trang class chứa mô tả chi tiết về một kiểu.

## 9. Thực hành hoàn chỉnh với Java 17+

Ta tạo package `com.example.text` có package documentation và runtime package annotation.

### 9.1. Cấu trúc project

~~~text
project/
└── src/
    ├── com/example/text/
    │   ├── package-info.java
    │   ├── PackageLabel.java
    │   └── TextNormalizer.java
    └── com/example/app/
        └── Main.java
~~~

### 9.2. Tạo annotation PackageLabel

Tệp `src/com/example/text/PackageLabel.java`:

~~~java
package com.example.text;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;

/**
 * Associates a package with a short descriptive label.
 */
@Documented
@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.PACKAGE)
public @interface PackageLabel {
    /**
     * Returns the label assigned to the package.
     *
     * @return the package label
     */
    String value();
}
~~~

### 9.3. Tạo package-info.java

Tệp `src/com/example/text/package-info.java`:

~~~java
/**
 * Provides utilities for trimming and preparing application text.
 *
 * <p>The package offers a small normalization API that can be used
 * before validating or comparing user input.
 *
 * <h2>Usage model</h2>
 * <p>Call {@link TextNormalizer#trim(String)} before applying
 * application-specific validation rules.
 *
 * @since 1.0
 * @see java.text.Normalizer
 */
@PackageLabel("text utilities")
package com.example.text;
~~~

### 9.4. Tạo class TextNormalizer

Tệp `src/com/example/text/TextNormalizer.java`:

~~~java
package com.example.text;

/**
 * Provides basic text-normalization operations.
 */
public final class TextNormalizer {
    private TextNormalizer() {
    }

    /**
     * Removes leading and trailing whitespace.
     *
     * @param text the input text; null is treated as an empty string
     * @return the trimmed text, or an empty string if text is null
     */
    public static String trim(String text) {
        return text == null ? "" : text.strip();
    }
}
~~~

### 9.5. Tạo chương trình Main

Tệp `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.text.PackageLabel;
import com.example.text.TextNormalizer;

public class Main {
    public static void main(String[] args) {
        Package pkg = TextNormalizer.class.getPackage();
        PackageLabel label = pkg.getAnnotation(PackageLabel.class);

        if (label == null) {
            throw new IllegalStateException("Package annotation is missing");
        }

        System.out.println("Package: " + pkg.getName());
        System.out.println("Label: " + label.value());
        System.out.println("Normalized: [" + TextNormalizer.trim("  Java  ") + "]");
    }
}
~~~

### 9.6. Biên dịch và chạy

Chạy từ thư mục `project`:

~~~bash
mkdir -p out docs

javac -encoding UTF-8 -d out \
  src/com/example/text/PackageLabel.java \
  src/com/example/text/package-info.java \
  src/com/example/text/TextNormalizer.java \
  src/com/example/app/Main.java

java -cp out com.example.app.Main
~~~

Stdout chính xác:

~~~text
Package: com.example.text
Label: text utilities
Normalized: [Java]
~~~

Ví dụ xác nhận package annotation có thể được đọc qua `Package` khi annotation được giữ ở runtime. Tệp `package-info.java` cũng chứa documentation comment để Javadoc tạo package summary.

### 9.7. Sinh tài liệu HTML

Vẫn ở thư mục `project`:

~~~bash
javadoc -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  -Xdoclint:all \
  com.example.text
~~~

Sau khi lệnh hoàn tất, mở:

~~~text
docs/com/example/text/package-summary.html
~~~

Kiểm tra câu summary, mô tả package, liên kết tới `TextNormalizer`, mục `Since` và các phần mô tả khác. Có thể mở trang class để xác nhận tài liệu method cũng được tạo.

## 10. Kiểm tra chất lượng package documentation

Javadoc có DocLint để phát hiện nhiều lỗi thường gặp trong comment. Trong JDK 21, DocLint được bật mặc định; có thể chỉ định rõ:

~~~bash
javadoc -Xdoclint:all -Werror \
  -encoding UTF-8 \
  -d docs \
  -sourcepath src \
  com.example.text
~~~

`-Werror` chuyển warning thành lỗi, hữu ích trong CI khi dự án muốn giữ chất lượng tài liệu ổn định.

DocLint có các nhóm kiểm tra:

| Nhóm | Nội dung |
|---|---|
| `html` | Cấu trúc HTML sai hoặc thiếu thẻ đóng |
| `syntax` | Cú pháp Javadoc, ký tự `<`, `>` hoặc `&` chưa escape đúng |
| `reference` | `{@link}` hoặc `@see` trỏ tới phần tử không tồn tại |
| `missing` | Thiếu documentation comment hoặc tag cần thiết |
| `accessibility` | Vấn đề accessibility như ảnh thiếu `alt` hoặc bảng thiếu caption |

DocLint không thay thế việc đọc lại tài liệu đã sinh. Nó kiểm tra các lỗi phổ biến trong comment, nhưng không thể quyết định nội dung có chính xác, dễ hiểu hoặc đầy đủ đối với người dùng API hay không.

Checklist kiểm tra trước khi phát hành:

- Câu đầu tiên mô tả đúng mục đích package.
- Nội dung giải thích mô hình và quan hệ giữa các kiểu quan trọng.
- Các quy tắc chung về dữ liệu, thread safety, resource và lỗi được nêu khi có liên quan.
- Các liên kết tới class/package/method hoạt động.
- Block tag được dùng đúng ngữ cảnh.
- HTML hợp lệ và heading bắt đầu ở cấp phù hợp.
- Ví dụ có thể biên dịch/chạy nếu được trình bày như ví dụ hoàn chỉnh.
- Các subpackage quan trọng cũng có package documentation riêng.
- Trang `package-summary.html` được mở và đọc thử sau khi tạo.

## 11. Lỗi thường gặp

| Hiện tượng | Nguyên nhân | Cách xử lý |
|---|---|---|
| Không có phần mô tả package | Thiếu `package-info.java` hoặc comment không đặt ngay trước package declaration | Tạo đúng file và dùng `/** ... */` |
| Trang package summary chỉ có danh sách class | Package comment rỗng hoặc package không được đưa vào lần chạy Javadoc | Kiểm tra `-sourcepath` và package name trên command line |
| Javadoc không tìm thấy package | Source root hoặc package directory sai | Đặt `-sourcepath` về thư mục gốc chứa package tree |
| Link trong package page bị lỗi | Sai tên class/member hoặc thiếu external link | Sửa `{@link}`/`@see` và kiểm tra `-link` nếu tham chiếu API ngoài |
| Comment hiển thị thành HTML sai | HTML thiếu thẻ đóng hoặc dùng cú pháp không hợp lệ | Sửa HTML và chạy `-Xdoclint:all` |
| Summary bị cắt ở câu đầu không đúng | Câu đầu có dấu chấm gây nhầm ranh giới câu | Viết summary đơn giản, tránh abbreviation không cần thiết |
| Annotation package không đọc được lúc chạy | Thiếu `@Target(PACKAGE)` hoặc retention không phải RUNTIME | Kiểm tra annotation declaration và package-info.class |
| Có annotation package nhưng không thấy ở package khác | Đang kiểm tra sai class loader hoặc sai runtime package | Dùng class thuộc đúng package/code source để lấy `Package` |
| Tài liệu của package con bị thiếu | Chỉ chỉ định package cha, không dùng `-subpackages` | Thêm package con hoặc dùng `-subpackages` |
| Ảnh hoặc hướng dẫn phụ không xuất hiện | Tệp đặt sai vị trí hoặc đường dẫn tương đối sai | Đặt trong `doc-files` cạnh source package và kiểm tra output |

## 12. Ghi nhớ

`package-info.java` là nơi chuẩn để viết package documentation và package annotations. Comment đặt trước package declaration; câu đầu tiên là summary sentence, sau đó mô tả mục đích, mô hình, quan hệ giữa các kiểu và những quy tắc áp dụng chung. Javadoc dùng nội dung đó để tạo `package-summary.html`.

`package.html` vẫn được hỗ trợ vì lý do tương thích lịch sử, nhưng `package-info.java` phù hợp hơn cho dự án mới và cho package annotations. Dùng `doc-files` để bổ sung hình ảnh hoặc tài liệu dài; dùng `javadoc` với `-sourcepath`, `-d` và `-subpackages` để tạo tài liệu; chạy DocLint và kiểm tra HTML được sinh trước khi phát hành.

Tài liệu tham khảo:

- [The javadoc Command — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html)
- [Documentation Comment Specification for the Standard Doclet — JDK 21](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
- [Java Language Specification, Java SE 21 — §7.4 Package Declarations](https://docs.oracle.com/javase/specs/jls/se21/jls21.pdf)
- [java.lang.Package API — Java SE 21](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Package.html)
- [How to Write Doc Comments for the Javadoc Tool — Oracle](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html)