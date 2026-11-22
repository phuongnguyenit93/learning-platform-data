# Tra cứu qua hộp tìm kiếm và thẻ {@index ...} trong Javadoc mô-đun

## 1. Mục tiêu

Tài liệu API Java thường có nhiều mô-đun (module), package, lớp và phương thức. Người đọc cần tìm đúng khai báo hoặc thuật ngữ nghiệp vụ mà không phải lần theo toàn bộ cây điều hướng. **Standard Doclet** của công cụ `javadoc` tạo trang HTML kèm **hộp Search**, **chỉ mục chữ cái (A–Z Index)** và các mục tìm kiếm được tác giả khai báo bằng **inline tag `{@index ...}`**.

Từ Java 9, hai khả năng liên quan đã được đưa vào Javadoc: tìm kiếm nội dung đã được lập chỉ mục và thẻ `{@index}` để thêm từ khóa không nhất thiết là tên class/method. Chúng vẫn được hỗ trợ trong JDK hiện đại.

Hoàn thành bài này, bạn có thể:

- Biết Javadoc tìm được những loại mục nào, phân biệt search theo **chỉ mục** với tìm kiếm toàn bộ văn bản.
- Sử dụng hộp Search để tìm module, package, type, member và thuật ngữ do `{@index}` đánh dấu.
- Viết đúng hai dạng `{@index word description}` và `{@index "multi word phrase" description}`.
- Gắn từ khóa vào Javadoc của `module-info.java`, lớp hoặc phương thức, tạo liên kết dẫn đến đúng vị trí giải thích.
- Tạo tài liệu module với `javadoc --module-source-path ... --module ...`, kiểm tra chỉ mục và xử lý lỗi tìm kiếm.
- Đặt ra quy tắc từ khóa nhất quán để người đọc tìm được khái niệm nghiệp vụ mà không làm chỉ mục bị nhiễu.

**Phạm vi:** API và quy trình tạo tài liệu bằng JDK 17+ với Standard Doclet. Ví dụ được kiểm tra trên JDK 24. Không sử dụng cơ chế Javadoc cũ đã lỗi thời hoặc công cụ xử lý HTML không còn cần thiết.

## 2. Ba cách tìm tài liệu: điều hướng, Search và A–Z Index

| Cơ chế | Cách dùng | Mục đích |
| --- | --- | --- |
| Điều hướng module/package/class | Mở trang module rồi chọn package, class và member | Tìm theo cấu trúc API khi đã biết thành phần |
| Hộp **Search** | Nhập tên hoặc một phần tên vào ô tìm kiếm trên trang tài liệu | Gợi ý và dẫn đến các **mục đã được lập chỉ mục**; sử dụng JavaScript ở trình duyệt |
| **Index** / A–Z Index / **Search Tags** | Mở chỉ mục chữ cái hoặc trang danh sách Search Tags | Duyệt các tên API và mục thuật ngữ theo danh sách HTML, hữu ích khi chưa biết chính xác từ khóa |

**Điểm mấu chốt:** Search trong Javadoc là **tìm kiếm trên chỉ mục được tạo ra từ khai báo API và search tags**, không phải công cụ quét tùy ý mọi từ trong toàn bộ đoạn mô tả trên mọi trang. Chỉ viết chữ “order lookup” trong một đoạn văn không bảo đảm từ đó trở thành một **mục riêng** trong Search. Nếu bạn muốn người dùng tìm đúng cụm từ nghiệp vụ đó, đánh dấu nó bằng `{@index "order lookup"}`.

Hộp Search sử dụng JavaScript và dữ liệu chỉ mục tĩnh được sinh cùng HTML. Nếu người xem tắt JavaScript, tìm kiếm tương tác có thể không dùng được; họ vẫn có thể duyệt chỉ mục chữ cái bằng HTML nếu trang Index được tạo. Đừng loại bỏ JavaScript hoặc các tài nguyên đi kèm trong quy trình xuất bản tài liệu.

## 3. Những gì Javadoc có thể tìm

Standard Doclet lập chỉ mục các đối tượng được đưa vào tài liệu:

| Đối tượng | Ví dụ cần tìm | Vị trí đích |
| --- | --- | --- |
| Module | `com.example.catalog` | Trang module summary |
| Package | `com.example.catalog` trong module tương ứng | Trang package summary |
| Type | `Catalog` | Trang class/interface/enum |
| Member | `lookup(String)`, `lookup`, một trường/constructor cụ thể | Khu vực member trên trang type |
| Search Tag | `order lookup`, `SKU`, `product id` | Vị trí đặt thẻ `{@index}` trong Javadoc |

Một phần tên có thể đủ để tìm, nhất là ở đầu tên hoặc ranh giới từ; tìm kiếm cũng hỗ trợ cách viết viết tắt theo CamelCase và nhiều từ cách nhau bằng khoảng trắng theo quy tắc của đặc tả phiên bản JDK. Ví dụ trong Java API chuẩn, `InpStr` có thể tìm `InputStream`. Khi cần phân biệt phương thức overload, nhập cả một phần tên chứa signature/kiểu tham số phù hợp.

Với tài liệu module, tìm theo tên module giúp đi đến module summary; tìm type/member giúp đi thẳng vào API. `{@index}` bổ sung **ngôn ngữ người đọc sử dụng**: ví dụ họ biết “SKU” nhưng chưa biết lớp Java nào xử lý mã hàng.

Các quy tắc xếp hạng, ranh giới từ và chi tiết khớp chuỗi được mô tả trong **Javadoc Search Specification** của phiên bản JDK. Không xây ứng dụng phụ thuộc thứ tự gợi ý chính xác của một lần build; thứ tự và mô hình kết quả có thể thay đổi khi nâng JDK.

## 4. Cú pháp thẻ `{@index}`

`{@index}` là **inline tag**: nó nằm trong comment tài liệu bắt đầu bằng `/**` và kết thúc bằng `*/`, không phải annotation Java và cũng không phải block tag `@index` đặt riêng ở đầu dòng.

Hai cú pháp chuẩn:

```text
{@index word}
{@index word mô tả ngắn}
{@index "cụm từ nhiều chữ"}
{@index "cụm từ nhiều chữ" mô tả ngắn}
```

- **word**: thuật ngữ một token, chẳng hạn `SKU`. Viết `{@index SKU Stock Keeping Unit}` khi muốn thêm mô tả giải thích từ viết tắt.
- **"cụm từ nhiều chữ"**: đặt trong dấu ngoặc kép để Javadoc hiểu toàn bộ cụm là một mục, ví dụ `{@index "order lookup" Tra cứu theo mã đơn}`.
- **Mô tả** là tùy chọn. Khi có, nó giúp người đọc hiểu ý nghĩa của thuật ngữ trong danh sách kết quả. **Mô tả không phải một phần của từ khóa**.
- Thẻ được xử lý tại **vị trí nó xuất hiện** trong comment. Standard Doclet tạo một mốc liên kết tại vị trí đó, và kết quả tìm kiếm có thể nhảy về đúng đoạn giải thích.

Ví dụ:

```java
/**
 * Tra cứu một mặt hàng theo {@index SKU Stock Keeping Unit}.
 * Một {@index "product id" mã định danh sản phẩm} có thể là khóa tra cứu.
 */
public final class Catalog {
    // Các thành viên của lớp.
}
```

Đây là đoạn minh họa, chưa phải chương trình có thể biên dịch độc lập. `SKU` và `product id` là hai mục tìm kiếm **riêng biệt**; “Stock Keeping Unit” và “mã định danh sản phẩm” là mô tả. Tên lớp `Catalog` vốn đã được Javadoc lập chỉ mục dưới mục type, nên không nhất thiết phải dùng `{@index Catalog}` chỉ để lặp lại tên lớp.

### 4.1. Vị trí đặt `{@index}`

Có thể đặt inline tag trong phần mô tả Javadoc của module, package, class/interface, constructor, method, field và các vị trí mô tả được standard doclet cho phép. Trong bài này ta minh họa ba vị trí:

1. **`module-info.java`:** giới thiệu khái niệm ở phạm vi toàn module, giúp người đọc từ khóa đi tới module summary.
2. **Javadoc của class:** mô tả khái niệm nghiệp vụ gắn với type.
3. **Javadoc của method:** mô tả một thuật ngữ ngay trong phương thức có ý nghĩa liên quan.

