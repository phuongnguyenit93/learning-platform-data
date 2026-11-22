# Lỗi reference trong Javadoc DocLint

Trong Javadoc, *reference* là tên Java element được nhắc tới trong documentation comment: package, class, interface, constructor, method, field, parameter hoặc exception. Khi một tên sai, không tồn tại, không thể phân giải hoặc không khớp với khai báo thật, Javadoc có thể tạo liên kết sai hoặc báo lỗi.

DocLint có nhóm kiểm tra `reference` để tìm các vấn đề này. Nhóm kiểm tra bao gồm các tham chiếu trong `@see`, `{@link ...}`, `{@linkplain ...}` và những tên được khai báo trong tag như `@param` hoặc `@throws`.

Bài học dùng JDK 21 làm mốc, tập trung vào cách đọc chẩn đoán, sửa cú pháp reference, cấu hình source/class/module path và kiểm tra liên kết tới API bên ngoài.

## 1. Reference error là gì?

Reference error xảy ra khi Javadoc không xác định được phần tử mà comment muốn trỏ tới hoặc tag mô tả một phần tử không khớp với khai báo Java.

Ví dụ:

~~~java
/**
 * Finds a product.
 *
 * @see #findById(String)
 */
public Optional<Product> find(String id) {
    // ...
}
~~~

Nếu class không có method `findById(String)`, Javadoc không thể tạo liên kết đúng. Đây là lỗi reference dù chương trình Java vẫn có thể biên dịch và chạy bình thường.

Những lỗi phổ biến:

- Tên class, package, method hoặc field bị viết sai.
- Dùng tên method đúng nhưng sai danh sách kiểu tham số.
- Trỏ tới overload không tồn tại hoặc không chỉ rõ overload cần thiết.
- `@param` ghi tên khác với tham số trong khai báo.
- `@param` cho type parameter thiếu dấu ngoặc nhọn, ví dụ ghi `@param T` thay vì `@param <T>`.
- `@throws` ghi tên exception không tồn tại hoặc không phải exception có thể được method ném ra.
- Class hoặc module phụ thuộc không nằm trong source path, class path hoặc module path.
- Tham chiếu tới API bên ngoài nhưng thiếu cấu hình liên kết Javadoc tương ứng.

Một lỗi reference có thể làm Javadoc kết thúc với error, khiến build tài liệu thất bại, đặc biệt khi CI dùng `-Werror`.

## 2. Nhóm reference trong DocLint

DocLint chia kiểm tra documentation comment thành các nhóm:

| Nhóm | Nội dung |
|---|---|
| `accessibility` | Kiểm tra vấn đề accessibility như ảnh thiếu `alt` |
| `html` | Kiểm tra lỗi HTML phổ biến như thẻ block nằm trong inline hoặc thiếu thẻ đóng |
| `missing` | Kiểm tra thiếu comment hoặc tag như `@param`, `@return` |
| `reference` | Kiểm tra tham chiếu tới Java API element và tên trong các tag |
| `syntax` | Kiểm tra cú pháp Javadoc, HTML entity và tag không hợp lệ |

`reference` tập trung vào việc tên được nhắc tới có khớp với API thật hay không. Ví dụ, `{@link}` trỏ tới method không tồn tại, hoặc `@param` ghi tên tham số không có trong chữ ký method.

DocLint được bật mặc định khi chạy `javadoc`. Có thể chỉ định rõ nhóm cần kiểm tra:

~~~bash
# Chỉ kiểm tra các vấn đề reference
javadoc -Xdoclint:reference -sourcepath src -d docs com.example.catalog

# Bật toàn bộ nhóm kiểm tra
javadoc -Xdoclint:all -sourcepath src -d docs com.example.catalog

# Bật toàn bộ nhóm, trừ kiểm tra missing
javadoc -Xdoclint:all,-missing -sourcepath src -d docs com.example.catalog

# Tắt toàn bộ DocLint (không khuyến nghị trong CI)
javadoc -Xdoclint:none -sourcepath src -d docs com.example.catalog
~~~

`-Werror` biến warning thành error để build có thể thất bại khi tài liệu không đạt chính sách chất lượng:

~~~bash
javadoc -Xdoclint:all -Werror -sourcepath src -d docs com.example.catalog
~~~

Không nên tắt DocLint chỉ để che một reference sai. Hãy sửa tên đích hoặc cấu hình đường dẫn tìm kiếm để tài liệu phản ánh đúng API.

