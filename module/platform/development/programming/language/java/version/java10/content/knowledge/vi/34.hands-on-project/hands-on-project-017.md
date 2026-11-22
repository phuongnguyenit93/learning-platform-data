# Java 10 – Thực hành tổng hợp: Xây dựng tài liệu API có tóm tắt và kiểu dáng nhất quán

> **Ngữ cảnh:** Java 10 → **Thực hành tổng hợp** → **Xây dựng tài liệu API có tóm tắt và kiểu dáng nhất quán**. Java 10 bổ sung thẻ Javadoc **`{@summary ...}`** (JDK-8173425), cho phép chỉ định chính xác phần tóm tắt của một API thay vì phụ thuộc hoàn toàn vào thuật toán cắt câu đầu tiên. Tính năng này **vẫn được hỗ trợ trên JDK hiện đại**. Bài thực hành kết hợp Javadoc chuẩn, hợp đồng `@param`/`@return`/`@throws`, cross-reference, tài liệu cấp package, kiểm tra DocLint, CSS bổ sung có thể tái sử dụng, và xác minh HTML sinh ra. Ví dụ được kiểm trên **OpenJDK 21**, biên dịch bằng `--release 17` và biên dịch được với `--release 10`; không khuyến nghị triển khai JDK 10 đã hết vòng đời bảo mật cho hệ thống mới.

## 1. Kết quả cần đạt

Sau bài này, bạn có thể:

1. Giải thích vì sao API documentation là một phần của **hợp đồng thư viện**, không chỉ là comment trong source.
2. Viết đoạn Javadoc mở đầu có **summary ngắn, chính xác, nhất quán** giữa class, constructor, methods và package.
3. Dùng đúng cú pháp inline **`{@summary Nội dung tóm tắt.}`** từ Java 10, đặt **ở đầu phần mô tả chính**.
4. Phân biệt summary do công cụ tự lấy từ câu đầu với summary do người viết đặt bằng `{@summary}`.
5. Đặt các block tags như `@param`, `@return`, `@throws`, `@see` và `@since` đúng mục đích.
6. Dùng `{@code}`, `{@link}` và `{@literal}` để hiển thị code, liên kết và ký tự đặc biệt trong mô tả.
7. Viết `package-info.java` để người học có thể đọc tổng quan của một package.
8. Tạo **stylesheet bổ sung** bằng `--add-stylesheet` mà không thay thế toàn bộ CSS mặc định của Javadoc.
9. Nhận biết `@apiNote`/`@implSpec`/`@implNote` là **custom tags thường cần đăng ký bằng `-tag`** với standard doclet; không mặc định chúng là thẻ built-in.
10. Tạo HTML từ command `javadoc`, kiểm warning/error với `-Xdoclint:all` và `-Werror`.
11. Kiểm thư mục output, summaries trong trang class/package, liên kết CSS và khả năng sử dụng.
12. Giữ kiểu dáng đồng nhất giữa nhiều packages/classes khi build tài liệu qua CI.
13. Phân biệt target `javac --release 10`/`--release 17` với version của Javadoc tool đang chạy.
14. Tránh những mẹo lỗi thời như các lựa chọn output frames/HTML4 đã bị bỏ khỏi JDK hiện đại.
15. Có checklist review API documentation trước khi publish.

**Sản phẩm cuối:** Một project Java đơn giản gồm `PriceCatalog.java`, `package-info.java`, `CatalogDemo.java` và `styles/api.css`, dùng `javadoc` tạo trang API có summary được kiểm chứng, kiểu dáng thống nhất và build QA nghiêm ngặt.

## 2. Vị trí của Javadoc trong chu trình phát triển

Javadoc dùng **documentation comments** `/** ... */` đặt ngay trước khai báo mà comment mô tả. **Standard doclet** xử lý chúng để tạo trang API có navigation, bảng tóm tắt types/methods, nội dung chi tiết, liên kết và chỉ mục tìm kiếm.

~~~text
Java source
  ├─ /** ... */ trước class/constructor/method/field
  ├─ package-info.java: giới thiệu package
  └─ (nếu dùng modules) module-info.java: giới thiệu module
                  │
                  │ javadoc + standard doclet + DocLint
                  ▼
          docs/index.html
          docs/<package>/package-summary.html
          docs/<package>/<Type>.html
          docs/index-all.html và những asset khác
                  │
                  ├─ CSS giao diện mặc định
                  └─ CSS bổ sung thống nhất
~~~

Tệp output cụ thể có thể khác giữa các phiên bản JDK/options. **Không** coi tên file HTML được nhắc trong sơ đồ là một API Java chính thức; xác minh output từ command đang chạy.

### 2.1. Javadoc và Java compiler có vai trò riêng

- `javac` kiểm và biên dịch source thành bytecode.
- `java` chạy class/JAR trên runtime.
- `javadoc` phân tích source/documentation comments và tạo website API.
- `-Xdoclint:all` kiểm cấu trúc documentation; nó **không** kiểm ý nghĩa nghiệp vụ thực sự của mỗi mô tả.
- Test Java kiểm behavior của implementation; kiểm HTML/Javadoc kiểm **độ đầy đủ và khả năng đọc tài liệu**.

Một source file compile thành công **không** chứng minh Javadoc đã đúng: thiếu `@param`, sai liên kết, thiếu summary hoặc HTML không hợp lệ vẫn có thể tồn tại. Ngược lại, Javadoc đẹp không bảo đảm runtime code đúng.

## 3. Mốc Java 10: thẻ `{@summary}`

Trước khi dùng explicit summary, standard doclet thường lấy **câu đầu tiên** của main description để làm tóm tắt xuất hiện trong các bảng/index. Cách cắt tự động có thể sai hoặc không như ý khi gặp viết tắt, dấu chấm, ký hiệu hoặc mô tả dài.

Ví dụ:

~~~java
/**
 * Calculates a value for U.S. customers.
 * The complete contract is explained below.
 */
public int calculate() { return 0; }
~~~

Đoạn trên là **snippet minh họa đặt bên trong một class**, không phải file runnable độc lập. Người đọc muốn summary có nghĩa trọn vẹn; Javadoc có thể suy ranh giới câu theo thuật toán/locale. Không nên xem thuật toán tự cắt là phương tiện bảo đảm wording chính xác cho API lớn.

### 3.1. Cách viết explicit summary

~~~java
/**
 * {@summary Calculates the total in integer units.}
 *
 * <p>The full description can explain constraints and exceptions.
 */
public int total() { return 0; }
~~~

**`{@summary ...}` là inline tag**, không phải `@summary` block tag. Khi đặt tại **đầu main description**, nội dung trong tag được dùng làm summary thay cho cách suy câu đầu. Phần mô tả bên dưới vẫn xuất hiện trong trang chi tiết.

### 3.2. Tại sao `{@summary}` hữu ích?