Đặt tag **gần đoạn giải thích chính xác nhất**. Mục tiêu không chỉ là xuất hiện trong hộp gợi ý mà còn giúp người dùng đến đúng vị trí sau khi bấm vào kết quả.

### 4.2. Phân biệt với `{@link}` và `@see`

| Tag | Câu hỏi nó giải quyết | Kết quả |
| --- | --- | --- |
| `{@index "order lookup"}` | “Người dùng gõ thuật ngữ này thì có tìm được không?” | Thêm mục search tag và mốc liên kết tại vị trí trong nội dung |
| `{@link Catalog}` hoặc `{@link #lookup(String)}` | “Từ đoạn văn này, làm sao chuyển tới một khai báo Java?” | Tạo liên kết tới API được tham chiếu |
| `@see Catalog` | “Có những API liên quan nào để xem thêm?” | Tạo mục liên quan trong phần See Also |

`{@index}` không thay thế liên kết API giữa các trang. Có thể kết hợp một thuật ngữ đã lập chỉ mục với `{@link}` khi đoạn mô tả cần cả chức năng tra cứu và điều hướng.

## 5. Ví dụ hoàn chỉnh: tài liệu cho một Java module

Tạo một module tên `com.example.catalog` với lớp `Catalog`. Ví dụ dùng cú pháp Java module kể từ Java 9, và lệnh `javadoc` hiện đại. Các từ khóa được chọn sao cho bạn có thể xác minh sự hiện diện của chúng trong dữ liệu Javadoc sinh ra.

### 5.1. Cấu trúc thư mục

```text
catalog-docs-demo/
└── src/
    └── com.example.catalog/
        ├── module-info.java
        └── com/
            └── example/
                └── catalog/
                    └── Catalog.java
```

Lệnh dưới đây giả sử đang đứng trong thư mục `catalog-docs-demo`. Chú ý **thư mục module có tên trùng với tên module**, còn thư mục package nằm bên trong module.

### 5.2. Tệp `src/com.example.catalog/module-info.java`

```java
/**
 * API ví dụ về tra cứu danh mục.
 * <p>Hỗ trợ {@index "order lookup" Tra cứu theo đơn}.
 * Từ viết tắt {@index SKU Stock Keeping Unit} có thể được tìm trong Javadoc.
 */
module com.example.catalog {
    exports com.example.catalog;
}
```

- Javadoc nằm **ngay trước** khai báo `module`, vì vậy nội dung sẽ thuộc trang module summary.
- `{@index "order lookup" Tra cứu theo đơn}` thêm thuật ngữ hai từ. Khi click kết quả, người đọc về vị trí này ở trang module.
- `{@index SKU Stock Keeping Unit}` thêm từ khóa một token cùng mô tả.
- `exports com.example.catalog;` cho phép API công khai của package được tiêu thụ từ module khác; đồng thời giúp ví dụ là một Java module hợp lệ.

### 5.3. Tệp `src/com.example.catalog/com/example/catalog/Catalog.java`

```java
package com.example.catalog;

/**
 * Lớp tra cứu mã sản phẩm.
 * <p>Tra cứu bằng {@index "product id" Mã sản phẩm}.
 */
public final class Catalog {
    private Catalog() { }

    /**
     * Tra cứu mã SKU.
     * <p>Sử dụng {@index "stock keeping unit" Thuật ngữ quản lý kho}.
     * @param sku mã hàng nhập vào
     * @return tên minh họa
     */
    public static String lookup(String sku) {
        return "item:" + sku;
    }
}
```

- Search có thể tìm **`Catalog`** như một type và **`lookup(String)`** như member ngay cả khi ta không viết thêm `{@index}` cho hai identifier này.
- `"product id"` chỉ đến phần mô tả class; `"stock keeping unit"` chỉ đến phần mô tả phương thức.
- `@param` và `@return` là các block tag chuẩn của method, giúp thông tin API đầy đủ. `{@index}` vẫn là inline tag trong phần mô tả.
- Phần thân `lookup` chỉ tạo một chuỗi minh họa; mục tiêu ví dụ là **tài liệu và chỉ mục**, không phải triển khai hệ thống danh mục thực.

