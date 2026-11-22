# Tạo API documentation bằng Javadoc

Javadoc là công cụ trong JDK dùng để tạo tài liệu API từ mã nguồn Java. Công cụ đọc **documentation comment** đặt trước khai báo package, module, class, interface, record, constructor, field và method; sau đó tạo tài liệu HTML gồm trang tổng quan, package, type, member, chỉ mục và liên kết giữa các API.

API documentation giúp người dùng thư viện hiểu API dùng để làm gì, cách gọi và ý nghĩa tham số, kết quả trả về, exception có thể phát sinh, điều kiện đầu vào, giới hạn, tác dụng phụ, phiên bản xuất hiện và trạng thái deprecated. Tài liệu tốt mô tả hợp đồng mà người gọi có thể dựa vào, khớp với hành vi thực tế và được kiểm tra trong quy trình build.

Toolchain dùng để kiểm tra bài này báo `javadoc 24.0.2`. Các tùy chọn có thể khác giữa các JDK; kiểm tra `javadoc --version`, `javadoc --help` và `javadoc --help-extra` của môi trường build thực tế.

## 1. Javadoc hoạt động như thế nào?

Documentation comment là comment Java mở đầu bằng dấu slash và hai dấu sao (`/**`). Javadoc đọc comment gắn với khai báo và phân tích tag như `@param`, `@return`, `@throws`, `@see`, `@since` và `@deprecated`. Standard doclet của JDK chuyển nội dung thành HTML.

Ví dụ:

~~~java
/**
 * Represents a product in the catalog.
 */
public final class Product {
}
~~~

Luồng cơ bản:

~~~text
Java source files
      |
      v
Documentation comments
      |
      v
     javadoc
      |
      +--> Parse declarations and tags
      +--> Resolve links and references
      +--> Check HTML and documentation rules
      |
      v
Generated API documentation (HTML)
~~~

Javadoc không chạy chương trình để suy ra ý nghĩa API và không tự biết mọi quy tắc nghiệp vụ. Người viết phải mô tả chính xác hành vi, điều kiện và giới hạn của API.

## 2. Cấu trúc documentation comment

Một comment thường có hai phần:

1. **Description:** phần mô tả chính, viết trước block tag.
2. **Block tags:** phần thông tin có cấu trúc, bắt đầu bằng `@tag`.

Ví dụ:

~~~java
/**
 * Finds a product by its SKU.
 *
 * <p>The lookup is case-sensitive and does not modify the catalog.
 *
 * @param sku the exact SKU to search for
 * @return the matching product, or an empty result if no product exists
 * @throws NullPointerException if {@code sku} is {@code null}
 * @since 1.0
 */
public Optional<Product> findBySku(String sku) {
    // ...
}
~~~

Description nên mở đầu bằng một câu ngắn nêu rõ mục đích. Javadoc dùng câu đầu để tạo summary trong trang package, trang class và bảng method. Summary cần tự đứng được khi hiển thị riêng. Sau câu đầu có thể thêm đoạn giải thích, ví dụ hoặc danh sách; block tag thường đặt sau description.

### 2.1. Viết summary tốt

Summary tốt:

~~~java
/**
 * Returns the number of products in this catalog.
 */
public int size() {
    // ...
}
~~~

Summary mơ hồ:

~~~java
/**
 * Gets the size.
 */
public int size() {
    // ...
}
~~~

Nên nói rõ giá trị được trả về hoặc hành động được thực hiện. Tránh mở đầu bằng “This method is used to...” vì không bổ sung thông tin. Nếu cần chỉ định summary rõ ràng, có thể dùng inline tag `{@summary ...}` trên JDK hỗ trợ.

## 3. Block tags thường dùng

| Tag | Dùng cho | Ý nghĩa |
|---|---|---|
| `@param name description` | Method, constructor, generic type | Mô tả tham số hoặc type parameter |
| `@return description` | Method trả về giá trị | Mô tả kết quả |
| `@throws Type description` | Method, constructor | Mô tả exception và điều kiện phát sinh |
| `@exception Type description` | Method, constructor | Tên thay thế của `@throws` |
| `@see reference` | Nhiều loại khai báo | Dẫn đến API hoặc tài liệu liên quan |
| `@since version` | API | Phiên bản đầu tiên có API |
| `@deprecated explanation` | API cũ | Lý do và API thay thế |
| `@author name` | Type/package | Tác giả; cần bật `-author` để hiển thị |
| `@version text` | Type/package | Phiên bản; cần bật `-version` |
| `@apiNote text` | API | Ghi chú cho người sử dụng |
| `@implSpec text` | Method có hợp đồng triển khai | Quy tắc implementation/subclass phải tuân theo |
| `@implNote text` | API | Ghi chú về cách triển khai |
| `@serial`, `@serialField`, `@serialData` | Serializable API | Mô tả serial form và dữ liệu serialization |