- Người viết **kiểm soát chính xác** câu xuất hiện trong bảng tóm tắt.
- Một câu ngắn có thể được lặp lại nhất quán ở navigation/index mà không làm mất thông tin chính.
- Chi tiết parameter, exceptions, preconditions có thể nằm bên dưới, không bị nhồi vào summary.
- Đỡ phụ thuộc heuristics cắt câu khi có viết tắt kiểu `e.g.`, `U.S.` hoặc nhiều dấu chấm.
- Một API lớn có thể áp cùng chính sách biên tập cho hàng trăm method comments.

### 3.3. Những điều kiện cần nhớ

1. Đặt `{@summary ...}` **ở đầu main description**, không đẩy xuống sau các đoạn HTML hoặc `@param`.
2. Summary nên là **một câu mô tả mục đích**, tránh danh sách tùy chọn/cảnh báo dài.
3. Không nhầm tag này với một **CSS style**; nó chọn text, còn kiểu chữ/màu là phần stylesheet.
4. Summary vẫn phải trung thực với implementation và không được thay thế hợp đồng đầy đủ.
5. Standard doclet hỗ trợ tag từ **JDK 10**; khi build bằng JDK đời hiện đại, kiểm Javadoc version và doclint tương ứng.

Nguồn lịch sử và hiện hành: [Oracle JDK 10 Release Notes](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html) và [JavaDoc Specification – JDK 25](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html).

## 4. Quy ước biên tập summary nhất quán

Nên thống nhất một phong cách cho toàn thư viện. Ví dụ trong một API có methods trả dữ liệu và thực hiện tính toán:

| API element | Summary tốt | Điều cần tránh |
| --- | --- | --- |
| Class | “Stores unit prices and creates deterministic quotes.” | “This is the PriceCatalog class with fields and methods.” |
| Constructor | “Creates a catalog from a map of unit prices.” | “Constructor.” |
| Lookup method | “Finds the unit price for a SKU.” | “Gets the data.” |
| Calculation method | “Computes the line total for a SKU and quantity.” | “This method calculates a lot of things.” |
| Count method | “Returns the number of products in this catalog.” | “Returns int.” |
| Package | “Provides immutable catalog prices and checked quotations.” | “Package of Java files.” |

**Một chính sách hiệu quả:**

- Bắt đầu bằng **động từ hướng hành động** phù hợp: Returns, Finds, Creates, Computes, Validates.
- Mô tả **hợp đồng quan sát được**, tránh lộ các chi tiết implementation có thể thay.
- Ưu tiên cụm từ nhất quán như “SKU”, “unit price”, “quantity”, “integer units”.
- Không viết “Returns the result” nếu người đọc không biết “result” là gì.
- Không nhồi @throws hoặc exception class vào summary, trừ khi đó là bản chất của API.
- Dùng dấu kết câu đúng; nội dung tag chỉ là text được render, không tự có một câu hấp dẫn.
- Nếu summary tương lai đổi, cập nhật nó cùng method contract và tests.

### 4.1. Summary khác long description

**Summary:** “Finds the unit price for a SKU.”

**Long description:** Mô tả behavior khi SKU không tồn tại, cách phân biệt giá 0 với absent, null-policy và cách kết quả được biểu diễn qua `OptionalInt`.

Summary phải có giá trị độc lập khi xuất hiện trong bảng tóm tắt, nhưng không cần chứa toàn bộ chi tiết của API. Long description và block tags bổ sung phần thiếu đó.

## 5. Bố cục chuẩn cho một Javadoc comment

Một ví dụ:

~~~java
/**
 * {@summary Computes a validated line total.}
 *
 * <p>All amounts are integer units.
 *
 * @param sku product identifier, never null
 * @param quantity nonnegative number of units
 * @return the extended line price
 * @throws NullPointerException if sku is null
 * @throws IllegalArgumentException if the SKU is unknown
 * @see #unitPrice(String)
 * @since 1.0
 */
public int quoteTotal(String sku, int quantity) { /* implementation */ }
~~~

Đây là **snippet cấu trúc minh họa**, không phải mã đầy đủ có thể compile độc lập; nội dung thật cần thêm quy tắc xử lý quantity/overflow nếu API thực sự có behavior đó.

Cấu trúc có hai phần:

1. **Main description:** summary ở đầu; sau đó giải thích context/contracts.
2. **Block tags:** từng tag ở đầu dòng (sau dấu `*` và spaces), ví dụ `@param` hoặc `@throws`.

**Không tiếp tục main description sau block tags** như thể `@param` không tồn tại; theo specification, block tags bắt đầu phần riêng của doc comment.

### 5.1. Ý nghĩa các thẻ phổ biến

| Tag | Dùng khi nào | Lưu ý |
| --- | --- | --- |
| `@param name ...` | Mô tả tham số của constructor/method | Tên trùng với signature; nói ý nghĩa và ràng buộc |
| `@return ...` | Mô tả giá trị trả về | Không dùng cho constructor/void methods |
| `@throws Exception ...` | Liệt kê lỗi có thể xảy ra | Nêu **điều kiện kích hoạt**, không chỉ lặp tên exception |
| `@see #method(...)` | Liên kết tham khảo bổ sung | Target phải resolve được |
| `@since 1.0` | Release **của thư viện** khi API được thêm | Không tự viết Java 10 nếu đó không phải version project |
| `@deprecated ...` | API thật sự deprecated | Chỉ dùng khi có kế hoạch thay thế rõ |
| `{@code ...}` | Inline code/identifiers | Escape nội dung tốt hơn plain HTML |
| `{@literal ...}` | Text literal có HTML metacharacters | Không áp kiểu monospace như code |
| `{@link Target}` | Liên kết tới API element | Có kiểm tra reference, không thay bằng text không có link |
| `{@summary ...}` | Chỉ định summary | Có ý nghĩa đặc biệt ở **đầu main description** |

### 5.2. Khi dùng annotations deprecation

Chỉ dùng khi API **thật sự** không còn nên được gọi:

~~~java
/**
 * {@summary Returns the old representation.}
 *
 * @deprecated Since 2.0, use {@link #newRepresentation()} instead.
 */
@Deprecated(since = "2.0", forRemoval = false)
public String oldRepresentation() {
    return newRepresentation();
}
~~~

Đoạn này là **minh họa bên trong một class** phải có method `newRepresentation()`, không phải code chạy độc lập. `@Deprecated` là annotation cho compiler/tooling, `@deprecated` là phần mô tả cho người đọc. Special Note của module yêu cầu **không lấy kiến thức lỗi thời làm khuyến nghị**: ở đây chỉ giải thích cách ghi migration docs còn áp dụng khi quản lý API cũ, không khuyên tạo API deprecated mới.

## 6. Liên kết, code và ký tự đặc biệt

Trong HTML API docs, các tham chiếu cần rõ và có thể click:

~~~java
/**
 * {@summary Finds a product.}
 *
 * <p>See {@link #unitPrice(String)} for unit-price lookup.
 * A missing value is represented by {@code OptionalInt.empty()}.
 * The literal text {@literal <unknown>} is not treated as an HTML tag.
 */
