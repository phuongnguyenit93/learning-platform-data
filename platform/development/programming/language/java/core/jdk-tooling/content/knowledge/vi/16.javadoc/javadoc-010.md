# Kiểm tra chất lượng Javadoc trong Java

Kiểm tra Javadoc là quá trình xác nhận tài liệu API được tạo đúng, đầy đủ, có liên kết hợp lệ và mô tả chính xác hành vi mà người dùng thư viện có thể quan sát. Chạy lệnh `javadoc` thành công mới là bước đầu. Một bộ API documentation đáng tin cậy còn cần vượt qua kiểm tra cú pháp, tag, HTML, tham chiếu, phạm vi API, tính nhất quán với mã nguồn và kiểm tra trực quan trên HTML đầu ra.

Có thể chia việc kiểm tra thành bốn lớp:

1. **Kiểm tra tự động bằng Javadoc/DocLint:** phát hiện comment, tag, HTML và reference có vấn đề.
2. **Kiểm tra phạm vi API:** bảo đảm đúng package, class và member công khai được đưa vào tài liệu.
3. **Kiểm tra nội dung:** đối chiếu mô tả, tham số, kết quả, exception, nullability, thread-safety và ví dụ với hành vi thực tế.
4. **Kiểm tra HTML đã sinh:** xem trang tổng quan, điều hướng, liên kết, khả năng truy cập và phiên bản tài liệu.

Javadoc không thể tự chứng minh mọi câu mô tả đúng với logic chương trình. Kết hợp DocLint với code review, test và kiểm tra HTML giúp giảm nguy cơ phát hành tài liệu sai hoặc thiếu.

Toolchain được dùng để kiểm tra bài này báo `javadoc 24.0.2`. Tùy chọn có thể khác giữa các JDK; hãy xem `javadoc --version`, `javadoc --help` và `javadoc --help-extra` trên môi trường build thực tế.

## 1. Javadoc và DocLint kiểm tra những gì?

`javadoc` đọc documentation comment trong source và tạo HTML bằng standard doclet. DocLint là nhóm kiểm tra được tích hợp trong công cụ này, giúp phát hiện các vấn đề trong documentation comment và HTML.

Các nhóm DocLint thường dùng:

| Nhóm | Nội dung kiểm tra | Ví dụ lỗi |
|---|---|---|
| `accessibility` | Một số yêu cầu về khả năng truy cập của HTML | Bảng thiếu cấu trúc tiêu đề phù hợp, hình ảnh thiếu mô tả |
| `html` | Cú pháp và cấu trúc HTML | Tag không hợp lệ, phần tử lồng sai hoặc thiếu đóng |
| `missing` | Thiếu documentation hoặc block tag cần thiết | Public method thiếu mô tả, thiếu `@param` hoặc `@return` |
| `reference` | Tham chiếu đến type/member | `{@link}` trỏ đến method không tồn tại hoặc sai overload |
| `syntax` | Cú pháp documentation comment và tag | Tag viết sai cấu trúc, inline tag không đóng |

Bật tất cả nhóm:

~~~text
javadoc -Xdoclint:all ...
~~~

Chỉ bật một số nhóm:

~~~text
javadoc -Xdoclint:html,reference,syntax ...
~~~

Loại trừ một nhóm:

~~~text
javadoc -Xdoclint:all,-missing ...
~~~

Chỉ tắt nhóm kiểm tra khi dự án có lý do rõ ràng và đã ghi nhận ngoại lệ. Với API công khai, nên giữ kiểm tra `missing`, `reference`, `html` và `syntax` trong build thường xuyên.

Tên nhóm và tùy chọn chi tiết có thể thay đổi theo JDK. Hãy xem trợ giúp của đúng toolchain thay vì giả định mọi phiên bản hỗ trợ giống nhau.

## 2. Biến warning thành lỗi với `-Werror`

Mặc định, Javadoc có thể tiếp tục tạo HTML dù phát hiện warning. Điều này hữu ích khi đang chuyển đổi codebase cũ, nhưng không phù hợp nếu CI cần ngăn tài liệu lỗi đi vào release.