### 3.1. `@param`

Dùng cho từng tham số; tên phải khớp chính xác với khai báo:

~~~java
/**
 * Adds a product to the catalog.
 *
 * @param product the product to add
 */
public void add(Product product) {
    // ...
}
~~~

Với generic type parameter, dùng `@param <T>`:

~~~java
/**
 * Converts a value to a textual representation.
 *
 * @param <T> the value type
 * @param value the value to convert
 * @return the textual representation
 */
public static <T> String describe(T value) {
    return String.valueOf(value);
}
~~~

Với record, `@param` có thể mô tả từng record component trong documentation comment của record.

### 3.2. `@return`

Dùng cho method trả về giá trị; không dùng cho constructor hoặc method `void`.

~~~java
/**
 * Returns the number of products currently stored.
 *
 * @return the number of products
 */
public int size() {
    return products.size();
}
~~~

Nếu kết quả có thể rỗng, null hoặc mang trạng thái đặc biệt, hãy mô tả chính xác. Với `Optional<T>`, nói rõ khi nào trả về `Optional.empty()`.

### 3.3. `@throws` và `@exception`

Mô tả điều kiện gây exception, không chỉ lặp lại tên exception:

~~~java
/**
 * Finds a product by its SKU.
 *
 * @param sku the SKU to search for
 * @return the product, or an empty result if it is absent
 * @throws NullPointerException if {@code sku} is {@code null}
 */
public Optional<Product> findBySku(String sku) {
    return Optional.ofNullable(products.get(
            Objects.requireNonNull(sku, "sku")));
}
~~~

Chỉ mô tả exception mà API thực sự có thể ném trong điều kiện được nêu. Với checked exception, giải thích tình huống phát sinh và ý nghĩa để người gọi xử lý.

### 3.4. `@since` và `@deprecated`

Dùng `@since` để ghi phiên bản API được giới thiệu:

~~~java
/**
 * Returns a stable identifier for this product.
 *
 * @return the product identifier
 * @since 1.2
 */
public String id() {
    return id;
}
~~~

Khi API không còn được khuyến nghị, dùng cả annotation `@Deprecated` và block tag `@deprecated`:

~~~java
/**
 * Returns the legacy product code.
 *
 * @deprecated Use {@link #sku()} instead.
 */
@Deprecated(since = "2.0", forRemoval = true)
public String productCode() {
    return sku;
}
~~~

Annotation hỗ trợ compiler, IDE và tooling nhận biết API deprecated. Tag giải thích lý do và chỉ dẫn cách thay thế. Không chỉ ghi “deprecated”; hãy nêu API thay thế, khác biệt hành vi nếu có và kế hoạch loại bỏ nếu dự án đã công bố.

### 3.5. `@apiNote`, `@implSpec` và `@implNote`

Ba tag này tách nội dung dành cho các đối tượng đọc khác nhau:

- `@apiNote`: lưu ý cho người sử dụng API.
- `@implSpec`: hợp đồng mà implementation phải tuân theo, đặc biệt với method có thể được override.
- `@implNote`: thông tin về cách implementation cụ thể hoạt động.

~~~java
/**
 * Returns an immutable snapshot of the current products.
 *
 * @apiNote The returned list can be safely retained by the caller.
 * @implSpec The list must not reflect later changes to the catalog.
 * @implNote The current implementation copies the values into a new list.
 * @return an immutable snapshot
 */
public List<Product> snapshot() {
    return List.copyOf(products.values());
}
~~~

Chỉ ghi chi tiết triển khai khi có giá trị cho người đọc hoặc người bảo trì. Không biến `@implNote` thành nơi mô tả mọi dòng code nội bộ.

## 4. Inline tags và liên kết trong documentation

Inline tag được đặt ngay trong description hoặc block tag.

| Inline tag | Công dụng |
|---|---|
| `{@link Type#method()}` | Liên kết đến API và hiển thị tên tham chiếu |
| `{@linkplain Type#method()}` | Liên kết nhưng hiển thị văn bản thông thường |
| `{@code expression}` | Hiển thị code inline |
| `{@literal text}` | Hiển thị literal, không phân tích như HTML/tag |
| `{@value}` | Hiển thị giá trị hằng số phù hợp |
| `{@inheritDoc}` | Kế thừa documentation từ method được override |
| `{@docRoot}` | Đường dẫn tương đối đến thư mục gốc tài liệu |
| `{@snippet ...}` | Chèn code snippet; hỗ trợ từ JDK 18 |

Ví dụ:

~~~java
/**
 * Adds a product if its {@link Product#sku()} is not already present.
 *
 * <p>See {@linkplain Catalog#findBySku(String) the lookup method}.
 */