~~~

- `{@link #unitPrice(String)}`: liên kết đến một method cùng class.
- `{@link java.util.OptionalInt}`: liên kết đến type Java khi Javadoc có thông tin phù hợp.
- `{@code OptionalInt.empty()}`: in code, không tạo link.
- `{@literal <unknown>}`: hiện ký tự như text, không coi là HTML markup.

Không dùng thẻ HTML tùy tiện như `<font>`, `<center>`, HTML4 frame cấu trúc cũ. Với tài liệu hiện hành, ưu tiên HTML5 semantics, CSS mặc định, inline Javadoc tags và những headings hợp lý.

### 6.1. Link tường minh thay vì URL thô

Khi target tồn tại trong chính docs, dùng `{@link}` giúp Javadoc kiểm reference. Với liên kết ngoài, có thể dùng HTML anchor hợp lệ hoặc `-link`/`-linkoffline` để liên kết tới bộ API docs tương ứng, tùy môi trường có mạng.

Dẫn URL thô trong mô tả mà không kiểm định link dễ dẫn tới tài liệu gãy khi publish. Tích hợp **link checks/HTTP status verification** trong pipeline phù hợp policy, nhưng phải phân biệt **external link check** với DocLint (DocLint không kiểm mọi URL trên internet còn sống).

## 7. Tài liệu cấp package: `package-info.java`

Tạo file tại `src/dev/sample/catalog/package-info.java`:

~~~java
/**
 * {@summary Provides immutable catalog prices and checked quotations.}
 *
 * <p>This package demonstrates stable API summaries, contracts,
 * cross-references and an additive Javadoc stylesheet.
 *
 * @since 1.0
 */
package dev.sample.catalog;
~~~

Các điểm quan trọng:

- File tên **`package-info.java`** nằm trong đúng thư mục package.
- Comment nằm ngay **trước package declaration**.
- `@since 1.0` ở đây là release minh họa của **thư viện PriceCatalog**, không phải “Java 1.0”.
- Tóm tắt này có thể xuất hiện ở trang/package summary, giúp người đọc hiểu mục đích của package mà không mở từng class.
- Khi có module descriptor `module-info.java`, cũng có thể viết Javadoc cho module; chỉ nên thêm khi project thực sự dùng **Java Platform Module System**, không ép ứng dụng classpath nhỏ trở thành module nếu không cần.

Không lấy `package.html` dạng cũ làm cách khởi đầu cho project hiện đại: standard doclet có thể còn hỗ trợ vì tương thích lịch sử, nhưng **`package-info.java` là lựa chọn được khuyến nghị**.

## 8. Tổ chức project ví dụ

~~~text
catalog-api/
├── src/
│   └── dev/
│       └── sample/
│           ├── catalog/
│           │   ├── PriceCatalog.java
│           │   └── package-info.java
│           └── demo/
│               └── CatalogDemo.java
├── styles/
│   └── api.css
└── build/
    ├── classes/
    └── docs/       (do công cụ tạo)
~~~

Tên package được chọn để dễ hiểu trong ví dụ; trong dự án thực, tuân theo namespace và versioning policy của tổ chức.

**Giới hạn phạm vi:** Chỉ xuất bản package `dev.sample.catalog` làm public API docs. Class `CatalogDemo` thuộc package demo để có thể chạy kiểm behavior mà **không xuất hiện như API công khai** khi Javadoc chỉ tạo tài liệu cho `dev.sample.catalog`.

## 9. Source API đầy đủ: `PriceCatalog.java`

Đây là **toàn bộ file Java** đã được compile bằng `javac --release 17`. Nó cũng biên dịch được với `--release 10` trên compiler hỗ trợ target 10 vì chỉ dùng Java APIs từ Java 10 trở về trước, bao gồm `Map.copyOf` và local `var`.

~~~java
package dev.sample.catalog;

import java.util.Map;
import java.util.Objects;
import java.util.OptionalInt;

/**
 * {@summary Stores unit prices and creates deterministic quotes.}
 *
 * <p>Prices are nonnegative integer units, not formatted currency.
 * Input entries are copied when the catalog is constructed.
 *
 * @apiNote Use {@link #unitPrice(String)} to distinguish a missing SKU
 * from a price of zero before calculating a quote.
 * @since 1.0
 */
public final class PriceCatalog {
    private final Map<String, Integer> prices;

    /**
     * {@summary Creates a catalog from a map of unit prices.}
     *
     * @param prices mapping of non-null SKU keys to nonnegative unit prices
     * @throws NullPointerException if the map, a key or a value is null
     * @throws IllegalArgumentException if a price is negative
     */
    public PriceCatalog(Map<String, Integer> prices) {
        Objects.requireNonNull(prices, "prices");
        for (var entry : prices.entrySet()) {
            Objects.requireNonNull(entry.getKey(), "sku");
            Objects.requireNonNull(entry.getValue(), "unit price");
            if (entry.getValue() < 0) {
                throw new IllegalArgumentException("negative unit price");
            }
        }
        this.prices = Map.copyOf(prices);
    }

    /**
     * {@summary Finds the unit price for a SKU.}
     *
     * @param sku SKU identifier, never null
     * @return the price, or {@link OptionalInt#empty()} when absent
     * @throws NullPointerException if {@code sku} is null
     */
    public OptionalInt unitPrice(String sku) {
        Objects.requireNonNull(sku, "sku");
        var value = prices.get(sku);
        return value == null ? OptionalInt.empty() : OptionalInt.of(value);
    }

    /**
     * {@summary Computes the line total for a SKU and quantity.}
     *
     * <p>For example, SKU {@code A-1} with price {@code 300} and
     * quantity {@code 2} yields {@code 600}.
     *
     * @param sku SKU identifier, never null
     * @param quantity nonnegative number of units
     * @return the unit price multiplied by quantity
     * @throws NullPointerException if {@code sku} is null
     * @throws IllegalArgumentException if SKU is unknown or quantity is negative
     * @throws ArithmeticException if result exceeds the {@code int} range
     * @see #unitPrice(String)
     */
    public int quoteTotal(String sku, int quantity) {
        if (quantity < 0) {
            throw new IllegalArgumentException("negative quantity");
        }
        var price = unitPrice(sku).orElseThrow(
                () -> new IllegalArgumentException("unknown SKU: " + sku));
        return Math.multiplyExact(price, quantity);
    }

    /**
     * {@summary Returns the number of products in this catalog.}
     *
     * @return a nonnegative count of SKU entries
     */
    public int size() {
        return prices.size();
    }
}
~~~

### 9.1. Vì sao API này dễ viết docs đúng?