Dùng `-Werror` để biến warning thành lỗi của lần chạy:

~~~text
javadoc -Xdoclint:all -Werror ...
~~~

Kết hợp hai tùy chọn có nghĩa là:

- `-Xdoclint:all`: bật toàn bộ nhóm kiểm tra documentation.
- `-Werror`: kết thúc với trạng thái lỗi nếu còn warning.

Có thể dùng `-Xmaxerrs` và `-Xmaxwarns` để điều chỉnh số lượng lỗi/cảnh báo được in ra khi cần điều tra một lần chạy lớn. Chúng không sửa nội dung và không thay thế việc xử lý nguyên nhân.

Khi đưa DocLint vào một dự án lâu năm, có thể bắt đầu bằng `-Xdoclint:all` để thống kê vấn đề, sửa theo nhóm, sau đó bật `-Werror` khi đã đạt mức chất lượng mong muốn. Tránh duy trì vô thời hạn một cấu hình bỏ qua warning mà không có kế hoạch xử lý.

## 3. Kiểm tra documentation bị thiếu

Một public API có thể biên dịch hoàn toàn bình thường dù thiếu Javadoc. Vì vậy, build `javac` thành công không chứng minh API docs đã đầy đủ.

Kiểm tra các thành phần:

- Public class, interface, enum và record có phần mô tả nêu vai trò.
- Public constructor giải thích điều kiện tạo object và đầu vào.
- Public method giải thích hành vi, tham số, kết quả và exception.
- Generic type parameter có `@param <T>` hoặc mô tả phù hợp.
- Public constant có mô tả ý nghĩa và đơn vị nếu có.
- Package có tài liệu chung nếu package là một phần của API.
- Module có mô tả và thông tin export phù hợp khi dự án modular.

### 3.1. Kiểm tra tag theo chữ ký method

Ví dụ method:

~~~java
/**
 * Searches for a product by its SKU.
 *
 * @param sku the exact SKU to search for
 * @return the matching product, or an empty result if none exists
 * @throws NullPointerException if {@code sku} is {@code null}
 */
public Optional<Product> findBySku(String sku) {
    // implementation
}
~~~

Đối chiếu documentation với chữ ký:

| Thành phần | Điều cần kiểm tra |
|---|---|
| `@param sku` | Tên phải khớp tham số thực tế; mô tả đúng định dạng và điều kiện đầu vào |
| `@return` | Mô tả chính xác kết quả, kể cả trường hợp empty/null |
| `@throws` | Nêu điều kiện thực tế có thể phát sinh exception |
| Description | Mô tả hành vi, quy tắc tìm kiếm và tác dụng phụ nếu có |

Với method `void`, không ghi `@return`. Với constructor, không ghi `@return`. Với generic method, kiểm tra cả type parameter và tham số thông thường.

### 3.2. Kiểm tra tên tham số và type parameter

Lỗi thường gặp là đổi tên tham số trong source nhưng quên cập nhật `@param`, hoặc ghi `@param <T>` trong khi type parameter có tên khác.

Ví dụ source:

~~~java
public Product find(String productSku) {
    // implementation
}
~~~

Documentation phải dùng `@param productSku`, không phải `@param sku`.

Khi refactor chữ ký API, kiểm tra lại block tag, ví dụ, snippet và mọi link đến overload đó.

### 3.3. Kiểm tra mô tả exception

Không chỉ liệt kê tên exception. Hãy mô tả điều kiện phát sinh và thông tin mà người gọi cần để xử lý.

Ví dụ:

~~~java
/**
 * Opens a catalog file.
 *
 * @param path the path to the catalog file
 * @return the loaded catalog
 * @throws IOException if the file cannot be read or parsed
 * @throws NullPointerException if {@code path} is {@code null}
 */
public Catalog open(Path path) throws IOException {
    // implementation
}
~~~

Đối chiếu với implementation và test. Nếu method thực tế còn ném `IllegalArgumentException` khi format sai, tài liệu cần phản ánh điều đó nếu đây là hành vi API được cam kết.