public void add(Product product) {
    // ...
}
~~~

Dùng `{@code}` cho tên biến, biểu thức, lệnh và code ngắn. Dùng `{@literal}` khi muốn hiển thị dấu ngoặc nhọn hoặc chuỗi có thể bị hiểu là HTML/Javadoc tag.

### 4.1. Link đến member cụ thể

Có thể liên kết class, constructor, field hoặc method:

~~~text
{@link Product}
{@link Product#sku()}
{@link Product#Product(String, String)}
{@link Catalog#findBySku(String)}
~~~

Khi có overload, ghi tham số để liên kết đúng method. Với API ở package khác, có thể dùng tên đầy đủ hoặc qualified reference phù hợp.

### 4.2. `{@value}` cho hằng số

~~~java
/**
 * Default maximum number of results.
 */
public static final int DEFAULT_LIMIT = 50;

/**
 * Returns the default result limit, currently {@value #DEFAULT_LIMIT}.
 *
 * @return the default limit
 */
public int defaultLimit() {
    return DEFAULT_LIMIT;
}
~~~

`{@value}` hữu ích khi giá trị hằng số cần hiển thị ngay trong lời giải thích. Không dùng cho field không phải constant phù hợp.

### 4.3. `{@inheritDoc}` cho method override

Khi override method, có thể kế thừa phần mô tả từ method cha hoặc interface:

~~~java
/**
 * {@inheritDoc}
 *
 * <p>This implementation performs the lookup in memory.
 */
@Override
public Optional<Product> findBySku(String sku) {
    // ...
}
~~~

`{@inheritDoc}` tránh lặp lại hợp đồng đã được định nghĩa ở API cha. Nếu implementation có thêm giới hạn hoặc hành vi cụ thể, bổ sung phần giải thích riêng.

### 4.4. Code snippet với `{@snippet}`

JDK 18+ hỗ trợ snippet tag trong documentation comment:

~~~java
/**
 * Creates a catalog and looks up a product:
 *
 * {@snippet :
 * Catalog catalog = new Catalog(List.of(product));
 * Optional<Product> result = catalog.findBySku("A-100");
 * }
 */
public final class Catalog {
}
~~~

Với ví dụ dài, có thể lưu snippet trong file riêng rồi cấu hình `--snippet-path`. Cách này giúp dùng lại ví dụ và kiểm tra chúng độc lập. Đảm bảo snippet thể hiện đúng API hiện tại.

## 5. Viết Javadoc cho class, interface, record, constructor và method

### 5.1. Class và interface

Documentation của type nên giải thích vai trò và trách nhiệm chính, cách tạo hoặc lấy instance, các bất biến mà type duy trì, cách tương tác với type liên quan, thread-safety và mutability nếu người dùng cần biết, cùng điều kiện sử dụng hoặc giới hạn đáng chú ý.

~~~java
/**
 * Provides lookup operations for a collection of products.
 *
 * <p>A catalog rejects duplicate SKUs and exposes immutable lookup results.
 *
 * @since 1.0
 */
public final class Catalog {
}
~~~

### 5.2. Constructor

Constructor cần mô tả object được khởi tạo ra sao, tham số, điều kiện đầu vào và exception:

~~~java
/**
 * Creates a catalog containing the supplied products.
 *
 * @param products initial products; the collection must not be {@code null}
 * @throws NullPointerException if the collection or an element is {@code null}
 * @throws IllegalArgumentException if two products have the same SKU
 */
public Catalog(Collection<Product> products) {
    // ...
}
~~~

Không ghi `@return` cho constructor.

### 5.3. Method

Method cần mô tả hành động, tham số, kết quả, exception và side effect:

~~~java
/**
 * Removes a product from the catalog.
 *
 * @param sku the SKU of the product to remove
 * @return {@code true} if a product was removed; {@code false} if none matched
 * @throws NullPointerException if {@code sku} is {@code null}
 */
public boolean remove(String sku) {
    // ...
}
~~~

Nếu method sửa trạng thái, có I/O, blocking, retry, cache, callback hoặc concurrency behavior, hãy mô tả điều đó khi nó ảnh hưởng đến người gọi.

### 5.4. Field và generic type

Field public/protected là một phần API. Cần mô tả ý nghĩa, đơn vị, phạm vi giá trị và mutability nếu có:

~~~java
/**
 * Default maximum number of products returned by a search.
 */
public static final int DEFAULT_LIMIT = 50;
~~~

Khi API dùng generic, mô tả ý nghĩa type parameter:

~~~java
/**
 * Maps an input value to a result.
 *
 * @param <I> the input type
 * @param <O> the output type
 */
public interface Mapper<I, O> {

    /**
     * Converts one input value.
     *
     * @param input the value to convert
     * @return the converted value
     */
    O map(I input);
}
~~~

Tên type parameter nên có ý nghĩa như `T`, `K`, `V`, `I`, `O` tùy ngữ cảnh; documentation phải giải thích vai trò của chúng khi không hiển nhiên.

## 6. Tài liệu package và module

API không chỉ gồm từng class. Package và module documentation giúp người đọc hiểu cách các type kết hợp với nhau.

### 6.1. `package-info.java`

Tạo `package-info.java` trong thư mục package:

~~~java
/**
 * Public API for product catalog lookup and management.
 *
 * <p>Use {@link com.example.catalog.Catalog} to search products and
 * {@link com.example.catalog.Product} to represent catalog entries.
 *
 * @since 1.0
 */
package com.example.catalog;
~~~

`package-info.java` có thể chứa package documentation và package annotations. Javadoc dùng nội dung này cho trang tổng quan package. Nếu package có nhiều type, hãy giải thích vai trò chung, quy tắc phối hợp và điểm bắt đầu mà người dùng nên đọc.

### 6.2. `module-info.java`

Với named module, có thể đặt documentation comment trước khai báo module:

~~~java
/**
 * Provides the product catalog API.
 *
 * <p>The module exports the public catalog package.
 */
module com.example.catalog {
    exports com.example.catalog;
}
~~~

Khi tạo tài liệu module, dùng các tùy chọn như `--module-path`, `--module-source-path` và `--module`. Các tùy chọn hiển thị module/package/type quyết định mức chi tiết tài liệu.

### 6.3. Trang tổng quan bằng `overview.html`

Có thể tạo file HTML tổng quan riêng và truyền bằng `-overview`:

~~~text
javadoc -overview overview.html -d docs -sourcepath src -subpackages com.example
~~~

Trang overview phù hợp để giới thiệu thư viện, mục tiêu, package chính, ví dụ bắt đầu nhanh và liên kết đến hướng dẫn ngoài API reference.

## 7. Tạo API documentation bằng lệnh `javadoc`

Cú pháp tổng quát:

~~~text
javadoc [options] [packagenames] [sourcefiles] [@files]
~~~

Các tùy chọn thường dùng:

| Tùy chọn | Công dụng |
|---|---|
| `-d directory` | Thư mục chứa HTML đầu ra |
| `-sourcepath path` | Gốc cây source |
| `-subpackages package` | Đệ quy tạo tài liệu cho package và subpackage |
| `-classpath path` / `--class-path` | Tìm class phụ thuộc |
| `--module-path path` | Tìm module |
| `--module module` | Chỉ định module cần tạo tài liệu |
| `--release version` | Mức tương thích source/API nền tảng |
| `-encoding UTF-8` | Encoding của source |
| `-docencoding UTF-8` | Encoding của HTML output |
| `-charset UTF-8` | Charset khai báo trong tài liệu |
| `-private` | Hiển thị cả thành viên private |
| `-protected` | Hiển thị protected/public; đây là mặc định |
| `-public` | Chỉ hiển thị public |
| `-author` | Hiển thị `@author` |
| `-version` | Hiển thị `@version` |
| `-link URL` | Liên kết đến Javadoc bên ngoài |
| `-linkoffline URL PATH` | Liên kết ngoài khi metadata có sẵn offline |
| `-overview file` | Thêm trang overview |
| `-windowtitle text` | Tiêu đề cửa sổ/trình duyệt |
| `-quiet` | Giảm status message |
| `-verbose` | In chi tiết hoạt động |

### 7.1. Tạo tài liệu cho package

Với cấu trúc:

~~~text
project/
  src/
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
  docs/
~~~

Chạy từ thư mục gốc `project`:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -d docs -sourcepath src -subpackages com.example.catalog
~~~

Javadoc tìm source trong `src`, lấy package `com.example.catalog` cùng các subpackage, rồi tạo HTML trong `docs`.

Nếu chỉ muốn tạo tài liệu cho một số file, truyền trực tiếp source file:

~~~text
javadoc --release 17 -d docs -sourcepath src src/com/example/catalog/Product.java src/com/example/catalog/Catalog.java
~~~

Khi dùng cách truyền file trực tiếp, hãy bảo đảm type phụ thuộc và package documentation có thể được tìm thấy qua source path/classpath phù hợp.

### 7.2. Kiểm tra HTML được sinh

Sau khi chạy thành công, mở `docs/index.html`. Các file thường gặp:

- `index.html`: trang tổng quan.
- Trang package index: danh sách package.
- `com/example/catalog/package-summary.html`: tài liệu package.
- `com/example/catalog/Catalog.html`: trang class.
- `index-all.html`: chỉ mục thành viên khi được tạo.
- `element-list`: danh sách module/package dùng cho liên kết Javadoc.
- CSS, JavaScript, search index và các trang hỗ trợ của standard doclet.

Tên và tập file cụ thể có thể thay đổi theo JDK và tùy chọn doclet. Kiểm tra trang index, trang package, trang type và các liên kết member thay vì chỉ xác nhận thư mục `docs` tồn tại.

## 8. Ví dụ hoàn chỉnh: tạo tài liệu API cho thư viện catalog

Ví dụ dùng Java 17, có package documentation, hai public class, constructor, method, link và tag chuẩn.

Cấu trúc:

~~~text
project/
  src/
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
  docs/
~~~

### 8.1. `package-info.java`

~~~java
/**
 * Public API for product catalog lookup and management.
 *
 * <p>Use {@link com.example.catalog.Catalog} to search products and
 * {@link com.example.catalog.Product} to represent catalog entries.
 *
 * @since 1.0
 */
package com.example.catalog;
~~~

### 8.2. `Product.java`

~~~java
package com.example.catalog;

import java.util.Objects;

/**
 * Represents a product identified by a stock keeping unit (SKU).
 *
 * <p>The SKU and display name are immutable after construction.
 *
 * @since 1.0
 */
public final class Product {
    private final String sku;
    private final String name;

    /**
     * Creates a product.
     *
     * @param sku the non-blank stock keeping unit
     * @param name the non-blank display name
     * @throws NullPointerException if {@code sku} or {@code name} is {@code null}
     * @throws IllegalArgumentException if either value is blank
     */
    public Product(String sku, String name) {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        if (sku.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("sku and name must not be blank");
        }
        this.sku = sku;
        this.name = name;
    }

    /**
     * Returns this product's SKU.
     *
     * @return the stock keeping unit
     */
    public String sku() {
        return sku;
    }

    /**
     * Returns this product's display name.
     *
     * @return the display name
     */
    public String name() {
        return name;
    }
}
~~~

### 8.3. `Catalog.java`

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * Provides lookup operations for products.
 *
 * <p>A catalog is immutable after construction. Each SKU is unique.
 *
 * @apiNote Use {@link #findBySku(String)} to look up a product.
 * @since 1.0
 */
public final class Catalog {
    private final Map<String, Product> products;

    /**
     * Creates a catalog from the supplied products.
     *
     * @param initialProducts products to add to the catalog
     * @throws NullPointerException if the collection or an element is {@code null}
     * @throws IllegalArgumentException if two products have the same SKU
     */
    public Catalog(Collection<Product> initialProducts) {
        Objects.requireNonNull(initialProducts, "initialProducts");
        Map<String, Product> index = new HashMap<>();
        for (Product product : initialProducts) {
            Objects.requireNonNull(product, "product");
            if (index.putIfAbsent(product.sku(), product) != null) {
                throw new IllegalArgumentException(
                        "duplicate SKU: " + product.sku());
            }
        }
        this.products = Map.copyOf(index);
    }

    /**
     * Finds a product by its exact SKU.
     *
     * <p>The lookup is case-sensitive and does not modify this catalog.
     *
     * @param sku the SKU to search for
     * @return the matching product, or {@link Optional#empty()} if no product exists
     * @throws NullPointerException if {@code sku} is {@code null}
     * @see Product#sku()
     * @since 1.0
     */
    public Optional<Product> findBySku(String sku) {
        return Optional.ofNullable(
                products.get(Objects.requireNonNull(sku, "sku")));
    }

    /**
     * Returns the number of products in this catalog.
     *
     * @return the number of products
     */
    public int size() {
        return products.size();
    }
}
~~~

### 8.4. Tạo HTML và kiểm tra lỗi documentation

Từ thư mục `project`, chạy:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.catalog
~~~

Giải thích:

- `--release 17`: kiểm tra source theo release Java 17.
- `-encoding UTF-8`: đọc source theo UTF-8.
- `-docencoding UTF-8` và `-charset UTF-8`: tạo HTML khai báo encoding phù hợp.
- `-Xdoclint:all`: bật các nhóm kiểm tra documentation.
- `-Werror`: biến warning thành lỗi để build thất bại nếu còn warning.
- `-d docs`: ghi tài liệu HTML vào thư mục `docs`.
- `-sourcepath src`: chỉ định gốc source.
- `-subpackages com.example.catalog`: tạo tài liệu cho package và subpackage.

Sau khi lệnh hoàn tất, mở:

~~~text
docs/index.html
docs/com/example/catalog/package-summary.html
docs/com/example/catalog/Product.html
docs/com/example/catalog/Catalog.html
~~~

Trang `Catalog.html` phải có mô tả class, constructor, `findBySku(String)`, `size()`, tham số, return, throws và liên kết đến `Product#sku()`. Ví dụ này dùng `Map.copyOf` và `Optional`, đều có trong Java 17. Các đoạn source được trình bày riêng theo từng file; hãy lưu đúng tên file/package trước khi chạy lệnh.

## 9. Doclint: kiểm tra chất lượng tài liệu

Doclint giúp phát hiện lỗi trong documentation comment và HTML. Dùng:

~~~text
javadoc -Xdoclint:all -d docs -sourcepath src -subpackages com.example
~~~

Các nhóm kiểm tra thường gặp:

| Nhóm | Nội dung |
|---|---|
| `accessibility` | Một số vấn đề về khả năng truy cập |
| `html` | HTML không hợp lệ hoặc cấu trúc HTML sai |
| `missing` | Thiếu documentation hoặc tag theo phạm vi kiểm tra |
| `reference` | Tham chiếu đến type/member không hợp lệ |
| `syntax` | Cú pháp documentation comment và tag |

Có thể bật/tắt nhóm:

~~~text
javadoc -Xdoclint:all,-missing -d docs -sourcepath src -subpackages com.example
~~~

`-Xdoclint` là tùy chọn nâng cao của standard doclet; nhóm và hành vi chi tiết có thể thay đổi giữa các JDK. Kiểm tra `javadoc --help-extra` của toolchain đang dùng.

### 9.1. Biến warning thành lỗi

Kết hợp `-Werror` để ngăn build phát hành khi còn warning:

~~~text
javadoc -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example
~~~

Cách này phù hợp với CI vì lỗi liên kết, HTML hoặc tag có thể được phát hiện ngay khi thay đổi source. Không nên tắt toàn bộ doclint chỉ để build qua; nếu một nhóm không phù hợp với quy ước dự án, hãy loại trừ có chủ đích và ghi nhận lý do.

## 10. Liên kết đến Javadoc bên ngoài

API thường tham chiếu đến type của Java SE hoặc thư viện khác. Dùng `-link` để tạo liên kết đến tài liệu đã được publish:

~~~text
javadoc --release 17 -link https://docs.oracle.com/en/java/javase/17/docs/api/ -d docs -sourcepath src -subpackages com.example
~~~

Các tham chiếu như `{@link java.util.Optional}` có thể trỏ đến trang API tương ứng nếu Javadoc tìm được metadata danh sách package/element tại URL.

Nếu build chạy offline, dùng `-linkoffline` với vị trí tài liệu và bản package list/element list đã tải sẵn:

~~~text
javadoc -linkoffline https://docs.example.com/api/ external-api-docs -d docs -sourcepath src -subpackages com.example
~~~

`external-api-docs` là thư mục chứa metadata liên kết offline phù hợp với tài liệu đích. Tránh liên kết đến URL tạm hoặc tài liệu không ổn định. Khi nâng phiên bản dependency, kiểm tra liên kết external API để tránh link hỏng hoặc sai version.

## 11. Custom tag và Taglet

Nếu dự án có metadata riêng, có thể đăng ký custom block tag bằng `-tag`:

~~~text
javadoc -tag "quality:a:Quality:" -d docs -sourcepath src -subpackages com.example
~~~

Sau đó dùng trong comment:

~~~java
/**
 * Performs a catalog lookup.
 *
 * @quality Stable API
 */
public Optional<Product> findBySku(String sku) {
    // ...
}
~~~

Cú pháp `-tag` gồm tên tag, vị trí hợp lệ và heading hiển thị. Kiểm tra trợ giúp JDK để chọn vị trí phù hợp. Với cách trình bày phức tạp hơn, có thể viết Taglet và đăng ký bằng `-taglet` cùng `-tagletpath`.

Chỉ thêm custom tag khi có quy ước thực sự cần thiết. Nếu dùng tag riêng, hãy cấu hình đồng nhất trong local build, IDE và CI để tài liệu không mất nội dung khi tạo bằng lệnh khác.

## 12. Tạo tài liệu cho module

Với modular project, Javadoc có thể tạo documentation theo module. Ví dụ cấu trúc source:

~~~text
src/
  com.example.catalog/
    module-info.java
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
~~~

`module-info.java`:

~~~java
/**
 * Provides product catalog APIs.
 */
module com.example.catalog {
    exports com.example.catalog;
}
~~~

Với nhiều module, dùng `--module-source-path` và chỉ định module cần tạo tài liệu:

~~~text
javadoc --release 17 --module-source-path src --module com.example.catalog -d docs
~~~

Đối với module đã biên dịch hoặc module nằm trên module path, dùng `--module-path` và `--module` theo cấu trúc dự án. Với named module, mức hiển thị mặc định tập trung vào API được export; các tùy chọn như `--show-packages`, `--show-types`, `--show-members` và `--show-module-contents` cho phép điều chỉnh phạm vi.

Đảm bảo package được export có tài liệu phù hợp. Package nội bộ không export vẫn có thể được tạo tài liệu khi chọn chế độ hiển thị rộng hơn, nhưng không nên nhầm tài liệu nội bộ với API công khai được hỗ trợ.

## 13. Đưa Javadoc vào Maven và Gradle

Trong dự án thực tế, nên tích hợp tạo API docs vào build để thay đổi public API luôn được phản ánh trong tài liệu.

### 13.1. Maven

Dùng Maven Javadoc Plugin, ví dụ:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-javadoc-plugin</artifactId>
    <version>3.11.2</version>
    <configuration>
        <release>17</release>
        <encoding>UTF-8</encoding>
        <docencoding>UTF-8</docencoding>
        <charset>UTF-8</charset>
        <doclint>all</doclint>
        <failOnWarnings>true</failOnWarnings>
    </configuration>
</plugin>
~~~

Tạo Javadoc:

~~~text
mvn javadoc:javadoc
~~~

Tạo Javadoc JAR để publish cùng artifact:

~~~text
mvn javadoc:jar
~~~

Tên plugin version trong ví dụ là cấu hình minh họa; dự án nên dùng phiên bản plugin đã được kiểm thử và quản lý thống nhất trong parent/build configuration.

### 13.2. Gradle

Với Gradle Java plugin, task `javadoc` tạo HTML từ source set chính. Có thể cấu hình:

~~~kotlin
tasks.withType<Javadoc>().configureEach {
    options.encoding = "UTF-8"
    (options as StandardJavadocDocletOptions).apply {
        addBooleanOption("Xdoclint:all", true)
        addBooleanOption("Werror", true)
    }
}
~~~

Chạy:

~~~text
./gradlew javadoc
~~~

Trên Windows:

~~~text
gradlew.bat javadoc
~~~

Đầu ra mặc định thường nằm trong `build/docs/javadoc`. Kiểm tra cấu hình Gradle theo phiên bản đang dùng vì API của `StandardJavadocDocletOptions` có thể khác giữa các phiên bản.

## 14. Xuất bản và versioning của API documentation

Một thư viện có thể publish Javadoc theo từng phiên bản:

~~~text
https://docs.example.com/library/1.0/
https://docs.example.com/library/1.1/
https://docs.example.com/library/2.0/
~~~

Giữ phiên bản tài liệu khớp với artifact binary. Người dùng cần biết trang docs mô tả đúng phiên bản JAR/module mà họ đang sử dụng.

Khi phát hành:

- Tạo Javadoc từ đúng source revision và JDK/toolchain đã ghi nhận.
- Kiểm tra trang overview, package và public type.
- Kiểm tra các liên kết nội bộ và external link.
- Đính kèm Javadoc JAR nếu thư viện được publish cho developer.
- Giữ lại tài liệu của phiên bản cũ nếu người dùng vẫn cần tham chiếu.
- Đánh dấu deprecated API và chỉ rõ API thay thế.
- Đưa tài liệu vào release pipeline cùng source JAR và binary artifact.

Không publish tài liệu chứa API nội bộ, thông tin nhạy cảm, đường dẫn máy phát triển hoặc ghi chú chưa được duyệt.

## 15. Quy tắc viết API documentation dễ dùng và dễ bảo trì

Một bộ API docs hữu ích nên trả lời được các câu hỏi thực tế:

- **Hành vi:** method làm gì, có thay đổi trạng thái hay không, có I/O hoặc blocking không?
- **Input:** tham số có được phép null không, định dạng/đơn vị nào hợp lệ, có giới hạn kích thước hoặc phạm vi không?
- **Output:** trả về giá trị nào, có thể rỗng không, object trả về mutable hay immutable?
- **Failure:** exception nào có thể xảy ra và trong điều kiện nào? Người gọi nên xử lý ra sao?
- **Concurrency:** object có thread-safe không, method có thể gọi đồng thời không, caller có cần đồng bộ hóa không?
- **Lifecycle:** ai sở hữu tài nguyên, khi nào phải đóng, có thể gọi lại sau close không?
- **Compatibility:** API được thêm từ version nào, có deprecated hoặc thay đổi behavior không?

Không cần mô tả chi tiết implementation nếu người dùng API không cần biết. Tuy nhiên, các đặc tính quan sát được như thứ tự kết quả, tính ổn định, độ chính xác, timeout, retry và side effect phải được nói rõ khi chúng ảnh hưởng đến cách sử dụng.

### 15.1. Tránh các lỗi viết tài liệu thường gặp

- Mô tả lặp lại tên method: “Gets the name” cho `getName()`.
- Thiếu `@param` hoặc mô tả không khớp kiểu/ý nghĩa.
- `@return` không giải thích trường hợp empty/null.
- `@throws` chỉ liệt kê exception mà không nêu điều kiện.
- Link đến overload sai hoặc class không tồn tại.
- HTML không đóng tag hoặc dùng heading sai cấu trúc.
- Ví dụ không biên dịch với API hiện tại.
- Ghi implementation detail như thể đó là hợp đồng ổn định.
- Không cập nhật Javadoc khi thay đổi public signature hoặc behavior.
- Dùng `@deprecated` mà không chỉ ra lựa chọn thay thế.

## 16. Troubleshooting Javadoc

### `error: reference not found`

**Nguyên nhân:** `{@link}` hoặc `@see` trỏ đến class/member sai, thiếu dependency hoặc overload không khớp.

**Cách xử lý:** kiểm tra tên type, package, signature và classpath/module path. Với overload, chỉ rõ danh sách tham số.

### `warning: no @param for ...`

**Nguyên nhân:** method/constructor có tham số nhưng documentation thiếu tag tương ứng hoặc tên tag không khớp.

**Cách xử lý:** thêm `@param` cho từng tham số và cập nhật mô tả khi chữ ký method đổi.

### `warning: no @return`

**Nguyên nhân:** method trả về giá trị nhưng documentation thiếu `@return` trong phạm vi kiểm tra.

**Cách xử lý:** mô tả kết quả và các trạng thái đặc biệt như empty, null hoặc giá trị mặc định.

### `invalid HTML`

**Nguyên nhân:** HTML trong documentation comment sai cú pháp, thiếu đóng tag hoặc lồng phần tử không hợp lệ.

**Cách xử lý:** sửa markup, ưu tiên HTML đơn giản và chạy lại `-Xdoclint:all`.

### Ký tự tiếng Việt bị lỗi

**Nguyên nhân:** encoding source hoặc output không đồng nhất.

**Cách xử lý:** dùng `-encoding UTF-8`, `-docencoding UTF-8` và `-charset UTF-8`; lưu source bằng UTF-8.

### Trang package không có mô tả

**Nguyên nhân:** thiếu `package-info.java` hoặc source path không tìm thấy file package documentation.

**Cách xử lý:** tạo `package-info.java` đúng package và xác nhận `-sourcepath` trỏ đến thư mục gốc source.

### Không thấy member mong muốn

**Nguyên nhân:** member không nằm trong mức visibility được chọn hoặc module/package không được export.

**Cách xử lý:** kiểm tra `-public`, `-protected`, `-package`, `-private`, module descriptor và các tùy chọn `--show-*`.

### External link không hoạt động

**Nguyên nhân:** URL tài liệu đích không có package list/element list phù hợp, build offline hoặc version docs sai.

**Cách xử lý:** dùng URL tài liệu đúng phiên bản; với build offline, dùng `-linkoffline` và metadata đã tải sẵn.

### Build Javadoc thất bại sau khi nâng JDK

**Nguyên nhân:** doclint chặt hơn, tag/HTML không còn hợp lệ, API hoặc tùy chọn doclet thay đổi.

**Cách xử lý:** đọc warning/error đầu tiên, chạy `javadoc --version`, kiểm tra `--help` và `--help-extra`, sửa comment theo chuẩn rồi mới cân nhắc cấu hình tương thích.

## 17. Checklist hoàn thành API documentation

- [ ] Public class/interface/record có summary nêu đúng vai trò.
- [ ] Public constructor có mô tả cách tạo object và điều kiện đầu vào.
- [ ] Public method mô tả hành vi, tham số, return và exception phù hợp.
- [ ] Generic type parameter có giải thích khi cần.
- [ ] Nullability, mutability, thread-safety, side effect và resource lifecycle được nêu khi ảnh hưởng người gọi.
- [ ] Link đến class/member đúng signature và đúng overload.
- [ ] `@since` khớp version API.
- [ ] API deprecated có annotation, lý do và API thay thế.
- [ ] Package có `package-info.java`.
- [ ] Module có documentation trong `module-info.java` nếu dự án modular.
- [ ] Ví dụ và snippet khớp với API hiện tại.
- [ ] Encoding source/output là UTF-8.
- [ ] Javadoc build chạy với `-Xdoclint:all`.
- [ ] CI dùng `-Werror` nếu chính sách yêu cầu không có warning.
- [ ] Đã mở kiểm tra `index.html`, package page và class/member page.
- [ ] External links, version và Javadoc JAR được kiểm tra trước release.

Javadoc biến documentation comment trong source thành API reference có thể duyệt và liên kết. Khi mô tả đúng hợp đồng, dùng tag nhất quán, kiểm tra bằng doclint và tạo tài liệu trong build pipeline, người dùng thư viện có thể hiểu cách gọi API mà không phải đọc implementation để đoán hành vi.