### 5.4. Sinh HTML bằng Javadoc

Trên Windows PowerShell, macOS hoặc Linux, có thể chạy nguyên dòng:

```bash
javadoc -quiet -Xdoclint:all -encoding UTF-8 -charset UTF-8 -d docs --module-source-path src --module com.example.catalog
```

Giải thích:

- `--module-source-path src` khai báo nơi chứa các module ở dạng source.
- `--module com.example.catalog` chọn đúng module cần đưa vào tài liệu; module không nằm trong tập đầu vào sẽ không tự xuất hiện trong kết quả.
- `-d docs` đặt HTML và tài nguyên tìm kiếm vào thư mục `docs`.
- `-encoding UTF-8` cho parser đọc mã nguồn UTF-8; `-charset UTF-8` quy định charset HTML đầu ra.
- `-Xdoclint:all` kiểm tra tài liệu nghiêm ngặt hơn, phát hiện nhiều lỗi cú pháp HTML/Javadoc và tham chiếu. `-quiet` giảm log thông thường, không có nghĩa đã tắt lỗi.

**Kết quả kiểm thử:** Lệnh trên chạy thành công với JDK 24 và không báo lỗi cho hai source file này. `javadoc` là công cụ **tạo tài liệu**, không chạy `main()`; do đó không có một stdout bài toán Java cố định. Dấu hiệu thành công là exit code 0 và các trang/tài nguyên được tạo.

Bạn cũng có thể biên dịch module độc lập với việc sinh tài liệu:

```bash
javac -encoding UTF-8 -d out --module-source-path src --module com.example.catalog
```

Lệnh `javac` kiểm tra mã Java. Lệnh `javadoc` kiểm tra và tạo HTML/Javadoc. Hai bước phục vụ những mục tiêu khác nhau; tài liệu có lỗi có thể cần sửa ngay cả khi Java source biên dịch được.

### 5.5. Những tệp đầu ra cần tìm

Với Standard Doclet trên JDK 24, các tệp quan trọng gồm:

```text
docs/
├── index.html
├── index-all.html
├── search-tags.html
├── tag-search-index.js
└── com.example.catalog/
    ├── module-summary.html
    └── com/
        └── example/
            └── catalog/
                └── Catalog.html
```

Đây là **các đường dẫn đã quan sát ở JDK 24**. Những tên file JavaScript nội bộ và cách tổ chức tài nguyên có thể thay đổi giữa các phiên bản JDK; đừng xây công cụ phụ thuộc cứng vào cấu trúc file JS được sinh ra. Nên xác minh chức năng bằng UI/đường dẫn HTML public mà người dùng thực sự truy cập.

Các điểm kiểm tra đáng tin:

- Trang module `com.example.catalog/module-summary.html` hiển thị `order lookup` và `SKU` tại vị trí mô tả.
- Trang class `com.example.catalog/com/example/catalog/Catalog.html` hiển thị `product id` và `stock keeping unit`, cùng danh sách member.
- `search-tags.html` cho phép duyệt các search tags riêng.
- `index-all.html` là chỉ mục chữ cái HTML; trên bản dựng hiện đại, có mục cho những thuật ngữ được `{@index}` khai báo.
- Dữ liệu tìm kiếm trong bản dựng kiểm tra ghi nhận chính xác **bốn nhãn**: `order lookup`, `SKU`, `product id`, `stock keeping unit`, với liên kết đến trang module/class/method tương ứng.

**Không chỉnh tay** các JS/HTML đã tạo để thêm từ khóa; lần `javadoc` kế tiếp sẽ sinh lại chúng. Hãy sửa comment Javadoc trong mã nguồn rồi chạy lại công cụ.

## 6. Thực hành hộp Search

Sau khi mở `docs/index.html` bằng một trình duyệt có JavaScript hoạt động, thực hiện theo thứ tự sau:

| Nhập trong Search | Bạn muốn tìm | Điều cần xác minh |
| --- | --- | --- |
| `com.example.catalog` | Module hoặc package của ví dụ | Kết quả tương ứng với module/package và đường dẫn của chúng |
| `Catalog` | Lớp `Catalog` | Mở trang class |
| `lookup` | Phương thức `lookup(String)` | Đi đến member trên trang class |
| `order lookup` | Search tag trong module documentation | Mở trang module tại đoạn giải thích thuật ngữ |
| `SKU` | Search tag trong module documentation | Mở mục giải thích SKU của module |
| `product id` | Search tag trong class documentation | Mở đoạn `product id` của class |
| `stock keeping unit` | Search tag trong method documentation | Đi đến đoạn giải thích thuộc member `lookup` |

Giao diện có thể phân loại hoặc xếp hạng kết quả khác nhau theo JDK và chuỗi đang nhập. Điều kiểm thử cần khẳng định là **mục được tìm thấy và liên kết trỏ đúng nội dung**; không chốt rằng mục đó luôn là gợi ý thứ nhất hay có màu sắc/vị trí chính xác.

### 6.1. Hành vi nhập liệu và khớp kết quả

Đặc tả tìm kiếm hiện đại hỗ trợ một số hành vi tiện dụng:

1. **Khớp tên hoặc phần đầu tên:** Khi nhập một tiền tố hợp lệ, Javadoc có thể trả type/member có tên tương ứng. Đừng kỳ vọng mọi đoạn con nằm giữa một từ đều khớp như full-text search.
2. **CamelCase:** Với identifier Java như `InputStream`, có thể tìm bằng dạng viết tắt các ranh giới chữ hoa, ví dụ `InpStr`. Tính năng này hữu ích với tên API dài.
3. **Dấu phân cấp:** Dấu `.` và `/` giúp truy vấn theo cấu trúc type/package/module khi cần phân biệt tên trùng.
4. **Nhiều từ:** Search xét chuỗi truy vấn gồm nhiều từ theo quy tắc thứ tự và ranh giới từ. Ví dụ `order lookup` khớp nhãn search tag đã khai báo đúng cụm đó.
5. **Chữ hoa/chữ thường:** Tìm kiếm có cơ chế ưu tiên cho cách viết khớp chính xác hơn; việc xếp hạng không nên được dùng như tiêu chí đúng/sai duy nhất.

Nếu một thuật ngữ không tìm thấy, hãy kiểm tra trước tiên xem nó có thực sự được khai báo bằng `{@index}` hay chỉ xuất hiện trong văn xuôi. Sau đó kiểm tra module/package chứa nó đã được đưa vào build hay chưa, và thử duyệt `search-tags.html`.

### 6.2. Search không thay thế bộ lọc nội dung tùy ý

Search không mặc định tìm mọi từ trong mô tả, comment mã nguồn, bài README bên ngoài hay các file không thuộc bộ Javadoc được sinh. Nếu tài liệu cần tìm “mã đơn hàng” nhưng bạn chỉ có khai báo Java tên `OrderRepository` và không gắn thuật ngữ tương ứng, người đọc có thể không thấy kết quả trực tiếp khi gõ cụm nghiệp vụ đó.

Dùng `{@index}` để tạo **entrypoint tìm kiếm có chủ đích**, ví dụ:

```java
/**
 * Tạo báo cáo tồn kho từ dữ liệu chuẩn.
 * <p>Quy trình {@index "stock report" Báo cáo tồn kho}
 * hỗ trợ đối chiếu trước khi xuất hàng.
 */
public final class InventoryReport {
    // Minh họa tài liệu cho thuật ngữ nghiệp vụ.
}
```

Đây là **đoạn minh họa rời**, không phải một file/module hoàn chỉnh. Nếu “stock report” là tên người dùng thực sự nhập, index tag giúp họ đến đúng nơi giải thích thay vì phải biết trước tên `InventoryReport`.

## 7. Quy tắc thiết kế search tags cho API mô-đun

Thêm càng nhiều `{@index}` không nhất thiết làm Search tốt hơn. Một chỉ mục hữu ích phải có từ khóa rõ nghĩa, vị trí giải thích đúng và ít trùng lặp.

### 7.1. Chọn từ khóa