## 3. Cú pháp reference của Javadoc

Dạng tổng quát của reference tới Java element:

~~~text
module/package.Class#member
~~~

Trong đó:

- `module/` là tên module, có thể bỏ nếu ngữ cảnh đã xác định được.
- `package.` là tên package đầy đủ.
- `Class` là tên class hoặc interface, có thể là nested class.
- `#member` là constructor, method, annotation member, field hoặc enum constant.

Các phần đầu có thể bỏ khi Javadoc suy ra được từ ngữ cảnh. Khi tham chiếu member trong chính class đang viết comment, thường chỉ cần `#member`.

Ví dụ:

~~~java
/**
 * Uses {@link java.util.Optional} to represent an optional result.
 *
 * <p>Call {@link ProductCatalog#find(String)} to search active products.
 *
 * @see java.util.Map
 */
~~~

### 3.1. Tham chiếu method và overload

Nếu method không overloaded và tên không trùng field/enum constant, có thể bỏ danh sách tham số. Khi có overload, hãy ghi rõ danh sách kiểu tham số:

~~~java
/**
 * Calls {@link #find(String)} for an active product.
 * Use {@link #find(String, boolean)} to include archived products.
 */
~~~

Trong reference, ghi kiểu tham số theo thứ tự khai báo. Không ghi tên biến:

~~~java
// Đúng
{@link #find(String, boolean)}

// Sai: reference không nhận tên biến
{@link #find(String id, boolean includeArchived)}

// Sai: kiểu tham số không khớp chữ ký
{@link #find(String, int)}
~~~

Có thể dùng kiểu fully qualified khi tên đơn giản không rõ ràng:

~~~java
{@link java.util.Map#get(Object)}
{@link java.nio.file.Files#readString(java.nio.file.Path)}
~~~

Các quy tắc hữu ích:

- Dùng `String`, không dùng `java.lang.String` nếu ngữ cảnh đã rõ; cả hai cách có thể dùng khi hợp lệ.
- Dùng đúng kiểu primitive như `int`, `boolean`, `long`.
- Dùng `String[]` cho mảng.
- Dùng tên nested type như `Outer.Inner`.
- Constructor được tham chiếu bằng tên class theo sau danh sách tham số, ví dụ `{@link ProductCatalog#ProductCatalog()}`.
- Với method generic, ghi kiểu tham số thực tế theo khai báo và dùng dạng tham chiếu được Javadoc hỗ trợ.

### 3.2. Reference trong module

Khi cần chỉ rõ module, dùng dấu `/` giữa module và package:

~~~java
/**
 * Uses {@link java.base/java.util.Optional} for optional values.
 */
~~~

Điều này hữu ích khi nhiều module có package hoặc type name tương tự. Module name không thay thế package name; phần sau dấu `/` vẫn là package và class.

### 3.3. Member reference và URI fragment

Dấu `#` đơn dùng để trỏ tới member:

~~~java
{@link ProductCatalog#find(String)}
~~~

Dấu `##` dùng để trỏ tới fragment tùy ý trong trang tài liệu, chẳng hạn heading có id:

~~~java
{@link ProductCatalog##search-examples Search examples}
~~~

Không dùng `##` để thay cho `#method(...)`. Hai cú pháp có mục đích khác nhau.

## 4. Sửa lỗi trong {@link}, {@linkplain} và @see

### 4.1. {@link} và {@linkplain}

`{@link}` tạo liên kết inline với label thường hiển thị theo kiểu code:

~~~java
/**
 * Use {@link java.util.Optional#orElse(Object)} to provide a fallback.
 */
~~~

`{@linkplain}` tạo liên kết inline nhưng label hiển thị bằng font văn bản thông thường:

~~~java
/**
 * Read the {@linkplain java.util.Optional API documentation}
 * before choosing a fallback strategy.
 */
~~~

Hai tag dùng chung cú pháp reference. Nếu target sai, đổi sang `{@linkplain}` không sửa được lỗi; cần sửa phần reference.

### 4.2. @see có ba dạng

Tham chiếu tới Java element:

~~~java
/**
 * @see java.util.Optional
 * @see ProductCatalog#find(String)
 */
~~~

Liên kết HTML tới URL:

~~~java
/**
 * @see <a href="https://docs.oracle.com/">Oracle documentation</a>
 */
~~~

Văn bản thuần, không tạo link:

~~~java
/**
 * @see "Internal catalog design document"
 */
~~~

Nếu muốn link tới Java class/method, dùng reference form. Nếu muốn URL ngoài, dùng HTML anchor hoặc một link tag thích hợp. Không đặt URL web vào vị trí reference Java element rồi kỳ vọng DocLint tự hiểu đó là URL.

### 4.3. Tên class và import

Javadoc đánh giá reference trong phạm vi của compilation unit; các import của source file được tính đến khi phân giải class/interface name.

Ví dụ:

~~~java
package com.example.catalog;

import java.util.Optional;

/**
 * Returns an {@link Optional} result.
 */
public class ProductCatalog {
}
~~~

Nếu import thiếu, tên class trùng nhau hoặc reference khó đọc, hãy dùng tên fully qualified:

~~~java
{@link java.util.Optional}
~~~

Cách này cũng giúp reviewer xác định chính xác API mà comment muốn nhắc tới.

## 5. Lỗi trong @param và @throws

Không phải mọi reference error đều nằm trong `{@link}`. DocLint cũng kiểm tra tên trong các block tag.

### 5.1. @param phải khớp khai báo

Tên trong `@param` phải giống chính xác tên tham số method/constructor:

~~~java
/**
 * Finds a product by its identifier.
 *
 * @param id product identifier
 * @return matching product, if present
 */
public Optional<String> find(String id) {
    return Optional.empty();
}
~~~

Nếu method nhận `id` nhưng comment ghi `@param productId`, DocLint có thể báo tên parameter không hợp lệ.

Với generic type parameter, phải đặt tên trong dấu ngoặc nhọn:

~~~java
/**
 * Converts a value to a target type.
 *
 * @param <T> target type
 * @param value source value
 * @return converted value
 */
public <T> T convert(Object value) {
    return (T) value;
}
~~~

`@param T` là sai khi muốn mô tả type parameter `T`; phải dùng `@param <T>`.

### 5.2. @throws phải trỏ tới exception hợp lệ

Tên exception trong `@throws` phải là exception có thể được method hoặc constructor ném ra. Dùng đúng class name và mô tả điều kiện phát sinh:

~~~java
/**
 * Reads a catalog file.
 *
 * @param path path to the catalog file
 * @return file contents
 * @throws IOException if reading the file fails
 */
public String read(Path path) throws IOException {
    return Files.readString(path);
}
~~~

Nếu dùng exception trong package khác, import type hoặc ghi fully qualified name. Kiểm tra lại chữ ký và logic của method trước khi thêm tag.

Javadoc tự đưa checked exception được khai báo trong `throws` clause vào phần Throws nếu chưa có tag mô tả. Thêm `@throws` giúp giải thích điều kiện phát sinh và cách caller xử lý.

## 6. Reference target phải được tìm thấy

Reference có cú pháp đúng vẫn có thể lỗi nếu Javadoc không tìm được class hoặc module đích.

Hãy phân biệt bốn nguồn tìm kiếm:

| Tùy chọn | Dùng để tìm |
|---|---|
| `-sourcepath` / `--source-path` | Source file của package và class phụ thuộc |
| `-classpath` / `--class-path` / `-cp` | Class/JAR không phải named module |
| `--module-path` / `-p` | Named module đã biên dịch hoặc modular JAR |
| `--module-source-path` | Source tree của các module |

Ví dụ project:

~~~text
project/
├── src/
│   └── com/example/catalog/
│       ├── ProductCatalog.java
│       └── Product.java
├── lib/
│   └── validation-api.jar
└── docs/
~~~

Tạo Javadoc cho package:

~~~bash
javadoc -encoding UTF-8 \
  -sourcepath src \
  --class-path lib/validation-api.jar \
  -d docs \
  -Xdoclint:reference \
  com.example.catalog
~~~

Nếu `ProductCatalog.java` tham chiếu `validation-api.jar`, Javadoc cần tìm được type trong JAR đó. Chỉ thêm `-link` tới trang HTML của thư viện không làm JAR xuất hiện trên class path.

Trên Windows, khi có nhiều đường dẫn trong class path, dấu phân cách là dấu chấm phẩy:

~~~powershell
javadoc -sourcepath src -classpath "lib/a.jar;lib/b.jar" -d docs -Xdoclint:reference com.example.catalog
~~~

Trên Linux/macOS, dấu phân cách là dấu hai chấm:

~~~bash
javadoc -sourcepath src \
  -classpath "lib/a.jar:lib/b.jar" \
  -d docs \
  -Xdoclint:reference \
  com.example.catalog
~~~

### 6.1. Project modular

Nếu dependency là named module, đặt nó trên module path. Nếu đang tạo tài liệu cho module source, chỉ định module source path:

~~~bash
javadoc \
  --module-source-path src \
  --module-path mods \
  -d docs \
  --module com.example.catalog
~~~

Nếu module phụ thuộc không được phân giải hoặc không được đọc theo module graph, reference tới type của module đó có thể không được giải quyết. Kiểm tra `requires`, module path và module được đưa vào lệnh Javadoc.

## 7. Link tới Javadoc của thư viện bên ngoài

Có hai việc riêng biệt:

1. Làm cho Javadoc tìm thấy type để xác minh reference.
2. Tạo hyperlink từ tài liệu sinh ra tới trang Javadoc đã phát hành của thư viện đó.

Class path/module path giải quyết việc thứ nhất. `-link` và `-linkoffline` giải quyết việc thứ hai.

### 7.1. Dùng -link

`-link` nhận URL gốc của bộ Javadoc bên ngoài. Thư mục URL cần có file `element-list` hoặc `package-list` do Javadoc tạo ra.

Ví dụ liên kết tới Java SE 21 API:

~~~bash
javadoc \
  -sourcepath src \
  -d docs \
  -link https://docs.oracle.com/en/java/javase/21/docs/api/ \
  com.example.catalog
~~~

Javadoc dùng `element-list` để biết module/package nào có trong tài liệu bên ngoài và tạo URL tương ứng. URL phải trỏ tới thư mục gốc của bộ Javadoc, không trỏ thẳng tới file HTML của một class.

### 7.2. Dùng -linkoffline

Dùng `-linkoffline` khi máy build không truy cập được website hoặc file `element-list`/`package-list` được lưu ở một vị trí khác.

Cú pháp:

~~~text
-linkoffline url1 url2
~~~

- `url1`: URL được ghi vào các hyperlink trong HTML đầu ra.
- `url2`: thư mục local chứa `element-list` hoặc `package-list`.

Ví dụ:

~~~bash
javadoc \
  -sourcepath src \
  -d docs \
  -linkoffline https://docs.example.org/catalog/api/ tools/catalog-api-docs \
  com.example.catalog
~~~

Trong ví dụ, `tools/catalog-api-docs` phải chứa `element-list` hoặc `package-list` phù hợp với bộ tài liệu được liên kết.

Không dùng `-linkoffline` để thay thế `--class-path` hoặc `--module-path`. Nó chỉ cấu hình liên kết tới tài liệu HTML bên ngoài.

## 8. Đọc và xử lý thông báo DocLint

Một lỗi có thể hiển thị theo dạng:

~~~text
ProductCatalog.java:18: error: reference not found
 * {@link #find(String, int)}
           ^
~~~

Đây là thông báo minh họa; wording và vị trí caret cụ thể phụ thuộc JDK và source.

Khi gặp lỗi, xử lý theo trình tự:

1. Đọc file và số dòng được báo.
2. Xác định tag hoặc block đang chứa reference.
3. Tách reference khỏi label hiển thị. Trong `{@link reference label}`, phần trước label là target phải được phân giải.
4. So sánh target với khai báo thật: package, class, member và kiểu tham số.
5. Kiểm tra import và tên fully qualified.
6. Nếu target thuộc dependency, xác nhận source/class/module path.
7. Nếu target đã phân giải nhưng link tới trang ngoài không đúng, kiểm tra `-link`, `-linkoffline` và `element-list`.
8. Chạy lại nhóm reference rồi chạy toàn bộ DocLint.

### 8.1. Phân loại nhanh

| Thông báo/vấn đề | Kiểm tra đầu tiên |
|---|---|
| `reference not found` trong `{@link}` | Tên class/member và danh sách kiểu tham số |
| `@param` có tên không hợp lệ | Tên parameter trong method/constructor; dấu `< >` của type parameter |
| `@throws` có tên không hợp lệ | Exception class, package/import và khả năng exception được ném |
| Reference tới type trong thư viện ngoài không tìm thấy | `--class-path` hoặc `--module-path` |
| Reference hợp lệ nhưng không có hyperlink tới API ngoài | `-link`/`-linkoffline` và file `element-list`/`package-list` |
| Chỉ một overload bị lỗi | Kiểu, thứ tự và số lượng tham số của overload |

Đừng sửa bằng cách đổi label sau reference. Label chỉ là chữ hiển thị; target mới là phần quyết định liên kết.

## 9. Ví dụ hoàn chỉnh với Java 17+

Ví dụ dưới đây có hai overload để minh họa reference chính xác, `@param`, `@return` và `@throws`.

### 9.1. Cấu trúc project

~~~text
project/
└── src/
    ├── com/example/catalog/
    │   └── ProductCatalog.java
    └── com/example/app/
        └── Main.java
~~~

### 9.2. ProductCatalog.java

Tệp `src/com/example/catalog/ProductCatalog.java`:

~~~java
package com.example.catalog;

import java.util.Optional;

/**
 * Looks up products by their identifiers.
 *
 * <p>Use {@link #find(String)} to find active products.
 * Use {@link #find(String, boolean)} when archived products
 * should also be considered.
 *
 * @see java.util.Optional
 */
public final class ProductCatalog {
    private ProductCatalog() {
    }

    /**
     * Finds an active product by identifier.
     *
     * @param id product identifier; must not be blank
     * @return the product name when it exists
     * @throws IllegalArgumentException if id is null or blank
     */
    public static Optional<String> find(String id) {
        if (id == null || id.isBlank()) {
            throw new IllegalArgumentException("id must not be blank");
        }

        if (id.equals("A-100")) {
            return Optional.of("Keyboard");
        }

        return Optional.empty();
    }

    /**
     * Finds a product, optionally including archived entries.
     *
     * @param id product identifier; must not be blank
     * @param includeArchived whether archived products are eligible
     * @return the matching product name when it exists
     * @throws IllegalArgumentException if id is null or blank
     * @see #find(String)
     */
    public static Optional<String> find(
            String id, boolean includeArchived) {
        if (includeArchived && "A-099".equals(id)) {
            return Optional.of("Legacy mouse");
        }

        return find(id);
    }
}
~~~

Trong class comment, `{@link #find(String)}` trỏ tới overload một tham số; `{@link #find(String, boolean)}` trỏ tới overload hai tham số. `@param` khớp với `id` và `includeArchived`; `@throws` mô tả exception thực tế có thể phát sinh.

### 9.3. Main.java

Tệp `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.catalog.ProductCatalog;

public class Main {
    public static void main(String[] args) {
        System.out.println(
                ProductCatalog.find("A-100").orElse("not found"));

        System.out.println(
                ProductCatalog.find("A-099", true).orElse("not found"));
    }
}
~~~

### 9.4. Biên dịch và chạy

Chạy từ thư mục `project`:

~~~bash
mkdir -p out docs

javac -encoding UTF-8 -d out \
  src/com/example/catalog/ProductCatalog.java \
  src/com/example/app/Main.java

java -cp out com.example.app.Main
~~~

Stdout chính xác:

~~~text
Keyboard
Legacy mouse
~~~

### 9.5. Sinh Javadoc và kiểm tra reference

Vẫn ở thư mục `project`:

~~~bash
javadoc -encoding UTF-8 \
  -sourcepath src \
  -d docs \
  -Xdoclint:reference \
  -link https://docs.oracle.com/en/java/javase/21/docs/api/ \
  com.example.catalog
~~~

Để chạy toàn bộ nhóm kiểm tra và coi warning là lỗi:

~~~bash
javadoc -encoding UTF-8 \
  -sourcepath src \
  -d docs \
  -Xdoclint:all \
  -Werror \
  -link https://docs.oracle.com/en/java/javase/21/docs/api/ \
  com.example.catalog
~~~

Kết quả là bộ tài liệu HTML trong thư mục `docs`, bao gồm trang `docs/com/example/catalog/ProductCatalog.html`. Mở trang đó để kiểm tra hai liên kết overload, phần Parameters, Returns và Throws.

Ví dụ này sử dụng Java 17 API như `String.isBlank()` và `Optional`; lệnh Javadoc dùng cú pháp tương thích JDK 21.

## 10. Những cách sửa sai thường gặp

| Sai | Đúng | Lý do |
|---|---|---|
| `{@link #find(String, int)}` | `{@link #find(String, boolean)}` | Kiểu tham số phải khớp overload |
| `{@link #find(String id)}` | `{@link #find(String)}` | Reference nhận kiểu tham số, không nhận tên biến |
| `@param productId` khi khai báo là `String id` | `@param id` | Tên phải khớp khai báo |
| `@param T` cho generic type parameter | `@param <T>` | Type parameter phải đặt trong ngoặc nhọn |
| `@see java.util.Optional#missing()` | `@see java.util.Optional#empty()` | Member phải tồn tại |
| Chỉ thêm `-link` khi thiếu class trong JAR | Thêm JAR vào `--class-path` | External link không cung cấp dependency để phân giải type |
| Dùng URL trong `{@link https://...}` | Dùng `@see <a href="...">...</a>` hoặc HTML anchor | `{@link}` trỏ tới Java element |
| Dùng `-link` với URL tới một file HTML class | Dùng URL thư mục gốc có `element-list`/`package-list` | Javadoc cần danh sách package/module để dựng link |

## 11. Suppress reference warning có nên không?

DocLint hỗ trợ `@SuppressWarnings("doclint:reference")` trên declaration để bỏ qua thông báo thuộc nhóm reference. Ví dụ:

~~~java
@SuppressWarnings("doclint:reference")
public class LegacyAdapter {
    // ...
}
~~~

Chỉ dùng khi có lý do cụ thể và đã ghi nhận giới hạn của tài liệu. Annotation suppress chỉ ẩn thông báo; nó không sửa target sai, không tạo class còn thiếu và không làm hyperlink hoạt động.

Nếu API đích đã bị xóa, hãy cập nhật comment tới API thay thế. Nếu dependency không có trong build, hãy sửa cấu hình path. Nếu reference chỉ sai chữ ký, hãy sửa kiểu tham số. Suppression không nên là giải pháp mặc định.

## 12. Quy trình kiểm tra trong dự án

Có thể đưa kiểm tra reference vào CI theo trình tự:

1. Chọn đúng JDK mà dự án dùng để phát hành tài liệu.
2. Chạy `javadoc -Xdoclint:reference` để phát hiện lỗi liên kết Java element.
3. Xác nhận source dependency nằm trên `-sourcepath`.
4. Xác nhận JAR không modular nằm trên `--class-path`.
5. Xác nhận named module nằm trên `--module-path` và module source nằm trên `--module-source-path`.
6. Cấu hình `-link` hoặc `-linkoffline` cho external API docs.
7. Chạy `javadoc -Xdoclint:all -Werror` để kiểm tra mọi nhóm và chặn warning theo chính sách CI.
8. Mở một số trang HTML được tạo để kiểm tra hyperlink và nội dung cuối cùng.

DocLint kiểm tra comment trong source và báo vị trí gần với lỗi. Nó không phải trình xác thực đầy đủ cho toàn bộ HTML đầu ra và không tự sửa comment. Khi cần xác minh trải nghiệm người đọc, hãy kiểm tra thêm HTML được sinh bằng công cụ kiểm tra liên kết hoặc HTML validator phù hợp.

## 13. Ghi nhớ

- Nhóm `reference` của DocLint kiểm tra tên Java element được nhắc tới trong Javadoc.
- `{@link}`, `{@linkplain}` và `@see` dùng cú pháp reference; overload cần danh sách kiểu tham số chính xác.
- `@param` phải khớp tên tham số; generic type parameter dùng `@param <T>`.
- `@throws` phải mô tả exception hợp lệ có thể được method/constructor ném ra.
- `-sourcepath`, `--class-path` và `--module-path` giúp Javadoc tìm source/type dependency.
- `-link` và `-linkoffline` tạo hyperlink tới Javadoc bên ngoài; chúng không thay thế class path/module path.
- Chạy `-Xdoclint:reference` khi điều tra lỗi reference và `-Xdoclint:all -Werror` trong quy trình kiểm tra tài liệu.
- Chỉ suppress khi có lý do rõ ràng; sửa reference hoặc dependency path là cách xử lý đúng.

Tài liệu tham khảo:

- [The javadoc Command — Java SE 21: DocLint and reference checks](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javadoc.html)
- [Documentation Comment Specification for the Standard Doclet — Java SE 21: References, @link, @see, @param and @throws](https://docs.oracle.com/en/java/javase/21/docs/specs/javadoc/doc-comment-spec.html)
- [The javac Command — Java SE 21: class path and module path](https://docs.oracle.com/en/java/javase/21/docs/specs/man/javac.html)