- Constructor xác nhận map không null, keys/values không null, prices không âm.
- `Map.copyOf` tạo immutable snapshot theo contract (không sửa map nguồn sau đó).
- `unitPrice` dùng `OptionalInt` giúp phân biệt **không có SKU** với **SKU có đơn giá bằng 0**.
- `quoteTotal` kiểm quantity không âm, SKU tồn tại, tính bằng `Math.multiplyExact` để báo overflow thay vì wrap integer.
- `size` trả số entry hiện có, không phụ thuộc cache nội bộ.
- Từng public element có **một summary rõ**, methods có param/return/throws đúng behavior.
- `{@link #unitPrice(String)}` nối docs nơi hướng dẫn người dùng tra giá và tính tổng.

### 9.2. Một chi tiết quan trọng: `@apiNote`

Trong file này có dòng `@apiNote`. Dù thẻ đó được dùng rộng rãi trong mã nguồn JDK, nó **không phải thẻ built-in của standard doclet được mọi project tự động chấp nhận**.

**Trong thí nghiệm thật**, chạy `javadoc -Xdoclint:all -Werror` mà **không khai báo custom tag** đã thất bại:

~~~text
error: unknown tag: apiNote
~~~

Để dùng nó với standard doclet, cần đăng ký, chẳng hạn:

~~~bash
-tag 'apiNote:a:API Note:'
~~~

Nếu dự án không muốn custom tags, thay phần chú thích thành một đoạn HTML5 bình thường:

~~~java
/**
 * {@summary Stores unit prices and creates deterministic quotes.}
 *
 * <p><strong>API note:</strong> Use {@link #unitPrice(String)}
 * to distinguish missing SKUs from a price of zero.
 */
~~~

**Không khẳng định `@implSpec` hay `@implNote` sẽ được nhận diện tự động**: các tên này cũng thường được khai báo làm custom tags trong các build JDK/documentation configurations. Khi dùng, cấu hình `-tag`/taglets và kiểm pipeline tương ứng. Đây là một bẫy thực tế của việc sao chép comment từ nguồn OpenJDK sang project riêng.

## 10. Chương trình chạy để đối chiếu contract

Tạo file `src/dev/sample/demo/CatalogDemo.java`:

~~~java
package dev.sample.demo;

import dev.sample.catalog.PriceCatalog;
import java.util.HashMap;

public final class CatalogDemo {
    public static void main(String[] args) {
        var source = new HashMap<String, Integer>();
        source.put("A-1", 300);
        source.put("B-2", 0);
        var catalog = new PriceCatalog(source);
        source.put("A-1", 900);

        System.out.println("snapshot-unit-price=" +
                catalog.unitPrice("A-1").orElseThrow());
        System.out.println("quoted-total=" +
                catalog.quoteTotal("A-1", 2));
        System.out.println("zero-price-present=" +
                catalog.unitPrice("B-2").isPresent());
        System.out.println("missing-sku=" +
                catalog.unitPrice("X-9").isEmpty());
        System.out.println("catalog-size=" + catalog.size());

        try {
            catalog.quoteTotal("X-9", 1);
        } catch (IllegalArgumentException e) {
            System.out.println("unknown-sku-rejected=true");
        }
        try {
            catalog.quoteTotal("A-1", -1);
        } catch (IllegalArgumentException e) {
            System.out.println("negative-quantity-rejected=true");
        }
        try {
            catalog.quoteTotal("A-1", Integer.MAX_VALUE);
        } catch (ArithmeticException e) {
            System.out.println("overflow-rejected=true");
        }
    }
}
~~~

### 10.1. Biên dịch và chạy trên POSIX shell

Đứng tại thư mục project:

~~~bash
mkdir -p build/classes

javac --release 17 -encoding UTF-8 -d build/classes \
  src/dev/sample/catalog/PriceCatalog.java \
  src/dev/sample/catalog/package-info.java \
  src/dev/sample/demo/CatalogDemo.java

java -cp build/classes dev.sample.demo.CatalogDemo
~~~