- **Từ vựng thực sự của người đọc:** “order lookup”, “product id”, “SKU”, “stock keeping unit”. Không buộc người đọc đoán tên class.
- **Cụm từ đủ đặc trưng:** Ưu tiên `"order lookup"` hơn từ `lookup` chung chung nếu nhiều API đều có lookup.
- **Viết tắt có chú giải:** `{@index SKU Stock Keeping Unit}` giúp người đọc hiểu một nhãn ngắn.
- **Nhất quán với glossary:** Chọn một cách gọi chính cho cùng khái niệm; thêm alias khi người dùng có hai cách gọi phổ biến và cả hai đều có giá trị tra cứu.
- **Không nhồi từ:** Mỗi term nên dẫn đến nội dung có giải thích thực sự, không lặp cùng từ khóa ở mọi class chỉ để tăng kết quả.

### 7.2. Vị trí và quyền hiển thị

| Nội dung giải thích | Nên đặt ở đâu? | Vì sao |
| --- | --- | --- |
| Ý nghĩa và phạm vi khái niệm chung | `module-info.java` | Người dùng tìm được thuật ngữ ngay từ tổng quan module |
| Khái niệm đại diện bởi một kiểu | Javadoc của class/interface | Có bối cảnh type và liên kết member |
| Hành vi cụ thể, tình huống hoặc thuật toán của method | Javadoc ngay trên method | Link dẫn đến chỗ áp dụng cụ thể |
| Quy ước chung cho một package | `package-info.java` | Vừa đủ chi tiết, tránh dồn mọi thứ vào module |

Nếu bạn ghi `{@index}` trong một khai báo không được đưa vào tài liệu do scope/visibility/build chọn, đừng kỳ vọng mục đó xuất hiện trong chỉ mục đã xuất. Ví dụ, module không được đưa vào `--module` hoặc API bị loại khỏi tài liệu sẽ không tự có search entry cho đoạn comment bị bỏ qua.

### 7.3. Từ khóa nhiều ngôn ngữ

Với bộ tài liệu tiếng Việt, có thể đặt thuật ngữ tiếng Việt trong `{@index "tra cứu mã hàng" ...}` khi đó đúng là cách người đọc sẽ tìm. Nên kiểm tra thực tế khi nhập dấu tiếng Việt vì hành vi chuẩn hóa dấu, ký tự Unicode và phân tích truy vấn phụ thuộc đặc tả/cài đặt. Nếu tài liệu vận hành đồng thời tiếng Việt và tiếng Anh, ghi rõ từ khóa chuẩn và alias cần thiết, tránh chỉ dịch tên ngầm mà không đánh dấu chúng.

Không tạo “alias” bằng cách thay đổi tên class hoặc package chỉ để Search khớp. Dùng `{@index}` là cách thêm từ khóa mà **không phải thay đổi API nhị phân**.

## 8. Kiểm tra chất lượng trước khi xuất bản

Kiểm thử Javadoc có hai lớp khác nhau.

**Lớp 1 — build và kết quả tĩnh:**

- Chạy `javadoc` với đúng module và kiểm tra exit code; xử lý warning/error của Javadoc.
- Dùng `-Xdoclint:all` hoặc chính sách doclint phù hợp để phát hiện vấn đề cú pháp và tham chiếu.
- Xác nhận tồn tại module summary, class page, `Index` và `Search Tags`.
- Kiểm tra bốn term của bài thực sự có trong nội dung/chỉ mục sinh ra; dấu tiếng Việt không bị lỗi encoding.
- Click liên kết từ trang chỉ mục để xác nhận về đúng **đoạn đặt `{@index}`**.

**Lớp 2 — kiểm tra trên trình duyệt thật:**

- Mở tài liệu với JavaScript đã bật.
- Gõ tên module, class, member, và ít nhất hai custom search tags.
- Kiểm tra kết quả điều hướng đúng, kể cả khi có overload hoặc nhiều module có tên tương tự.
- Thử điều hướng bằng bàn phím và khả năng đọc trên màn hình cỡ nhỏ nếu là yêu cầu sản phẩm.
- Thử một lần khi JavaScript bị tắt để bảo đảm chỉ mục HTML vẫn là cách duyệt hỗ trợ.

Với bộ test tự động, có thể kiểm tra sự có mặt của từ khóa trong HTML/tài nguyên sinh ra, nhưng **đừng dùng đường dẫn `tag-search-index.js` và khóa JSON nội bộ như một API ổn định lâu dài**. Kiểm tra URL và trải nghiệm người dùng sẽ bền hơn qua các lần nâng JDK.