## 4. Kiểm tra link và tham chiếu Javadoc

Các tham chiếu thường nằm trong `{@link}`, `{@linkplain}`, `@see`, `{@value}` và `{@inheritDoc}`.

Ví dụ link hợp lệ:

~~~java
/**
 * Uses {@link Product#sku()} to identify the product.
 *
 * @see Catalog#findBySku(String)
 */
public final class ProductIndex {
}
~~~

Các lỗi cần tìm:

- Tên class hoặc package sai.
- Member không tồn tại hoặc đổi tên.
- Link đến overload sai vì thiếu kiểu tham số.
- Tham chiếu đến member private không phù hợp với tài liệu API công khai.
- `{@inheritDoc}` dùng ở nơi không có documentation cha/interface thích hợp.
- Link external trỏ sai phiên bản tài liệu.

DocLint nhóm `reference` giúp phát hiện nhiều tham chiếu nội bộ không hợp lệ. Khi gặp lỗi, kiểm tra package, tên class, tên member và signature. Với overload, viết rõ kiểu tham số:

~~~text
{@link Catalog#findBySku(String)}
{@link Catalog#findById(long)}
~~~

### 4.1. Kiểm tra liên kết đến tài liệu bên ngoài

Dùng `-link` để liên kết đến Javadoc đã publish:

~~~text
javadoc --release 17 -link https://docs.oracle.com/en/java/javase/17/docs/api/ ...
~~~

Javadoc cần metadata danh sách package/element tại địa chỉ tài liệu để tạo liên kết. Với build offline, dùng `-linkoffline` và thư mục metadata đã tải sẵn:

~~~text
javadoc -linkoffline https://docs.example.com/api/ external-api-docs ...
~~~

Kiểm tra URL đúng phiên bản thư viện hoặc Java SE, metadata thuộc đúng bộ tài liệu, HTML sinh ra trỏ đến đúng trang đích, và CI có quyền truy cập tài liệu đích hoặc sử dụng metadata offline.

DocLint không thay thế việc kiểm tra mọi liên kết HTTP bên ngoài. Một URL có thể hợp lệ về cú pháp nhưng máy chủ đã di chuyển, yêu cầu đăng nhập hoặc không còn tồn tại. Dùng link checker phù hợp với quy trình tài liệu để kiểm tra URL sau khi sinh HTML.

## 5. Kiểm tra HTML và khả năng truy cập

Javadoc sinh HTML từ description, inline tag và block tag. DocLint có thể phát hiện nhiều lỗi HTML, nhưng vẫn cần xem trang kết quả.

Kiểm tra:

- Heading có thứ tự hợp lý và không nhảy cấp tùy tiện.
- Bảng có hàng tiêu đề và mô tả cột rõ ràng.
- Danh sách được tạo đúng dạng list.
- Code block dễ đọc và không bị cắt mất nội dung.
- HTML không chứa tag lỗi hoặc markup không an toàn.
- Liên kết có nhãn có ý nghĩa, không chỉ ghi “click here”.
- Hình ảnh hoặc icon tùy chỉnh có văn bản thay thế khi cần.
- Trang có thể đọc được ở màn hình nhỏ và khi zoom.
- Điều hướng bằng bàn phím và công nghệ hỗ trợ hoạt động ở mức cần thiết.

Nếu dự án thêm stylesheet, script, header, footer hoặc doclet tùy chỉnh, kiểm tra cả những phần này. Lỗi có thể xuất hiện ở template tùy chỉnh dù source comment đã hợp lệ.

Có thể dùng HTML validator hoặc accessibility checker độc lập trong pipeline tài liệu nếu mức độ phát hành yêu cầu. Đọc kết quả theo chuẩn HTML mà Javadoc đang sinh; tránh đánh đồng cảnh báo của validator cũ với lỗi thật của standard doclet mới.

## 6. Kiểm tra phạm vi API được đưa vào tài liệu

Javadoc có các mức visibility khác nhau. Mặc định thường hiển thị public và protected API; `-public` chỉ hiển thị public, còn `-private` hiển thị cả thành viên private.

| Tùy chọn | Phạm vi |
|---|---|
| `-public` | Chỉ public type/member |
| `-protected` | Public và protected; thường là mặc định |
| `-package` | Public, protected và package-private |
| `-private` | Tất cả, bao gồm private |

Với API reference dành cho người dùng thư viện, không nên dùng `-private` nếu không có mục tiêu công bố tài liệu nội bộ. Điều này có thể làm lộ cấu trúc triển khai, tên thành phần nội bộ hoặc chi tiết chưa phải hợp đồng được hỗ trợ.

Kiểm tra package được đưa vào lệnh:

~~~text
javadoc -sourcepath src -subpackages com.example.publicapi -d docs
~~~

`-subpackages` đệ quy qua package và subpackage được chỉ định. Nếu bỏ sót package, trang tổng quan có thể không có API mà người dùng mong đợi dù source comment đã đầy đủ.

Với named module, xem xét `--module`, `--module-path`, `--module-source-path` và các tùy chọn `--show-packages`, `--show-types`, `--show-members`, `--show-module-contents`. Đảm bảo tài liệu công khai phản ánh đúng package export trong `module-info.java`.

## 7. Kiểm tra tính chính xác về ngữ nghĩa

Đây là phần cần người review hiểu API. DocLint kiểm tra cấu trúc và tham chiếu, nhưng không thể biết một câu mô tả có đúng với nghiệp vụ hay không.

Đối chiếu từng mô tả với code và test:

| Chủ đề | Câu hỏi cần xác nhận |
|---|---|
| Input | Null có được chấp nhận? Chuỗi có phân biệt hoa thường? Có giới hạn độ dài? |
| Output | Có thể trả empty/null? Kết quả có ổn định hoặc có thứ tự không? |
| Mutability | Object trả về có mutable? Có phải snapshot hay view trực tiếp? |
| Side effect | Method có sửa trạng thái, ghi file, gửi request hoặc cập nhật cache? |
| Exception | Điều kiện nào làm phát sinh checked/unchecked exception? |
| Thread-safety | Có thể gọi đồng thời? Caller có cần đồng bộ hóa? |
| Resource | Ai sở hữu stream, connection hoặc executor? Ai phải đóng? |
| Performance | Có blocking, retry, timeout hoặc chi phí đáng kể cần biết? |
| Compatibility | API có từ phiên bản nào? Có deprecated hoặc thay đổi behavior? |

Ví dụ, nếu tài liệu nói method trả về immutable snapshot, kiểm tra implementation có thật sự tạo bản sao không. Nếu tài liệu nói tìm kiếm không phân biệt hoa thường, kiểm tra cả implementation lẫn test cho các SKU khác chữ hoa/thường.

Không ghi chi tiết triển khai tạm thời như thể đó là hợp đồng ổn định. Ngược lại, không bỏ qua hành vi quan sát được mà caller cần dựa vào.

## 8. Kiểm tra ví dụ và code snippet

Code trong Javadoc thường có ba dạng:

- Code inline bằng `{@code ...}`.
- Snippet đặt trực tiếp bằng `{@snippet ...}`.
- Ví dụ dài nằm trong file riêng và được đưa vào qua snippet path hoặc tài liệu hướng dẫn.

Javadoc không tự đảm bảo mọi đoạn code trong comment là một chương trình độc lập có thể biên dịch. Với ví dụ có giá trị học tập, hãy kiểm tra bằng compiler/test hoặc chạy trong một project mẫu.

Checklist cho mỗi ví dụ:

1. Import đầy đủ hoặc nói rõ package/import đã lược bỏ.
2. Tên class, method và tham số tồn tại trong phiên bản API được mô tả.
3. Mã có thể biên dịch với Java release mục tiêu.
4. Kết quả stdout hoặc kết quả minh họa khớp với chương trình.
5. Không sử dụng API deprecated mà không giải thích.
6. Không bỏ qua exception hoặc resource cleanup quan trọng.
7. Ví dụ không dựa vào file, service hay biến môi trường không được nêu.

Nếu snippet dài được lưu riêng, kiểm tra file đó có được đưa vào build và được cập nhật cùng API. Tránh để ví dụ trong Javadoc và test code trở thành hai bản sao lệch nhau.

## 9. Quy trình tạo và kiểm tra Javadoc cho Java 17

Ví dụ sau tạo một thư viện catalog nhỏ. Ta sẽ biên dịch mã nguồn, sinh API docs với DocLint nghiêm ngặt và kiểm tra HTML được tạo.

Cấu trúc project:

~~~text
project/
  src/
    com/
      example/
        catalog/
          package-info.java
          Product.java
          Catalog.java
        app/
          Main.java
  out/
  docs/
~~~

### 9.1. Tài liệu package

Tệp `src/com/example/catalog/package-info.java`:

~~~java
/**
 * Public API for product catalog lookup.
 *
 * <p>Use {@link com.example.catalog.Catalog} to search for products.
 *
 * @since 1.0
 */
package com.example.catalog;
~~~

### 9.2. Class Product

Tệp `src/com/example/catalog/Product.java`:

~~~java
package com.example.catalog;

import java.util.Objects;

/**
 * Represents a product identified by a stock keeping unit (SKU).
 *
 * <p>The SKU and name are immutable after construction.
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
     * @throws NullPointerException if either argument is {@code null}
     * @throws IllegalArgumentException if either argument is blank
     */
    public Product(String sku, String name) {
        Objects.requireNonNull(sku, "sku");
        Objects.requireNonNull(name, "name");
        if (sku.isBlank() || name.isBlank()) {
            throw new IllegalArgumentException("values must not be blank");
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

### 9.3. Class Catalog

Tệp `src/com/example/catalog/Catalog.java`:

~~~java
package com.example.catalog;

import java.util.Collection;
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;
import java.util.Optional;

/**
 * Provides read-only lookup operations for a collection of products.
 *
 * <p>The catalog rejects duplicate SKUs and does not change after construction.
 *
 * @since 1.0
 */
public final class Catalog {
    private final Map<String, Product> products;

    /**
     * Creates a catalog from the supplied products.
     *
     * @param initialProducts products to include
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
     * @return the matching product, or an empty result if none exists
     * @throws NullPointerException if {@code sku} is {@code null}
     * @see Product#sku()
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

### 9.4. Chương trình dùng thử

Tệp `src/com/example/app/Main.java`:

~~~java
package com.example.app;

import com.example.catalog.Catalog;
import com.example.catalog.Product;
import java.util.List;

public class Main {
    public static void main(String[] args) {
        Catalog catalog = new Catalog(List.of(
                new Product("A-100", "Keyboard"),
                new Product("B-200", "Mouse")));

        System.out.println("Catalog size: " + catalog.size());
        Product found = catalog.findBySku("A-100").orElseThrow();
        System.out.println("Found: " + found.sku() + " - " + found.name());
        System.out.println("Missing: " + catalog.findBySku("X-999").isEmpty());
    }
}
~~~

Biên dịch từ thư mục `project`:

Windows PowerShell:

~~~powershell
New-Item -ItemType Directory -Force out, docs | Out-Null
javac --release 17 -encoding UTF-8 -d out `
    src\com\example\catalog\package-info.java `
    src\com\example\catalog\Product.java `
    src\com\example\catalog\Catalog.java `
    src\com\example\app\Main.java
~~~

macOS/Linux:

~~~sh
mkdir -p out docs
javac --release 17 -encoding UTF-8 -d out \
    src/com/example/catalog/package-info.java \
    src/com/example/catalog/Product.java \
    src/com/example/catalog/Catalog.java \
    src/com/example/app/Main.java
~~~

Chạy chương trình:

~~~text
java -cp out com.example.app.Main
~~~

Stdout:

~~~text
Catalog size: 2
Found: A-100 - Keyboard
Missing: true
~~~

### 9.5. Sinh Javadoc với kiểm tra nghiêm ngặt

Từ thư mục `project`:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -d docs -sourcepath src -subpackages com.example.catalog
~~~

Giải thích:

- `--release 17`: dùng API nền tảng và mức source tương thích Java 17.
- `-encoding UTF-8`: đọc source theo UTF-8.
- `-docencoding UTF-8`: ghi HTML bằng UTF-8.
- `-charset UTF-8`: khai báo charset trong HTML.
- `-Xdoclint:all`: bật các nhóm kiểm tra documentation.
- `-Werror`: làm build thất bại nếu còn warning.
- `-d docs`: thư mục đầu ra.
- `-sourcepath src`: gốc cây source.
- `-subpackages com.example.catalog`: tạo tài liệu cho package catalog và subpackage.

Lệnh chỉ tạo tài liệu cho package catalog. Package ứng dụng `com.example.app` không phải API được publish trong ví dụ này.

## 10. Kiểm tra HTML được tạo

Sau khi lệnh Javadoc hoàn tất, kiểm tra các file chính:

~~~text
docs/index.html
docs/com/example/catalog/package-summary.html
docs/com/example/catalog/Product.html
docs/com/example/catalog/Catalog.html
~~~

Tên file phụ trợ và trang index có thể khác giữa các phiên bản JDK hoặc cấu hình doclet. Hãy kiểm tra những trang thực sự được tạo trong output.

Trên Windows PowerShell:

~~~powershell
Get-ChildItem -Recurse docs | Select-Object FullName, Length
~~~

macOS/Linux:

~~~sh
find docs -type f -print
~~~

Mở `docs/index.html` trong trình duyệt và kiểm tra:

- Trang tổng quan hiển thị package dự kiến.
- Trang package có phần mô tả từ `package-info.java`.
- Trang `Product` có constructor, `sku()` và `name()`.
- Trang `Catalog` có constructor, `findBySku(String)` và `size()`.
- Tham chiếu `Product#sku()` dẫn đến đúng member.
- Summary hiển thị đúng ở phần tóm tắt và chi tiết.
- Các block tag hiển thị đúng phần Parameters, Returns, Throws và Since nếu có.
- Không có dấu tiếng Việt lỗi encoding hoặc code block bị vỡ.

Đừng chỉ kiểm tra exit code. Một lần chạy có thể tạo HTML nhưng output vẫn thiếu package do `-sourcepath` hoặc `-subpackages` sai.

## 11. Kiểm tra lỗi bằng ví dụ có chủ đích

Để hiểu DocLint, thử tạo một lỗi nhỏ trong documentation rồi chạy lại lệnh kiểm tra.

Ví dụ documentation không khớp chữ ký:

~~~java
/**
 * Finds a product.
 *
 * @param product the product SKU
 * @return the product if found
 */
public Optional<Product> findBySku(String sku) {
    // implementation
}
~~~

Ở đây `@param product` không khớp tên tham số `sku`. Tùy kiểm tra và JDK, DocLint có thể báo thiếu tag cho tham số thật hoặc tag không khớp.

Ví dụ link sai:

~~~java
/**
 * Uses {@link Product#skuCode()} to identify a product.
 */
public final class Catalog {
}
~~~

Nếu `skuCode()` không tồn tại, nhóm `reference` sẽ phát hiện tham chiếu không hợp lệ.

Ví dụ HTML sai:

~~~java
/**
 * <p>Returns a product from the catalog.
 * <ul>
 *   <li>Searches by SKU.
 * </p>
 */
public Optional<Product> findBySku(String sku) {
    // implementation
}
~~~

Cấu trúc list và paragraph không hợp lệ có thể bị nhóm `html` phát hiện.

Sau khi sửa, đổi `@param product` thành `@param sku`, đổi link thành `{@link Product#sku()}` và đóng các HTML element đúng cấu trúc. Chạy lại lệnh với `-Xdoclint:all -Werror`. Mục tiêu là không còn warning hoặc error liên quan đến tài liệu.

## 12. Kiểm tra với Maven và Gradle

Trong dự án dùng build tool, đưa kiểm tra Javadoc vào CI để mọi thay đổi API đều được kiểm tra.

### 12.1. Maven

Dùng Maven Javadoc Plugin để tạo API docs:

~~~text
mvn javadoc:javadoc
~~~

Tạo Javadoc JAR để phát hành cùng thư viện:

~~~text
mvn javadoc:jar
~~~

Trong cấu hình plugin, thiết lập release, UTF-8, DocLint và fail-on-warning theo phiên bản plugin đang dùng. Ví dụ cấu hình có thể gồm:

~~~xml
<configuration>
    <release>17</release>
    <encoding>UTF-8</encoding>
    <docencoding>UTF-8</docencoding>
    <charset>UTF-8</charset>
    <doclint>all</doclint>
    <failOnWarnings>true</failOnWarnings>
</configuration>
~~~

Kiểm tra tài liệu plugin đang dùng để xác nhận tên parameter và cách truyền tùy chọn Javadoc; không giả định mọi phiên bản plugin hỗ trợ cùng một cấu hình.

### 12.2. Gradle

Với Gradle Java plugin, task `javadoc` tạo HTML. Có thể cấu hình standard doclet:

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

Đầu ra thường nằm trong `build/docs/javadoc`. Đường dẫn và API cấu hình có thể thay đổi theo phiên bản Gradle.

## 13. Kiểm tra tài liệu giữa các phiên bản API

Khi phát hành thư viện nhiều phiên bản, kiểm tra tài liệu theo đúng binary artifact:

- Javadoc được tạo từ cùng source revision với binary.
- `@since` phản ánh phiên bản đầu tiên API xuất hiện.
- API deprecated có annotation, lý do và API thay thế.
- Tài liệu cũ vẫn được lưu nếu người dùng cần tham khảo.
- Liên kết external trỏ đến đúng version dependency.
- Javadoc JAR đi kèm đúng version của thư viện.
- Release notes không mâu thuẫn với behavior mô tả trong API docs.

Có thể dùng tùy chọn `--since` để tạo tài liệu nhấn mạnh API mới hoặc deprecated trong các release được chỉ định. Kiểm tra `javadoc --help` của JDK trước khi thêm tùy chọn này vào pipeline.

Khi thay đổi chữ ký method, type parameter, exception hoặc semantics, review tài liệu như một phần của API compatibility review. Một thay đổi source có thể biên dịch nhưng làm link hoặc ví dụ trong Javadoc lỗi.

## 14. Tự động hóa kiểm tra trong CI

Một pipeline tài liệu có thể thực hiện theo thứ tự:

1. Checkout đúng commit.
2. Cài JDK được dự án hỗ trợ.
3. Compile source và test.
4. Chạy Javadoc với `-Xdoclint:all -Werror`.
5. Kiểm tra output directory có trang index và trang API mong đợi.
6. Chạy link checker hoặc HTML/accessibility validator nếu dự án yêu cầu.
7. Lưu HTML/Javadoc JAR làm build artifact.
8. Publish đúng version sau khi release được duyệt.

Ví dụ command kiểm tra cơ bản:

~~~text
javadoc --release 17 -encoding UTF-8 -docencoding UTF-8 -charset UTF-8 -Xdoclint:all -Werror -d build/apidocs -sourcepath src -subpackages com.example.publicapi
~~~

Nên cố định JDK và plugin version để kết quả có thể tái hiện. Ghi nhận phiên bản công cụ trong log CI; khi nâng JDK, xem lại warning mới thay vì tắt DocLint ngay lập tức.

Có thể thêm bước kiểm tra file output:

Windows PowerShell:

~~~powershell
if (-not (Test-Path build\apidocs\index.html)) {
    throw "Javadoc index.html was not generated"
}
~~~

macOS/Linux:

~~~sh
test -f build/apidocs/index.html
~~~

Đây chỉ là kiểm tra sự tồn tại của output; vẫn cần kiểm tra package/type pages và nội dung liên kết.

## 15. Troubleshooting khi kiểm tra Javadoc

### `reference not found`

**Nguyên nhân:** `{@link}` hoặc `@see` trỏ đến type/member không tồn tại, sai package hoặc sai overload.

**Cách xử lý:** kiểm tra signature, tên package, import và module/class path. Với overload, chỉ rõ tham số.

### `no @param for ...`

**Nguyên nhân:** thiếu `@param` hoặc tên tag không khớp với tham số trong source.

**Cách xử lý:** đối chiếu chữ ký method/constructor và cập nhật từng tag. Với generic method, kiểm tra cả `@param <T>`.

### `no @return`

**Nguyên nhân:** method trả về giá trị nhưng tài liệu chưa mô tả kết quả trong phạm vi kiểm tra.

**Cách xử lý:** thêm `@return`, nói rõ trường hợp empty/null và trạng thái đặc biệt. Không thêm `@return` cho method `void` hoặc constructor.

### `invalid HTML`

**Nguyên nhân:** tag HTML không hợp lệ, lồng sai hoặc thiếu đóng.

**Cách xử lý:** sửa markup, dùng HTML đơn giản và chạy lại nhóm `html` hoặc `-Xdoclint:all`.

### Javadoc kết thúc với warning dù HTML được tạo

**Nguyên nhân:** warning vẫn được phép trong cấu hình hiện tại.

**Cách xử lý:** bật `-Werror` trong CI để không chấp nhận warning mới.

### Không thấy package hoặc member

**Nguyên nhân:** package không nằm trong `-subpackages`, source path sai hoặc visibility filter không phù hợp.

**Cách xử lý:** kiểm tra `-sourcepath`, package đầu vào, `-public`/`-protected`/`-private` và module export.

### External link không mở được

**Nguyên nhân:** URL sai version, metadata không có hoặc máy build không truy cập được máy chủ.

**Cách xử lý:** dùng URL đúng và `-linkoffline` khi build offline; chạy link checker trên HTML đầu ra.

### Ví dụ trong Javadoc không chạy

**Nguyên nhân:** snippet không được compile/test như một phần của build, API thay đổi hoặc ví dụ thiếu import/setup.

**Cách xử lý:** đưa ví dụ quan trọng thành test/example source được biên dịch trong CI và đồng bộ với documentation.

### Build Javadoc khác nhau giữa local và CI

**Nguyên nhân:** khác JDK, locale, encoding, plugin hoặc dependency trên classpath/module path.

**Cách xử lý:** cố định toolchain, encoding, release và plugin version; lưu log `javadoc --version` và command line.

## 16. Checklist kiểm tra trước khi publish

- [ ] Đã xác nhận JDK/Javadoc version và release mục tiêu.
- [ ] Đã chạy `-Xdoclint:all`.
- [ ] CI bật `-Werror` khi chính sách yêu cầu không có warning.
- [ ] Không còn lỗi `reference`, `html` hoặc `syntax`.
- [ ] Public API cần hỗ trợ có mô tả đầy đủ.
- [ ] `@param`, `@return`, `@throws` khớp chữ ký và hành vi.
- [ ] Link đến class, method và overload đúng.
- [ ] Package/module documentation được tạo đúng phạm vi.
- [ ] Không vô tình publish private/internal API.
- [ ] Code snippet và ví dụ quan trọng đã được biên dịch hoặc kiểm thử.
- [ ] HTML output có trang index, package và type cần thiết.
- [ ] Navigation, search, encoding, code block và accessibility đã được xem xét.
- [ ] External links và version dependency đã được kiểm tra.
- [ ] Javadoc HTML/Javadoc JAR khớp source revision và binary release.
- [ ] CI lưu log, command line và artifact để có thể tái hiện.

Kiểm tra Javadoc hiệu quả cần cả công cụ lẫn review nội dung. DocLint phát hiện nhiều lỗi cú pháp, tag, HTML và reference; `-Werror` giúp giữ chuẩn trong CI; còn đối chiếu với implementation, test và HTML đầu ra xác nhận người dùng nhận được tài liệu API đúng, đầy đủ và hữu ích.