Đây là tập lệnh dành cho Bash/POSIX shell; **PowerShell không dùng dấu `\` để nối dòng**. Trên PowerShell, đặt các đường dẫn cùng một dòng và tạo directory bằng `New-Item` nếu cần.

### 10.2. Stdout **đúng như đã chạy kiểm chứng**

~~~text
snapshot-unit-price=300
quoted-total=600
zero-price-present=true
missing-sku=true
catalog-size=2
unknown-sku-rejected=true
negative-quantity-rejected=true
overflow-rejected=true
~~~

Chương trình đã được biên dịch và chạy với Java 21 trong môi trường kiểm thử tạm. Đầu ra **8 dòng** được ghi lại đúng thứ tự, không dựa vào ví dụ ước đoán.

### 10.3. Đối chiếu từng dòng với docs

1. `snapshot-unit-price=300`: map nguồn đổi sang 900 nhưng API giữ snapshot tại thời điểm dựng.
2. `quoted-total=600`: price 300 × quantity 2.
3. `zero-price-present=true`: SKU `B-2` tồn tại với giá 0.
4. `missing-sku=true`: `X-9` không có; `OptionalInt.isEmpty()` là true.
5. `catalog-size=2`: hai SKU ban đầu.
6. `unknown-sku-rejected=true`: SKU không tồn tại khiến quote từ chối bằng IllegalArgumentException.
7. `negative-quantity-rejected=true`: số lượng âm không hợp lệ.
8. `overflow-rejected=true`: multiplication vượt int range, bị `Math.multiplyExact` phát hiện.

**Bài học:** Mô tả `@param`/`@return`/`@throws` phải khớp behavior **đã được test**, không được viết hứa hẹn rộng hơn code. Nếu đổi implementation, review docs cùng thay đổi API.

## 11. Tạo stylesheet đơn giản và đồng nhất

Tạo file `styles/api.css`:

~~~css
:root { --api-accent: #14647d; }

body {
  font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
}

a {
  text-underline-offset: 0.15em;
}

a:focus-visible {
  outline: 2px solid var(--api-accent);
  outline-offset: 2px;
}
~~~

Mục tiêu không phải thiết kế lại Javadoc từ đầu mà **giữ cùng kiểu chữ, mức nhấn và chỉ báo keyboard focus** trên toàn bộ trang được tạo. CSS này đã được thử ở bản Javadoc 21 với `--add-stylesheet` và kiểm file output được liên kết.

### 11.1. Vì sao dùng `--add-stylesheet`?

- Standard doclet có **stylesheet mặc định** phục vụ cấu trúc docs, navigation, bảng, dark/light behavior tùy version.
- `--add-stylesheet` **bổ sung** CSS sau stylesheet mặc định; bạn có thể override có chọn lọc.
- `--main-stylesheet` (hoặc alias được tool hỗ trợ) **thay thế** main stylesheet, đòi tự đảm trách nhiều rule hơn; không cần thiết cho mục tiêu đổi vài quy ước nhỏ.
- CSS bổ sung có thể áp cho tất cả class/package pages trong một lần Javadoc generation.

**Chọn phương pháp có rủi ro thấp:** Dùng CSS mặc định làm nền, chỉ custom một tập nhỏ selectors/CSS variables. Khi nâng JDK, kiểm lại output vì DOM/CSS structure của standard doclet có thể thay đổi.

### 11.2. Accessibility không phải “màu đẹp”

Giữ độ tương phản chữ/nền đủ đọc; thể hiện keyboard focus rõ; không dùng màu làm **phương tiện duy nhất** để truyền trạng thái; không xóa outline focus chỉ để tối giản. Kiểm responsive layout trên viewport nhỏ và zoom cao bằng browser/visual QA phù hợp.

Javadoc default được xây dựng có hỗ trợ accessibility; thay toàn bộ CSS một cách vội vàng có thể làm mất các tiêu chuẩn đó. API docs thường được tra cứu nhiều năm, vì vậy bảo trì, khả năng tìm kiếm và tương phản quan trọng hơn một theme phức tạp.

### 11.3. Không ghi CSS trực tiếp vào doc comment

Đừng lặp `<style>...</style>` ở mỗi Javadoc comment. Thống nhất tại **stylesheet duy nhất** giúp đổi thiết kế có kiểm soát và tránh style conflict giữa các trang. Khi có multiple modules, dùng cùng CSS/style design system nhưng kiểm từng output site.

## 12. Build HTML Javadoc: câu lệnh đã kiểm

Giả sử project đứng tại cấu trúc ở phần 8, dùng POSIX shell:

~~~bash
mkdir -p build/docs

javadoc -quiet -Werror -Xdoclint:all \
  -encoding UTF-8 -docencoding UTF-8 \
  -d build/docs \
  --no-platform-links \
  -notimestamp \
  --add-stylesheet styles/api.css \
  -tag 'apiNote:a:API Note:' \
  -sourcepath src \
  -subpackages dev.sample.catalog
~~~

**Đây là command đã kiểm thành công trên OpenJDK 21** với source và CSS ở bài. Trên Windows PowerShell, dùng lệnh **một dòng** hoặc cú pháp nối dòng của PowerShell; trên CMD, nếu `-tag` có khoảng trắng ở title, dùng double quotes thay cho single quotes.

### 12.1. Ý nghĩa từng option

| Option | Vai trò | Điểm cần nhớ |
| --- | --- | --- |
| `-d build/docs` | Output directory | Không ghi đè source; publish site từ thư mục này |
| `-sourcepath src` | Root tìm source packages | Phải khớp layout thật |
| `-subpackages dev.sample.catalog` | Chọn package và packages con | Không kéo package demo vào public API |
| `-encoding UTF-8` | Encoding đọc Java source | Giữ Unicode tiếng Việt đúng |
| `-docencoding UTF-8` | Encoding của HTML output | Tránh lỗi ký tự trong site |
| `-Xdoclint:all` | Bật kiểm tra doc comment nghiêm ngặt | HTML/references/missing tags và các nhóm được hỗ trợ |
| `-Werror` | Xem warnings như build failure | Chặn xuất bản docs có warnings |
| `-quiet` | Giảm thông báo trạng thái | Không có nghĩa tắt errors |
| `--no-platform-links` | Tắt liên kết tự động tới platform docs | Hữu ích khi build offline; cân nhắc nếu muốn link JDK APIs |
| `-notimestamp` | Bỏ timestamp ẩn do doclet tạo | Giảm khác biệt output không liên quan giữa các builds |
| `--add-stylesheet styles/api.css` | Thêm CSS vào output | Giữ stylesheet mặc định |
| `-tag 'apiNote:a:API Note:'` | Đăng ký custom block tag | Không thiếu dòng này khi source dùng `@apiNote` |

DocLint **không** xác minh một SKU có thật, ngoại lệ có đúng business policy, ví dụ có chạy thực hay không hoặc external URL luôn sống. Kết hợp Javadoc build với unit/integration tests.

### 12.2. Cách viết PowerShell một dòng

~~~powershell
New-Item -ItemType Directory -Force build/docs | Out-Null
javadoc -quiet -Werror -Xdoclint:all -encoding UTF-8 -docencoding UTF-8 -d build/docs --no-platform-links -notimestamp --add-stylesheet styles/api.css -tag 'apiNote:a:API Note:' -sourcepath src -subpackages dev.sample.catalog
if ($LASTEXITCODE -ne 0) { throw 'Javadoc failed' }
~~~

**Khác shell:** dấu `\` nối dòng của Bash không có cùng ý nghĩa trong PowerShell. Việc gọi lệnh Java qua PowerShell cũng cần kiểm `$LASTEXITCODE`, không chỉ dựa vào việc có stdout text.

## 13. Kết quả kiểm thử HTML Javadoc thật

Lệnh strict Javadoc ở trên đã tạo những file sau:

~~~text
build/docs/index.html
build/docs/api.css
build/docs/dev/sample/catalog/PriceCatalog.html
build/docs/dev/sample/catalog/package-summary.html
~~~

Kiểm trực tiếp trên output HTML:

| Điều kiểm | Kết quả đã quan sát |
| --- | --- |
| `index.html` tồn tại và không rỗng | PASS |
| `PriceCatalog.html` tồn tại và không rỗng | PASS |
| `package-summary.html` tồn tại và không rỗng | PASS |
| `api.css` được copy vào output | PASS |
| Summary class có text “Stores unit prices and creates deterministic quotes.” | PASS |
| Summary lookup method có text “Finds the unit price for a SKU.” | PASS |
| Summary quotation method có text “Computes the line total for a SKU and quantity.” | PASS |
| Summary count method có text “Returns the number of products in this catalog.” | PASS |
| Package summary có text “Provides immutable catalog prices and checked quotations.” | PASS |
| Trang class có tham chiếu `api.css` | PASS |
| HTML có heading từ custom `@apiNote` đã đăng ký | PASS |
| `-Xdoclint:all` cùng `-Werror` | PASS |

Phạm vi kiểm thử: các file và text/links trong HTML output đã sinh, không phải một cuộc kiểm nghiệm thủ công trên mọi trình duyệt/thiết bị. Khi deploy tài liệu thật, cần thêm **browser QA** về accessibility, responsive layout, broken links và cảm nhận người dùng.

### 13.1. Tự kiểm bằng shell

~~~bash
test -s build/docs/index.html
test -s build/docs/api.css
test -s build/docs/dev/sample/catalog/PriceCatalog.html

grep -F "Stores unit prices and creates deterministic quotes." \
  build/docs/dev/sample/catalog/PriceCatalog.html

grep -F "api.css" \
  build/docs/dev/sample/catalog/PriceCatalog.html
~~~

Đây là các lệnh **POSIX shell**; nếu dùng PowerShell, `Test-Path` và `Select-String` là các công cụ tương đương về ý định. Dùng `-F` khi tìm nguyên text để tránh regex metacharacters làm thay đổi kết quả.

**Đừng chỉ grep string rồi khẳng định visual style đẹp:** kiểm CSS đã được link, trình duyệt thực render ra sao và keyboard navigation còn dùng được hay không.

## 14. Biên dịch target Java 10 khác với phiên bản công cụ Javadoc

Một source dùng `{@summary}` trong doc comment có thể được kiểm với Javadoc tool hiện đại, trong khi bytecode Java được compiler nhắm Java 10:

~~~bash
mkdir -p build/classes10

javac --release 10 -encoding UTF-8 -d build/classes10 \
  src/dev/sample/catalog/PriceCatalog.java \
  src/dev/sample/catalog/package-info.java

javap -verbose -classpath build/classes10 dev.sample.catalog.PriceCatalog
~~~

Trong test với compiler OpenJDK 21, class header của `PriceCatalog` cho:

~~~text
minor version: 0
major version: 54
~~~

`54` là class-file major cho Java 10. Điều này chứng minh **code có thể được biên dịch tới target Java 10** bằng compiler đã thử, không chứng minh production nên chạy Java 10 hoặc mọi compiler tương lai sẽ còn hỗ trợ `--release 10`.

Khi compile bằng `--release 17` trên cùng nguồn, `javap` cho **major version 61**. Javadoc tool tự nó có **tool version**, không phải class-file major; đừng suy rằng `javadoc 21` luôn tạo Java21 bytecode hoặc `{@summary}` chỉ hoạt động khi biên dịch bytecode major54.

### 14.1. Javadoc comment và Java language level

`/** ... */` là dạng comment đã có từ lâu; `{@summary}` được **standard doclet JDK10+ diễn giải**. Nếu Java compiler chỉ biên dịch code, nội dung tag không trở thành Java statement runtime. Nhưng muốn HTML có summary đúng, hãy build bằng Javadoc/doclet có hỗ trợ tag ấy.

**Không** dùng options hoặc custom doclets từ JDK 8 đã bị thay thế để sinh Javadoc cho dự án hiện đại chỉ vì nội dung học nằm trong Java 10.

## 15. Chiến lược styling nhất quán ở quy mô thư viện

Giả sử một thư viện có nhiều packages. Hãy chuẩn hóa:

1. Quy tắc summary của class/package/method và ngôn ngữ nhất quán.
2. Cách gọi tên entities: SKU, quantity, unit price, optional value.
3. Thứ tự block tags: `@param` theo thứ tự signature, rồi `@return`, `@throws`, `@see`, `@since` theo convention được đội nhóm thống nhất.
4. Mức độ chi tiết của null policy, default behavior, empty result và exceptions.
5. Quy tắc link: loại nào dùng `{@link}`, loại nào dùng external URL có kiểm.
6. Một file CSS được áp trong mọi docs build.
7. Các chỉ tiêu accessibility và browser QA.
8. Một command/build plugin configuration thống nhất Javadoc/doclint/warnings.
9. Tên/version của thư viện trong `@since`, không tự nhầm với Java SE version.
10. Quy trình review và publish docs cùng code release.

### 15.1. Không copy CSS từ trang HTML output rồi sửa tùy tiện

Standard doclet có thể thay cấu trúc HTML/CSS giữa các JDK releases. Nếu sao chép `stylesheet.css` của một JDK và thay nó hoàn toàn ở JDK khác, UI có thể mất navigation/khả năng responsive. Dùng `--add-stylesheet` và override ít selectors/CSS variables là hướng duy trì dễ hơn.

### 15.2. Cross-package links

Khi cùng build nhiều packages, Javadoc có thể tạo liên kết giữa các types mà nó biết. Nếu một dependency không được đưa vào Javadoc set, hãy dùng cấu hình `-link` hoặc `-linkoffline` tương ứng với docs version cần tham chiếu, và kiểm links khi xuất bản.

### 15.3. API docs và internationalization

Với docs viết tiếng Việt, dùng source/output encoding UTF-8; tránh tách dấu tiếng Việt trong mọi bước copy/build; kiểm nội dung hiển thị trên browser. Summary nên viết đúng một ngôn ngữ/chính tả chuẩn. Không trộn tên kỹ thuật khác nhau cho cùng một concept nếu có glossary thống nhất.

## 16. Những lỗi thường gặp khi dùng `{@summary}`

| Lỗi | Hậu quả | Sửa |
| --- | --- | --- |
| Viết `@summary text` | Không phải inline tag chuẩn để định summary | Viết `{@summary text}` |
| Đặt `{@summary}` sau đoạn mô tả dài | Không được dùng theo ý nghĩa special summary | Đưa nó vào đầu main description |
| Nhồi 5 câu vào summary | Bảng tóm tắt khó scan | Một câu đủ ý, chi tiết ở dưới |
| Summary ghi sai behavior | Người dùng dựa vào lời hứa sai | Đồng bộ docs với tests/implementation |
| Copy cùng summary cho mọi method | Không phân biệt API methods | Mỗi method nói chức năng riêng |
| Viết summary như tên method | Thiếu ngữ nghĩa | Động từ + đối tượng + điều kiện chính |
| Dùng viết tắt nhiều dấu chấm rồi phụ thuộc heuristic | Summary có thể bị cắt sai | Dùng explicit `{@summary}` |
| Bỏ block tags cần thiết | Hợp đồng khó hiểu, DocLint có thể cảnh báo | Bổ sung `@param`/`@return`/`@throws` |
| Lặp lại cùng contract hai lần mâu thuẫn | Summary và detailed docs trái nhau | Chọn một wording thống nhất |

### 16.1. Khi không cần `{@summary}`

Nếu câu mở đầu đã là một câu ngắn, chuẩn và Javadoc tạo summary đúng, việc dùng tag **không bắt buộc**. Tuy nhiên với một dự án muốn chính sách nhất quán, chọn “luôn explicit summary” cũng là convention hợp lệ. Quan trọng là tác động lên **generated summary** được kiểm.

## 17. Những lỗi thường gặp về style và custom tags

| Biểu hiện | Nguyên nhân có thể | Hướng xử lý |
| --- | --- | --- |
| `error: unknown tag: apiNote` | Dùng custom `@apiNote` nhưng thiếu `-tag` | Đăng ký custom tag hoặc dùng HTML note |
| CSS không thấy trên trang | Sai path của stylesheet, build chưa copy hoặc browser cache | Kiểm `--add-stylesheet`, file output, link href |
| Header/navigation bị biến dạng | Override CSS mặc định quá rộng | Dùng CSS bổ sung với phạm vi hẹp |
| Trang mobile khó xem | CSS dùng fixed widths/overflow | Kiểm viewport và responsive behavior |
| Không thấy keyboard focus | CSS xóa outline | Dùng `:focus-visible` có contrast |
| Gõ `-Xdoclint:all` nhưng CI vẫn pass khi warning | Thiếu `-Werror` hoặc flags không vào task thật | Kiểm exit code/build logs |
| Broken link `{@link #method}` | Sai method signature/target không hiện diện | Sửa link và chạy DocLint |
| `@since` ghi phiên bản Java thay cho project | Hiểu sai contract versioning | Dùng release thực của thư viện |
| Đường docs output cũ còn file | Không clean target trước build | Clean riêng output docs khi được phép |
| Link ra Internet lỗi khi build offline | Dùng platform/external links cần network | Dùng `--no-platform-links` hoặc linkoffline có đúng dữ liệu |
| Doc comments render code sai | HTML metacharacters chưa escape | Dùng `{@code}` hoặc `{@literal}` |
| Build với Javadoc đời khác | Tool versions khác defaults/HTML | Pin JDK build version và test CI |

**Quan sát kiểm thử cụ thể:** Bản thử ban đầu dùng `@apiNote` nhưng chưa khai báo `-tag` **bị DocLint/Javadoc từ chối**. Bổ sung `-tag 'apiNote:a:API Note:'` làm strict build thành công, HTML có heading API Note. Không bỏ qua warnings bằng cách tắt toàn bộ DocLint nếu căn nguyên là custom tag chưa đăng ký.

## 18. Kiểm tra tính đúng của documentation bằng test cases

### 18.1. Test summary và HTML

Báo QA PASS nếu:

- Class, constructor, public methods và package có summary/description phù hợp.
- `{@summary}` được đặt đúng ở đầu và text xuất hiện trong generated output.
- Không có thiếu @param hoặc @return theo conventions.
- `{@link}` targets cần thiết resolve được.
- CSS được copy vào docs, link của file HTML trỏ đúng path.
- DocLint/Werror không còn lỗi/warnings.

### 18.2. Test API runtime behavior

Báo QA PASS nếu:

- Map nguồn thay đổi sau khi dựng catalog không đổi snapshot.
- SKU có giá 0 được phân biệt với SKU không tồn tại.
- Quote hợp lệ trả đúng total.
- Quantity âm và SKU không tồn tại được từ chối theo documented contract.
- Overflow được phát hiện, không âm thầm wrap.
- Source compile đúng target release.
- Tests chạy trên runtime target thực nếu yêu cầu deploy compatibility.

### 18.3. Test trải nghiệm

Sau khi build, mở `build/docs/index.html` trong trình duyệt phù hợp hoặc trên một doc site tạm và kiểm:

- Navigation và search có dùng được không?
- Link package ↔ class ↔ methods có dẫn tới mục đúng?
- Bảng summary có quét đọc dễ không?
- Nội dung khác màu/trạng thái có đủ contrast?
- Di chuyển bằng Tab có thấy focus?
- Zoom 200%/màn hình nhỏ có bị cắt, tràn?
- CSS/additional assets có bị CORS/CSP/server path ảnh hưởng không?
- Có thông tin nội bộ/secrets bị đưa vào Javadoc không?

**Lưu ý:** Trong bài đã kiểm **tạo file + text + CSS link** bằng công cụ, **không tuyên bố** đã chạy full browser accessibility audit. Checklist browser là bước bắt buộc khi publish tài liệu thực tế.

## 19. CI/CD: đưa Javadoc thành một bước build có kiểm soát

Một pipeline tốt nên thực hiện:

1. Chọn **JDK build/version còn được hỗ trợ** và cố định theo policy.
2. Checkout source tại đúng commit.
3. Chạy compile tests trên target release.
4. Chạy `javadoc -Xdoclint:all -Werror` với CSS và custom tags config thống nhất.
5. Kiểm output HTML quan trọng bằng file checks và summary checks.
6. Chạy link checker và visual/a11y checks khi cần.
7. Chỉ publish docs khi các bước QA qua hết.
8. Gắn docs artifact với application/library release và commit.
9. Có retention/rollback version cũ khi site docs thay đổi.
10. Không publish internal APIs hoặc secrets chỉ vì `javadoc` nhìn thấy chúng.

### 19.1. Maven và Gradle

Maven Javadoc Plugin và Gradle Javadoc tasks có thể tích hợp sinh tài liệu vào build; nhưng **đừng cho rằng options của lệnh CLI tự động chuyển nguyên xi thành một property trong mọi plugin version**. Cần cấu hình theo tài liệu plugin/Gradle version thực và kiểm lệnh Javadoc cuối cùng trong build logs.

Với multi-module project, kiểm output được sinh cho đúng modules/public packages và dùng stylesheet **cùng phiên bản**. Trong IDE, JDK chạy IDE có thể khác JDK mà build tool chọn cho Javadoc task; khi output khác giữa máy và CI, hãy kiểm JDK/Javadoc toolchain trước.

### 19.2. Reproducibility

`-notimestamp` giúp giảm một nguồn thay đổi không có ý nghĩa, nhưng **không** đảm bảo hai JDK khác version tạo HTML giống hệt: layout/default CSS, index scripts, signatures và doclet implementation có thể thay đổi. Khi cần reproducibility nghiêm ngặt, pin JDK/tool versions và kiểm artifacts, không chỉ pin CSS file.

## 20. Bài tập thực hành có đáp án

**Bài 1.** Java 10 giới thiệu thẻ gì để kiểm soát API summary? — **`{@summary ...}`**.

**Bài 2.** Khi nào tag `{@summary}` được dùng làm summary? — Khi đặt **ở đầu main description** theo standard doclet specification.

**Bài 3.** `@summary Text` có phải cú pháp thay thế? — **Không**; cần inline tag với braces.

**Bài 4.** Có nhất thiết mọi comment phải dùng `{@summary}` không? — **Không**; nhưng dùng như một convention thống nhất là lựa chọn hợp lệ.

**Bài 5.** Constructor nên có `@return`? — **Không**; constructor không trả return value theo method contract.

**Bài 6.** Method có tham số `sku` cần `@param` tên gì? — **`@param sku`**, khớp signature.

**Bài 7.** Nếu method ném IllegalArgumentException, phần docs nên ghi gì? — Điều kiện kích hoạt (SKU unknown, quantity âm, v.v.), không chỉ tên exception.

**Bài 8.** `{@code ...}` khác `{@link ...}`? — Một tag định dạng code, tag kia tạo link API.

**Bài 9.** Tài liệu package đặt ở đâu? — **`package-info.java`** trong package source folder.

**Bài 10.** Vì sao không dựa vào `package.html` cho dự án mới? — Dạng đó chủ yếu còn được hỗ trợ vì historical compatibility; `package-info.java` được khuyến nghị.

**Bài 11.** Muốn thay màu/kiểu chữ nhẹ mà giữ Javadoc CSS mặc định dùng option nào? — **`--add-stylesheet`**.

**Bài 12.** `--main-stylesheet` khác gì? — Nó **thay thế** default main stylesheet, cần bảo trì nhiều rule hơn.

**Bài 13.** Vì sao nên giữ `:focus-visible`? — Hiển thị vị trí keyboard focus, cải thiện accessibility.

**Bài 14.** `-Xdoclint:all` và `-Werror` khác gì? — Một bật các nhóm kiểm tài liệu; một biến warnings thành build failures.

**Bài 15.** Dùng `@apiNote` rồi nhận unknown tag phải làm gì? — Đăng ký custom tag với `-tag` hoặc dùng mô tả HTML thường; không tắt kiểm toàn bộ.

**Bài 16.** `@apiNote` là built-in standard tag trên Javadoc21? — **Không** trong lần kiểm Javadoc tiêu chuẩn; cần registration ở demo.

**Bài 17.** `--no-platform-links` dùng khi nào? — Khi muốn tránh platform links tự động, ví dụ build offline; nó cũng bỏ link tiện ích tới platform docs.

**Bài 18.** `@since 1.0` nghĩa Java 1.0? — **Không** trong demo; đó là version của **thư viện**.

**Bài 19.** Class major 54 nghĩa Javadoc tool version 10? — **Không**; đó là bytecode target Java 10.

**Bài 20.** Javadoc HTML build PASS đủ để cam kết API đúng nghiệp vụ? — **Không**; cần runtime tests và review hợp đồng.

**Bài 21.** CSS file tồn tại trong build/docs đã chứng minh được site render đẹp? — **Chưa**; cần kiểm link, render browser, a11y/visual.

**Bài 22.** Có thể dùng JDK mới để tạo Javadoc cho code nhắm Java 10? — Có thể khi tool hỗ trợ source/language target và code/flags phù hợp; cần kiểm trên phiên bản JDK thực.

**Bài 23.** Tại sao phải kiểm summary ở generated HTML chứ không chỉ source? — Để biết standard doclet thực chọn và render đúng phần tóm tắt.

**Bài 24.** Cách đảm bảo style toàn thư viện nhất quán? — Dùng design rules, một stylesheet bổ sung, một doc build config, code review và visual QA chung.

## 21. Checklist cuối trước khi publish API docs

- [ ] Comment `/** ... */` đặt đúng trước public API declaration.
- [ ] Mỗi API element có summary một câu tự đủ nghĩa.
- [ ] `{@summary ...}` ở **đầu main description** khi cần kiểm soát explicit summary.
- [ ] Không nhầm inline `{@summary}` với block `@summary`.
- [ ] `@param` tên và thứ tự khớp signature.
- [ ] `@return` mô tả giá trị, không dùng ở constructors/void.
- [ ] `@throws` chỉ rõ điều kiện lỗi quan trọng và khớp implementation.
- [ ] `{@link}` references resolve đúng.
- [ ] `{@code}`/`{@literal}` được dùng đúng cho literals.
- [ ] `package-info.java` có tổng quan hữu ích.
- [ ] `@since` là version thư viện, không nhầm Java SE release.
- [ ] `@Deprecated`/`@deprecated` chỉ dùng khi API thực deprecated và có migration path.
- [ ] Custom `@apiNote`/`@implSpec`/`@implNote` được đăng ký nếu sử dụng.
- [ ] CSS dùng `--add-stylesheet`, không phá default layout.
- [ ] Font, spacing, focus, contrast và responsive được review.
- [ ] HTML5 trong comments hợp lệ.
- [ ] `-encoding UTF-8` và `-docencoding UTF-8` đúng.
- [ ] `-Xdoclint:all -Werror` chạy trên JDK đã chọn.
- [ ] Sinh đúng package/class pages, có index/navigation.
- [ ] Summary text xuất hiện đúng trong generated HTML.
- [ ] CSS asset được copy và trang HTML trỏ đúng.
- [ ] Runtime unit/integration tests xác minh public contract.
- [ ] Có CI steps và lưu kết quả gắn với release commit.
- [ ] Không xuất bản internal classes/secrets ngoài intended API.
- [ ] Dùng JDK/Javadoc version còn được hỗ trợ, không áp HTML4/frames behavior lỗi thời.
- [ ] Đã kiểm link/visual/accessibility trên trình duyệt trước khi phát hành.

## 22. Tài liệu tham khảo chính thức và còn áp dụng

1. [Oracle JDK 10 Release Notes – Comment Tag for Summary of an API Description](https://www.oracle.com/java/technologies/javase/10-relnote-issues.html): `{@summary}` được thêm từ Java 10, JDK-8173425.
2. [Oracle Java SE 25 – Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): cú pháp doc comments, `{@summary}`, block/inline tags và scope.
3. [Oracle Java SE 25 – The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): options `-d`, `--add-stylesheet`, `-tag`, `-Werror` và DocLint.
4. [Oracle Java SE 17 – Documentation Comment Specification](https://docs.oracle.com/en/java/javase/17/docs/specs/javadoc/doc-comment-spec.html): tính năng Javadoc vẫn áp dụng trong JDK17.
5. [Oracle Java SE 17 – The javadoc Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javadoc.html): lệnh và standard doclet.
6. [Oracle – How to Write Doc Comments for the Javadoc Tool](https://www.oracle.com/java/technologies/javase/writing-doc-comments.html): biên tập API descriptions/tags (đối chiếu với đặc tả mới khi có khác biệt).
7. [OpenJDK JDK-8173425 – Javadoc needs a new tag to specify the summary](https://bugs.openjdk.org/browse/JDK-8173425): mục tiêu kỹ thuật của `{@summary}`.
8. [Oracle Java SE 25 – Javadoc Overview](https://docs.oracle.com/en/java/javase/25/javadoc/index.html): tính năng và khả năng Javadoc tool hiện hành.
9. [Oracle Java SE 17 – Map.copyOf](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Map.html#copyOf(java.util.Map)): immutable snapshot behavior trong ví dụ.
10. [Oracle Java SE 17 – OptionalInt](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/OptionalInt.html): contract cho SKU absent vs price 0.
11. [Oracle Java SE 17 – Math.multiplyExact](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Math.html#multiplyExact(int,int)): kiểm overflow trong demo.
12. [Oracle Java SE 17 – javac](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javac.html): `--release` và source/target bytecode.
13. [Oracle Java SE 17 – javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html): kiểm class-file major/minor.
14. [MDN – CSS :focus-visible](https://developer.mozilla.org/en-US/docs/Web/CSS/:focus-visible): keyboard focus styling vẫn áp dụng cho web docs.
15. [W3C Web Content Accessibility Guidelines 2.2](https://www.w3.org/TR/WCAG22/): tiêu chuẩn tham khảo về contrast, navigation và focus visibility.

**Tổng kết:** Tính năng `{@summary ...}` của **Java 10** vẫn giúp chủ động định nghĩa đoạn tóm tắt API xuất hiện trong bảng/index trên **Javadoc hiện đại**. Để tài liệu vừa **đúng nội dung** vừa **nhất quán về kiểu dáng**, hãy viết contract rõ với `@param`/`@return`/`@throws`, thêm `package-info.java`, dùng `{@link}`/`{@code}`, bổ sung một CSS duy nhất qua `--add-stylesheet`, đăng ký custom tags như `@apiNote` bằng `-tag` khi có, và kiểm `javadoc -Xdoclint:all -Werror`. Sau khi sinh HTML, kiểm **summary text, link, CSS, accessibility** và đối chiếu với **tests của API thật** trước khi publish.