### 8.1. Vì sao phải chạy `javadoc` trong CI?

Source Java vẫn có thể biên dịch dù Javadoc chứa thuật ngữ sai, link hỏng, tag chưa đóng hoặc một package/module bị bỏ sót khỏi tập tài liệu. Biên dịch bằng `javac` giúp kiểm tra mã, còn tạo tài liệu trong CI giúp xác minh hành vi của **doclet** và scope tài liệu thực sự xuất bản.

Ví dụ yêu cầu nghiệm thu thực tế:

| Ca kiểm tra | Kết quả mong đợi |
| --- | --- |
| Có `{@index "order lookup"}` ở module | Search Tags có nhãn `order lookup` dẫn tới trang module |
| Có `{@index SKU ...}` ở module | Search Tags có nhãn `SKU` và mô tả liên quan |
| Có `{@index "product id" ...}` ở class | Entry trỏ vào trang class `Catalog` |
| Có `{@index "stock keeping unit" ...}` ở method | Entry trỏ tới đoạn method `lookup(String)` |
| Gõ `Catalog` | Tìm được type, không cần index tag riêng cho tên class |
| Gõ `lookup` | Tìm được phương thức public trong tài liệu |
| Bỏ module khỏi input build | Module và những tag chỉ có trong module bị loại không xuất hiện |
| Dùng browser với JS tắt | Hộp Search không hoạt động, nhưng Index HTML vẫn giúp duyệt |
| Thay đổi JDK, rebuild | Các mục/đường dẫn người dùng cần vẫn hoạt động; không so sánh cố định cấu trúc JS |

## 9. Các lỗi phổ biến

| Vấn đề | Nguyên nhân | Hướng xử lý |
| --- | --- | --- |
| Gõ thuật ngữ có trong đoạn mô tả nhưng Search không ra | Text chưa tạo **search tag** và không phải tên API được lập chỉ mục | Thêm `{@index "thuật ngữ"}` gần vị trí giải thích |
| Dùng `@index` đứng đầu dòng như block tag | Cú pháp không đúng với inline tag `{@index}` | Dùng đầy đủ cặp `{...}` nằm trong Javadoc |
| Viết `{@index order lookup}` với ý định index cả hai từ | Không trích dẫn phrase, nên chỉ `order` là từ khóa, phần sau có thể thành description | Dùng `{@index "order lookup"}` |
| Mô tả quá chung chung | Kết quả Search khó phân biệt các term | Viết mô tả ngắn có ý nghĩa, đặt tag đúng ngữ cảnh |
| Có tag trong `//` hoặc `/* ... */` thường | Standard Doclet không xử lý nó như tài liệu API | Viết trong `/** ... */` gắn với khai báo |
| Tag trong code của module khác không thấy trong HTML | Module/type không được đưa vào tập build Javadoc | Kiểm tra `--module`, source path và phạm vi API |
| `{@index}` sinh link đến trang “không đúng” | Tag đặt ở vị trí quá rộng hoặc thiếu ngữ cảnh | Chuyển tag đến đoạn mô tả chính xác hơn |
| Tìm kiếm trống sau triển khai trang web | JavaScript hoặc asset của Search thiếu/bị chặn; đường dẫn tài nguyên lỗi | Xuất bản toàn bộ thư mục `docs`, kiểm tra tab Console/Network và cấu hình CSP |
| Search không hoạt động khi JS bị tắt | Tìm kiếm tương tác phụ thuộc JavaScript | Cho người đọc dùng chỉ mục A–Z HTML |
| Chỉ kiểm tra file `tag-search-index.js` của một bản JDK | Đó là artifact implementation, không phải giao diện API ổn định | Kiểm tra chức năng và đường dẫn HTML từ bản dựng thực tế |
| Các mục bị trùng và gây nhiễu | Lặp tag ở nhiều chỗ không có nội dung mới | Chọn vị trí chuẩn và quy tắc đặt term |
| Thuật ngữ tiếng Việt bị sai dấu | Source/output charset hoặc cơ chế kiểm thử chưa nhất quán | Chốt UTF-8, chạy với `-encoding`/`-charset` và kiểm tra trình duyệt |

**Lưu ý về `-noindex`:** tùy chọn của Standard Doclet này yêu cầu không sinh chỉ mục. Không dùng nó cho quy trình xuất bản cần Index và trải nghiệm tra cứu mặc định; nếu tài liệu thiếu trang Index, hãy kiểm tra tùy chọn build trước khi tìm lỗi ở `{@index}`.

## 10. Bài tập thực hành

1. Tạo đúng cấu trúc module và hai source file của mục 5, chạy `javadoc`.
2. Mở trang module, tìm `order lookup` và `SKU` bằng hộp Search; kiểm tra mỗi kết quả dẫn đến đoạn giải thích chính xác.
3. Mở trang class, nhập `product id` và `stock keeping unit`; kiểm tra mốc liên kết và vị trí method.
4. Thử nhập `Catalog` và `lookup`, so sánh kết quả tên API với kết quả custom search tags.
5. Thêm một thuật ngữ nghiệp vụ khác bằng `{@index "catalog export" Xuất dữ liệu danh mục}` ở đoạn phù hợp, rebuild và kiểm tra chỉ mục.
6. Xóa thử tag mới trong source rồi rebuild từ output sạch; xác minh mục mới không còn được lập chỉ mục, trong khi tên class/method vẫn tra được.
7. Chạy test trong trình duyệt có JavaScript rồi tắt JavaScript; so sánh Search tương tác với A–Z Index.

Không sửa trực tiếp HTML hay JS sinh ra để hoàn thành bài tập: đầu vào bền vững là **Javadoc comment trong source**.

## 11. Tự kiểm tra

**Câu 1.** Người dùng tìm `"order lookup"` nhưng source chỉ có method `lookup(String)`, chưa có `{@index}`. Vì sao không bảo đảm kết quả cho cả cụm từ?

**Câu 2.** Viết thẻ lập chỉ mục chính xác cho cụm hai từ `product id`, có mô tả “Mã sản phẩm”.

**Câu 3.** Khác nhau giữa `{@index "product id"}` và `{@link Catalog}` là gì?

**Câu 4.** Nên đặt từ khóa dùng chung toàn module trong `module-info.java` hay phân tán ở mọi method?

**Câu 5.** Khi Javadoc tìm thấy đúng thuật ngữ nhưng link đến đoạn không liên quan, nên sửa file JavaScript đã sinh hay sửa vị trí tag trong source?

**Câu 6.** Nếu người dùng tắt JavaScript thì còn cách nào để duyệt chỉ mục?

**Đáp án gợi ý:** (1) Search dùng chỉ mục API/search tags thay vì quét toàn văn; (2) `{@index "product id" Mã sản phẩm}`; (3) `{@index}` thêm mục tìm và mốc còn `{@link}` liên kết khai báo Java; (4) đặt ở module khi nội dung giải thích là tổng quan module; (5) sửa tag trong source rồi rebuild; (6) dùng A–Z Index HTML được tạo nếu build không vô hiệu hóa index.

## 12. Tài liệu tham khảo chính thức

- [Oracle JDK 24 — Documentation Comment Specification: inline tag `{@index}`](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/doc-comment-spec.html)
- [Oracle JDK 24 — Javadoc Search Specification](https://docs.oracle.com/en/java/javase/24/docs/specs/javadoc/javadoc-search-spec.html)
- [Oracle JDK 24 — Javadoc Command](https://docs.oracle.com/en/java/javase/24/docs/specs/man/javadoc.html)
- [Oracle JDK 24 — Javadoc API Help](https://docs.oracle.com/en/java/javase/24/docs/api/help-doc.html)

Một tài liệu mô-đun dễ tra cứu cần hai lớp bổ sung cho nhau: **chỉ mục tự động theo tên khai báo Java** và **các từ khóa nghiệp vụ có chủ đích bằng `{@index}`**. Khi xây dựng tài liệu bằng Javadoc hiện đại và kiểm tra cả trang kết quả lẫn liên kết đích, người đọc có thể tìm được thông tin mà không cần biết trước cấu trúc package hoặc tên class.