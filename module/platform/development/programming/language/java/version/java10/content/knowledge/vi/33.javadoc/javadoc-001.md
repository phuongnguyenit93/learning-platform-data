# Thẻ {@summary ...} để khai báo phần tóm tắt trong Javadoc (Java 10+)

## 1. Vấn đề: câu nào thực sự được hiện trong bảng API Summary?

Khi mở trang Javadoc của một thư viện Java, người đọc thường nhìn **Class Summary, Method Summary, Field Summary hoặc Index** trước khi kéo xuống phần mô tả chi tiết. Mỗi hàng cần một câu ngắn mô tả trách nhiệm chính của API, giúp người dùng quyết định sẽ mở chi tiết của phần tử nào.

Theo mặc định, **standard doclet** của công cụ `javadoc` trích **câu đầu tiên của phần mô tả chính** trong Javadoc comment làm summary. Nhưng câu đầu tiên không phải lúc nào cũng được phân tích chính xác: tên miền `api.example.test`, phiên bản `v1.2.3`, ký hiệu viết tắt, dấu câu hoặc cách diễn đạt phức tạp có thể khiến người soạn muốn chọn một đoạn tóm tắt minh bạch thay vì để công cụ phỏng đoán.

**Từ JDK 10**, thẻ inline **`{@summary ...}`** cho phép **khai báo trực tiếp phần văn bản dùng làm API summary**:

```java
/**
 * {@summary Chuẩn hóa mã API trước khi lưu vào bộ nhớ.}
 * Phương thức này loại khoảng trắng hai đầu rồi viết hoa ổn định.
 *
 * @param code mã cần chuẩn hóa
 * @return mã đã được chuẩn hóa
 */
public static String normalize(String code) {
    return code.trim().toUpperCase(java.util.Locale.ROOT);
}
```

Trong trường hợp này, nội dung tóm tắt được chọn là:

```text
Chuẩn hóa mã API trước khi lưu vào bộ nhớ.
```

Câu “Phương thức này loại khoảng trắng ...” là **nội dung giải thích tiếp theo**, vẫn được đưa vào phần mô tả đầy đủ trong trang HTML, nhưng **không bị kéo vào phần summary**.

**Điểm mấu chốt:** `{@summary ...}` là **thẻ nội tuyến của Javadoc**, không phải một Java annotation, Java keyword, runtime API hoặc `@summary` block tag. Nó được **công cụ tạo tài liệu** xử lý, không làm thay đổi thuật toán đang chạy của phương thức Java.

### Mục tiêu học tập

Sau bài này, bạn có thể:

1. Nêu lý do Java 10 bổ sung thẻ `{@summary ...}` và giải thích vấn đề first-sentence inference.
2. Viết đúng cú pháp và **đặt thẻ ở đầu main description**.
3. Phân biệt nội dung của thẻ với phần mô tả chi tiết bên dưới.
4. Hiểu summary được đưa vào những khu vực nào trong HTML do standard doclet sinh ra.
5. So sánh **không có thẻ** với **có thẻ** và **thẻ đặt sai vị trí**.
6. Dùng `javadoc -Xdoclint:all` để tìm lỗi vị trí, reference và cú pháp.
7. Biên dịch chương trình Java 17+ rồi sinh và kiểm tra Javadoc HTML.
8. Biết cú pháp Javadoc truyền thống `/** ... */` và chú thích Markdown `///` trên JDK 23+.
9. Viết summary tốt cho class, interface, method, field và các phần tử tài liệu phù hợp.
10. Tránh hiểu nhầm với `@return`, `@since`, `@deprecated` hoặc mô tả trong runtime.
11. Tự rà soát phần tóm tắt trước khi phát hành tài liệu API.
12. Chỉ áp dụng những kiến thức **vẫn còn hiệu lực trên JDK mới**, không dựa vào mẹo hoặc định dạng Javadoc đã lỗi thời.

## 2. Bối cảnh Java 10: vì sao cần một tag riêng?

Trong **Oracle JDK 10 Release Notes**, mục **“Comment Tag for Summary of an API Description”** ghi nhận thay đổi **JDK-8173425**.

Trước khi có thẻ summary tường minh, standard doclet xác định đoạn tóm tắt bằng **heuristic chọn câu đầu tiên**. Công cụ có thể dùng thuật toán đơn giản dựa trên dấu chấm và khoảng trắng, hoặc sử dụng cơ chế phân tích ranh giới câu như `java.text.BreakIterator` tùy chế độ. Cách này không phải lúc nào cũng trùng với chủ ý của tác giả Javadoc.

Ví dụ:

```java
/**
 * Hỗ trợ API v1.2.3. Cung cấp các phép kiểm tra dữ liệu bổ sung.
 */
public final class ApiVersionGuide { }
```

Người viết thường muốn mô tả đầy đủ API, nhưng hệ thống lấy summary dựa trên các quy tắc dấu câu có thể khó dự đoán với những chuỗi chứa dấu chấm hoặc văn bản đa ngôn ngữ.

Từ Java 10, có thể thể hiện **ranh giới summary** một cách rõ ràng:

```java
/**
 * {@summary Hỗ trợ API v1.2.3 cùng các phép kiểm tra dữ liệu.}
 * Những ví dụ, ràng buộc và cách dùng chi tiết được trình bày sau đây.
 */
public final class ApiVersionGuide { }
```

Dù văn bản summary có dấu chấm bên trong `v1.2.3`, **toàn bộ nội dung nằm trong cặp dấu ngoặc của tag** được dùng làm summary.

### Mốc phiên bản

| Phiên bản | Điểm liên quan | Tình trạng sử dụng |
| --- | --- | --- |
| **JDK 10** | Bổ sung thẻ inline `{@summary ...}`, JDK-8173425 | **Vẫn còn hỗ trợ trong Javadoc hiện đại** |
| **JDK 17 / 21** | Dùng thẻ trong Javadoc comment truyền thống `/** ... */` | Phù hợp với source Java 17+ |
| **JDK 23+** | Thêm **Markdown documentation comments** `///` theo JEP 467 | Có thể dùng `{@summary ...}` trong dạng Markdown |
| **JDK 25 / 26** | Đặc tả standard doclet vẫn ghi rõ nghĩa của thẻ summary | Cần đọc đúng đặc tả của toolchain đang dùng |

**Không phải vì tính năng xuất hiện ở Java 10 mà phải biên dịch ứng dụng bằng JDK 10 cũ.** Có thể dùng JDK 17+ hoặc JDK hiện hành để biên dịch và sinh tài liệu với thẻ này.

## 3. Cú pháp chính xác và vị trí đặt thẻ

Cú pháp:

```text
{@summary nội dung tóm tắt}
```

Trong một comment Javadoc truyền thống, đặt thẻ **ở đầu phần mô tả chính (main description)**:

```java
/**
 * {@summary Đọc giá trị cấu hình theo tên khóa.}
 * Giá trị được lấy từ nguồn cấu hình đã đăng ký.
 * Nếu không có khóa tương ứng, phương thức trả về null.
 *
 * @param key tên khóa
 * @return giá trị tìm được hoặc null
 */
public String find(String key) {
    return settings.get(key);
}
```

Chú ý ba thành phần:

- `/** ... */`: comment tài liệu, khác comment thường `/* ... */` hoặc `// ...`.
- `{@summary ...}`: **inline tag** có ngoặc nhọn. Trong ví dụ, nó xuất hiện **trước mọi câu mô tả khác**.
- `@param`, `@return`: **block tags** đặt sau phần mô tả chính; không thay vai trò summary.

### Main description là vùng nào?

Theo đặc tả Javadoc, main description bắt đầu từ phần nội dung của comment và kết thúc trước **block tag đầu tiên**. Khi đã sang phần `@param`, `@return`, `@throws`, `@see`, các dòng sau thuộc phần block tags, không phải tiếp tục phần mô tả chính thông thường.

```text
/**
 * {@summary Mở tài nguyên theo ID.}   <-- đầu main description
 * Mô tả cơ chế đọc, lỗi, giới hạn.    <-- phần main description tiếp theo
 *
 * @param id mã tài nguyên             <-- bắt đầu block tags
 * @return tài nguyên                  <-- block tag
 */
```

**Quy tắc quan trọng nhất từ đặc tả:** thẻ `{@summary ...}` **chỉ có ý nghĩa chọn summary khi được dùng ở đầu main description**. Ở vị trí khác, Javadoc vẫn có thể render nội dung của tag nhưng **không dùng tag đó để định nghĩa summary**.

### Chữ hoa, dấu cách và dấu câu

- Viết đúng `summary` chữ thường. Tên tag **phân biệt hoa/thường**.
- Chừa khoảng trắng giữa `summary` và nội dung.
- Tóm tắt nên ngắn gọn, rõ nghĩa, thông thường kết thúc bằng dấu chấm.
- Có thể có dấu chấm trong version/hostname; tag explicit tránh việc công cụ tự đoán điểm kết thúc.
- Không viết nhiều câu dài vào tag chỉ vì nó không bị giới hạn bởi heuristic chọn câu đầu.
- Không đặt một câu mở đầu đứng trước tag rồi hy vọng tag sẽ “thay” câu đầu đó.

## 4. Vì sao tag khác với cách tự lấy câu đầu tiên?

Khi **không có** `{@summary}`, standard doclet thường dùng câu đầu main description:

```java
/**
 * Kiểm tra xem cấu hình có được cung cấp hay không.
 * Đây là phần giải thích điều kiện null và chuỗi rỗng.
 */
public static boolean isConfigured(String value) {
    return value != null && !value.isBlank();
}
```

Summary mặc định:

```text
Kiểm tra xem cấu hình có được cung cấp hay không.
```

Với thẻ explicit:

```java
/**
 * {@summary Kiểm tra cấu hình đầu vào.}
 * Cấu hình được coi là có mặt khi khác null và có ký tự không trắng.
 */
public static boolean isConfigured(String value) {
    return value != null && !value.isBlank();
}
```

Summary explicit:

```text
Kiểm tra cấu hình đầu vào.
```

**Lợi ích chính** là người đọc và người bảo trì có thể thấy ngay đâu là câu tóm tắt có chủ ý, dù phần giải thích bên dưới dài hoặc có những dấu câu khiến heuristic khó suy đoán.

| Tình huống | Quy tắc chọn summary |
| --- | --- |
| Không có thẻ `{@summary}` | Standard doclet suy từ câu đầu main description |
| Có thẻ ở đầu main description | Dùng nội dung của thẻ làm summary |
| Có thẻ ở giữa/sau câu mở đầu | Không dùng thẻ đó làm summary; có thể có cảnh báo |
| Comment chỉ gồm block tags và không có main description | Không có nội dung main description thích hợp để tạo một câu tóm tắt rõ nghĩa |
| Có nội dung sau thẻ đúng vị trí | Nội dung đó vẫn được render ở phần mô tả đầy đủ |

**Không cần dùng thẻ ở mọi API.** Nếu câu đầu đã là summary ngắn gọn, không mơ hồ và công cụ cho output đúng, để mặc định là hợp lệ. Dùng `{@summary}` khi cần kiểm soát rõ ràng hoặc dự án có style guide yêu cầu.

## 5. Thẻ summary ảnh hưởng tới phần nào của tài liệu HTML?

Trong HTML được tạo bởi **standard doclet**, một summary được dùng ở các khu vực tóm lược và chỉ mục, chẳng hạn:

- **Class/Interface Summary** khi listing các types.
- **Method Summary** cho các phương thức.
- **Field Summary** cho fields.
- **Constructor Summary** cho constructors.
- **Index** hoặc những danh sách liên kết do doclet tạo.
- Các vùng tóm tắt khác tùy declaration và cấu trúc tài liệu.

Trong phần chi tiết của phần tử, toàn bộ nội dung main description vẫn được render: summary tag **không cắt bỏ mô tả sau đó**.

### Cùng một mô tả được dùng hai cách

Ví dụ:

```java
/**
 * {@summary Tạo một mã an toàn cho đường dẫn dịch vụ.}
 * Thao tác dùng quy tắc chuẩn hóa được mô tả tại đây và không gọi mạng.
 *
 * @param raw mã chưa chuẩn hóa
 * @return mã đã chuẩn hóa
 */
public String normalize(String raw) {
    return raw.trim();
}
```

**Method Summary** thường chỉ lấy:

```text
Tạo một mã an toàn cho đường dẫn dịch vụ.
```

**Method Detail** hiển thị phần mô tả lớn hơn:

```text
Tạo một mã an toàn cho đường dẫn dịch vụ.
Thao tác dùng quy tắc chuẩn hóa được mô tả tại đây và không gọi mạng.
Parameters: raw ...
Returns: ...
```

Đây là mô tả về nội dung hiển thị, không phải HTML copy nguyên bản; các class/CSS/structure thực tế có thể thay theo phiên bản JDK.

### Tag không làm gì ở runtime

Thẻ `{@summary ...}` không:

- Thay kiểu dữ liệu hoặc contract của phương thức.
- Tạo annotation/metadata runtime để reflection đọc.
- Thay output của `main()`.
- Ảnh hưởng hiệu năng JVM hoặc Garbage Collector.
- Tạo validate logic cho `@param` / `@return`.
- Tự động làm unit tests hay API tests pass.

Thẻ chỉ tác động tới **nội dung tài liệu được công cụ hỗ trợ sinh ra**.

## 6. Java 17+ demo đầy đủ: SummaryTagDemo.java

Để tự kiểm chứng, viết một class công khai có hai methods: một phương thức dùng `{@summary}`, một phương thức để **first-sentence default**.

Tạo file **`SummaryTagDemo.java`**:

```java
import java.util.Locale;

/**
 * {@summary Tiện ích chuẩn hóa mã API cho miền api.example.test.}
 * Lớp này minh họa việc Javadoc lấy toàn bộ nội dung của summary tag
 * dù bên trong có các dấu chấm ở tên miền.
 *
 * @since 10
 */
public final class SummaryTagDemo {
    private SummaryTagDemo() { }

    /**
     * {@summary Chuyển mã nhập thành chữ hoa sau khi loại khoảng trắng ở hai đầu.}
     * Chi tiết: sử dụng locale ổn định và không sửa đối tượng chuỗi đầu vào.
     *
     * @param value mã cần xử lý, không được null
     * @return mã đã chuẩn hóa
     * @throws IllegalArgumentException nếu giá trị null
     */
    public static String normalize(String value) {
        if (value == null) {
            throw new IllegalArgumentException("value must not be null");
        }
        return value.trim().toUpperCase(Locale.ROOT);
    }

    /**
     * Kiểm tra cấu hình có được cung cấp hay không. Chi tiết bổ sung
     * không thuộc câu tóm tắt mặc định.
     *
     * @param value giá trị kiểm tra
     * @return true nếu khác null và không trống
     */
    public static boolean isConfigured(String value) {
        return value != null && !value.isBlank();
    }

    /**
     * Chạy ví dụ để kiểm tra hành vi Java độc lập với Javadoc.
     *
     * @param args tham số dòng lệnh không được dùng
     */
    public static void main(String[] args) {
        System.out.println("normalized=" + normalize("  java  "));
        System.out.println("configured=" + isConfigured(" ready "));
        System.out.println("emptyConfigured=" + isConfigured("  "));
    }
}
```

Class có private constructor vì chỉ cung cấp static utility methods. `Locale.ROOT` giúp phép viết hoa ổn định hơn so với lấy default locale của người dùng.

**Lưu ý `@since 10` trong demo** là ví dụ metadata về **phiên bản mà API của một thư viện giả định được giới thiệu**, không phải cách kích hoạt summary tag. Với code production, phải ghi số phiên bản public API thực tế, không chép nguyên `@since 10` nếu thư viện không dùng version đó.

### Biên dịch và chạy code

```bash
javac --release 17 -encoding UTF-8 SummaryTagDemo.java
java SummaryTagDemo
```

**Stdout chính xác đã được biên dịch/chạy kiểm chứng:**

```text
normalized=JAVA
configured=true
emptyConfigured=false
```

Kết quả trên đến từ logic Java thông thường. Nó **không phụ thuộc việc có chạy `javadoc` hay không**.

### Tạo tài liệu HTML

```bash
javadoc -quiet -Xdoclint:all \
  -encoding UTF-8 -charset UTF-8 \
  -d docs SummaryTagDemo.java
```

Đây là lệnh cho **POSIX shell**; dấu `\` dùng để nối dòng. Với PowerShell/Windows, viết lệnh một dòng:

```powershell
javadoc -quiet -Xdoclint:all -encoding UTF-8 -charset UTF-8 -d docs SummaryTagDemo.java
```

Lệnh đã được chạy thành công bằng **Zulu OpenJDK 24.0.2**, sử dụng source file trên và `javadoc -Xdoclint:all`, không có warning/error từ nội dung Javadoc trong bản demo.

File quan trọng được sinh:

```text
docs/SummaryTagDemo.html
docs/index-all.html
```

Tùy JDK, doclet còn tạo nhiều trang, stylesheet, script và search data khác. Không cần phụ thuộc cấu trúc CSS/HTML classes nội bộ để kiểm chứng nội dung.

## 7. Kết quả HTML đã kiểm chứng: summary và detail khác nhau

Trong tài liệu do Javadoc tạo từ file demo:

**Class description summary** có nội dung:

```text
Tiện ích chuẩn hóa mã API cho miền api.example.test.
```

Nội dung tóm tắt class xuất hiện trong `SummaryTagDemo.html` và phần Index của `index-all.html`.

**Method Summary** của `normalize(String)` có nội dung:

```text
Chuyển mã nhập thành chữ hoa sau khi loại khoảng trắng ở hai đầu.
```

**Method Summary** của `isConfigured(String)` có nội dung:

```text
Kiểm tra cấu hình có được cung cấp hay không.
```

Còn nội dung “Chi tiết bổ sung không thuộc câu tóm tắt mặc định” có trong **Method Detail**, không nằm trong summary table. Điều này xác nhận sự khác nhau giữa việc **chọn summary** và việc **render toàn bộ mô tả**.

### Bằng chứng thú vị: dấu chấm trong tên miền

Class summary của ví dụ chứa `api.example.test.` — nhiều dấu chấm nằm trong đoạn người viết muốn giữ. Phần HTML summary vẫn chứa **đầy đủ tên miền và câu tóm tắt**, thay vì phải suy luận nên cắt tại dấu chấm nào.

Đây là một tình huống thẻ `{@summary ...}` có thể tốt hơn heuristic tự suy first sentence.

### Cách tự kiểm tra khi phát triển

1. Chạy `javadoc` bằng JDK mục tiêu.
2. Mở `docs/index.html` hoặc `docs/SummaryTagDemo.html` trong trình duyệt.
3. Tìm bảng **Method Summary** và kiểm tra summary của từng method.
4. Nhấp vào một method để mở **Method Detail**.
5. Kiểm tra mô tả sau tag vẫn có mặt trong detail.
6. So sánh với `index-all.html` nếu muốn xác nhận summary trên chỉ mục.
7. Nếu output không đúng, kiểm tra vị trí tag và lệnh/toolchain đang dùng.

Đừng viết test của tài liệu phụ thuộc mã CSS class do JDK tạo nếu mục tiêu chỉ là nội dung: cấu trúc HTML có thể đổi qua các bản JDK.

## 8. Phản ví dụ: đặt {@summary} sau câu mở đầu là sai

Một comment sai vị trí:

```java
/**
 * Đây là câu tóm tắt mặc định.
 * {@summary Đoạn này không thay câu tóm tắt.}
 * Thông tin chi tiết tiếp theo.
 */
public void process() { }
```

Nhìn bề ngoài vẫn có một tag summary, nhưng nó **không ở đầu main description**.

Theo đặc tả, thẻ chỉ có ý nghĩa chọn summary nếu xuất hiện ở **đầu**. Trong một thí nghiệm với JDK 24, cùng trường hợp sai vị trí này tạo cảnh báo:

```text
warning: invalid use of @summary
```

Và trong **Method Summary** vẫn là câu:

```text
Đây là câu tóm tắt mặc định.
```

Đoạn văn bản trong thẻ đặt sai có thể được render ở mô tả chi tiết, nhưng không thay phần tóm tắt như mong muốn. **Không mặc định rằng thẻ bị đặt sai vị trí sẽ tạo lỗi build**; có thể chỉ là warning nếu build chưa chọn chế độ nâng warning lên error.

### Cách sửa

```java
/**
 * {@summary Đây là câu tóm tắt do tác giả lựa chọn.}
 * Đoạn mô tả chi tiết nằm sau thẻ.
 */
public void process() { }
```

### Trường hợp viết hai câu trong summary

```java
/**
 * {@summary Cung cấp các API phiên bản v1.2.3. Hoạt động trên nhiều nguồn.}
 */
public final class MultiSentenceExample { }
```

Thẻ xác định một **vùng văn bản** chứ không có hợp đồng yêu cầu mỗi dấu chấm bên trong tự cắt đoạn. Nhưng **khuyến nghị nội dung** là giữ summary **một câu ngắn và hoàn chỉnh**. Không nên dùng khả năng bao nhiều câu để nhồi toàn bộ hướng dẫn vào bảng Summary.

## 9. Phân biệt inline tag và block tag

Javadoc có hai dạng tag chính.

### Inline tags

Có dạng:

```text
{@tag text}
```

Ví dụ:

- `{@summary ...}`: khai báo summary tường minh.
- `{@code ...}`: hiển thị một đoạn mã ở dạng code font.
- `{@link ...}`: liên kết tới một phần tử API.
- `{@literal ...}`: hiển thị text theo cách literal.

Một số inline tags có giới hạn vị trí đặc biệt, trong đó `{@summary}` chỉ có ý nghĩa summary ở **đầu main description**.

### Block tags

Có dạng:

```text
@param name description
@return description
@throws ExceptionType description
@since release
@see reference
```

Chúng xuất hiện sau phần mô tả chính, tạo mục riêng hoặc metadata trong documentation output.

**Không có thẻ block chuẩn `@summary` để thay `{@summary ...}`.** Nếu người viết gõ:

```java
/**
 * @summary Đây là tóm tắt.
 */
public class WrongStyle { }
```

thì đó không phải cú pháp của thẻ Javadoc summary chuẩn. Standard doclet có thể báo unknown tag hoặc không tạo output mong muốn. Hãy luôn dùng dạng **inline có cặp ngoặc nhọn**.

### Phân biệt với @return

`@return` giải thích **giá trị được trả về**. Nó không mô tả toàn bộ hành vi API. Một method cần cả summary lẫn thông tin return thì viết hai phần rõ ràng:

```java
/**
 * {@summary Tìm người dùng theo mã định danh.}
 * Truy vấn nguồn dữ liệu được cấu hình cho dịch vụ này.
 *
 * @param id mã người dùng
 * @return người dùng tìm được hoặc null nếu không tồn tại
 */
public User findUser(String id) { ... }
```

Đây là **đoạn minh họa API chưa runnable** vì `User` và thân phương thức không được định nghĩa; để biên dịch thực tế, hãy dựa vào chương trình hoàn chỉnh ở mục 6.

Trên các JDK hiện đại còn có dạng inline `{@return ...}` trong một số trường hợp method documentation, với chức năng tạo cả tóm tắt và phần Returns. Đây là **một thẻ khác**, không nên thay thế tất cả summaries bằng `{@return}` nếu method có hành vi chính không chỉ là trả một giá trị.

## 10. Truyền thống /** ... */ và Markdown /// trên JDK 23+

Đây là hai dạng comment tài liệu hiện được standard doclet hỗ trợ trên JDK mới.

### Dạng truyền thống: dùng được từ Java 10

```java
/**
 * {@summary Chuyển chuỗi thành dạng chữ hoa.}
 * Nội dung chi tiết và các block tags theo cú pháp Javadoc quen thuộc.
 */
public static String upper(String value) {
    return value.toUpperCase(java.util.Locale.ROOT);
}
```

Đây là lựa chọn **tương thích rộng** với JDK 17+, 21+ và môi trường xây dựng tài liệu chưa dùng Markdown documentation comments.

### Dạng Markdown: JDK 23 trở lên

**JEP 467 — Markdown Documentation Comments** (JDK 23) hỗ trợ những dòng comment bắt đầu bằng `///`. Inline Javadoc tags, gồm `{@summary ...}`, vẫn có thể xuất hiện trong phần text.

Ví dụ:

```java
/// {@summary Chuyển một giá trị thành cấu hình chuẩn.}
///
/// Thông tin chi tiết có thể dùng **Markdown** trên JDK 23+.
public class MarkdownSummaryCase {
    /// {@summary Đếm ký tự trong một chuỗi không null.}
    ///
    /// @param value chuỗi đầu vào
    /// @return số ký tự UTF-16
    public static int length(String value) {
        return value.length();
    }
}
```

Mã này đã được biên dịch với **`javac --release 23`** và Javadoc tạo HTML thành công trên JDK 24, có xác nhận nội dung summary của class và method.

**Giới hạn phải nhớ:**

- Tính năng `{@summary}` xuất hiện từ **Java 10**.
- Cú pháp comment Markdown `///` chỉ được hỗ trợ từ **JDK 23**.
- Nếu phải build tài liệu với JDK 17/21, dùng `/** ... */` thay cho `///`.
- Không coi nội dung `README.md` thông thường là một Javadoc comment có thể gắn cho method chỉ vì chứa `{@summary}`.
- Với dạng `///`, các dòng liên tiếp là một comment; một dòng trống không bắt đầu bằng `///` có thể kết thúc nhóm comment. Xem JDK-specific spec để tránh mất nội dung.

**Ví dụ chính mục 6 dùng comment truyền thống** để giữ khả năng chạy trên Java 17+, đúng theo mốc Java 10 của chủ đề.

## 11. Các loại phần tử có thể có summary

Theo bảng khả năng tag của standard doclet trên JDK 25, `summary` có thể xuất hiện trong mô tả tài liệu của nhiều phần tử, ví dụ:

| Phần tử | Ý nghĩa summary |
| --- | --- |
| **Module** | Mô tả ngắn mục đích của module |
| **Package** (thường từ `package-info.java`) | Nêu vai trò package |
| **Class / interface / enum / record** | Tóm tắt contract hoặc trách nhiệm của type |
| **Constructor** | Tóm tắt việc khởi tạo object |
| **Method / annotation element** | Tóm tắt hành vi của member |
| **Field / enum constant** | Tóm tắt ý nghĩa dữ liệu |
| **Overview và một số doc-files** | Tạo nội dung giới thiệu/tóm tắt theo khả năng standard doclet |

**Vị trí vẫn là nguyên tắc quyết định:** nằm ở đầu main description của phần tử hoặc của nội dung được doclet xử lý tương ứng.

Không đặt một `{@summary}` trong method A rồi kỳ vọng nó thay summary của method B. Mỗi Javadoc comment gắn với **declaration ngay sau nó**.

### Ví dụ với field

```java
/**
 * {@summary Số lần thử tối đa trước khi trả lỗi.}
 * Giá trị được dùng bởi bộ xử lý retry của ứng dụng.
 */
public static final int MAX_ATTEMPTS = 3;
```

Đây là đoạn minh họa, không phải một chương trình Java hoàn chỉnh. Field Summary sẽ dùng câu khai báo nếu doclet xử lý comment tương ứng.

### Ví dụ với interface

```java
/**
 * {@summary Cung cấp cách nạp cấu hình theo tên.}
 * Implementation có thể lấy cấu hình từ file, database hoặc biến môi trường.
 */
public interface ConfigReader {
    String load(String name);
}
```

Summary giúp người đọc chọn đúng abstraction; phần mô tả dài hơn trình bày các đảm bảo và giới hạn.

## 12. Cách viết một summary thật sự hữu ích

Dùng tag đúng cú pháp chưa đủ. Nội dung trong summary cần giúp người dùng đọc API ở chế độ lướt.

### Nên

- Dùng **một câu rõ ràng** mô tả trách nhiệm hoặc hành vi quan trọng nhất.
- Dùng động từ thích hợp đối với method: “Chuyển…”, “Lấy…”, “Tìm…”, “Kiểm tra…”.
- Đối với type, diễn đạt vai trò: “Đại diện cho…”, “Cung cấp…”, “Quản lý…”.
- Đối với field, nói **giá trị dùng để làm gì**, không nhắc lại tên field.
- Giữ thuật ngữ nhất quán với code và tên tham số.
- Để ngoại lệ, thuật toán, điều kiện tiền đề/hậu điều kiện **ở phần detail** và block tags.
- Nếu một mô tả có tên miền, version, dấu chấm hoặc cấu trúc có thể gây sai first-sentence parsing, dùng explicit summary.
- Sinh Javadoc HTML kiểm tra output thay vì chỉ đọc source code.

### Không nên

- Dùng tóm tắt “This is a class”, “Utility method”, “Does something”.
- Viết nhiều câu dài, chứa toàn bộ ví dụ và thuật toán vào summary table.
- Lặp nguyên xi tên method theo cách không cung cấp thêm ý nghĩa.
- Đưa secrets, thông tin môi trường private hoặc URL nội bộ nhạy cảm vào Javadoc công khai.
- Viết một câu mơ hồ, không nhất quán với return type hoặc exception contract.
- Nhầm summary với mục `@return`.
- Lặp nhiều thẻ summary để tạo danh sách nhiều mục.
- Đặt summary tag sau block tags hoặc sau câu mô tả mở đầu.

### Ví dụ trước – sau

Trước:

```java
/**
 * Process data. This method takes objects from various sources and
 * transforms them in an implementation-specific way.
 */
public Result process(Input data) { ... }
```

Sau:

```java
/**
 * {@summary Chuẩn hóa dữ liệu đầu vào trước khi kiểm tra tính hợp lệ.}
 * Phương thức chuyển định dạng và áp dụng các quy tắc nghiệp vụ.
 *
 * @param data dữ liệu đầu vào
 * @return kết quả chuẩn hóa
 */
public Result process(Input data) { ... }
```

Hai đoạn này chỉ để so **cách viết tài liệu**, chưa phải code runnable vì các types nghiệp vụ không được định nghĩa. Khi triển khai cần mô tả đúng sự thật về contract.

## 13. Lỗi liên quan dấu ngoặc, HTML và inline tags

### Lỗi: quên dấu đóng ngoặc

```java
/**
 * {@summary Tìm dữ liệu theo tên khóa.
 */
```

Thiếu dấu `}` có thể làm Javadoc parse sai thẻ hoặc báo lỗi. Đừng chỉ kiểm tra Java code compile được; chạy công cụ `javadoc` để bắt các lỗi doc comment.

### Lỗi: dùng HTML đặc biệt không đúng

Với **traditional Javadoc comments**, dấu `<`, `>` và `&` trong text cần được xử lý theo cú pháp HTML/Javadoc hợp lệ. Để hiển thị đoạn code, nên dùng inline `{@code ...}` hoặc escape thích hợp khi cần.

```java
/**
 * {@summary So sánh hai giá trị số nguyên.}
 * Điều kiện: {@code left < right}.
 */
```

Dấu `<` trong `{@code ...}` được hiển thị theo cách hỗ trợ mã, tránh coi nó là tag HTML trong text.

### Lỗi: dùng ngoặc nhọn không cân bằng

Nội dung của inline tags phải có **dấu ngoặc nhọn khớp nhau** để parser tìm được điểm kết thúc đúng. Nếu cần diễn đạt một literal có ngoặc đặc biệt, dùng escaping/tag phù hợp với đặc tả của JDK đang chạy, hoặc viết lại văn bản đơn giản.

### Lỗi: nhét cả block HTML lớn vào summary

Về kỹ thuật, summary tag render nội dung của nó. Nhưng một bảng HTML, đoạn code nhiều dòng hoặc heading trong summary dễ làm bố cục API table dài và khó quét.

**Nên đặt câu ngắn trong summary**, rồi đưa bảng, list và ví dụ vào phần mô tả chi tiết hoặc doc-files.

### Lỗi: tin rằng summary tự sinh ra return/throws contract

Không. `{@summary ...}` chỉ chọn đoạn summary. Các thông tin về tham số, return value và exceptions vẫn cần mô tả bằng các block tags hoặc nội dung rõ ràng.

## 14. Dùng doclint và kiểm thử tài liệu trong CI

Công cụ `javadoc` hiện đại cung cấp DocLint để phát hiện nhiều vấn đề trong comments như cú pháp, references, accessibility và mô tả thiếu.

Lệnh gợi ý:

```bash
javadoc -Xdoclint:all -d docs SummaryTagDemo.java
```

Nếu muốn build thất bại khi có warnings:

```bash
javadoc -Xdoclint:all -Werror -d docs SummaryTagDemo.java
```

**Có điều kiện:** `-Werror` yêu cầu Javadoc version hỗ trợ cờ này; nó báo lỗi khi có warnings. Cần kiểm chứng lệnh với JDK build của dự án.

Điểm cần nhớ:

- `javac` và `javadoc` không phải cùng một bước; code compile được không chứng minh tài liệu HTML đã chính xác.
- `-Xdoclint:all` có thể cảnh báo những vấn đề khác như thiếu `@param` hoặc method documentation, không chỉ `{@summary}`.
- Với tag đặt sai vị trí, phép thử JDK 24 hiển thị **warning: invalid use of @summary**.
- DocLint giúp bắt nhiều lỗi phổ biến nhưng **không tự bảo đảm chất lượng ngữ nghĩa của câu tóm tắt**.
- Sau khi CI pass, vẫn nên kiểm tra một vài bảng Summary trong HTML, nhất là các API quan trọng.

### Quy trình review cụ thể

1. Chạy Java tests để chắc logic không thay.
2. Sinh Javadoc bằng **JDK được CI dùng**.
3. Đọc warnings/errors và sửa nguồn comment.
4. Kiểm tra summary của class/method xuất hiện đúng trong output HTML.
5. Kiểm tra mô tả chi tiết không bị biến mất.
6. Đối chiếu `@param`, `@return`, `@throws` với signature thật.
7. Đảm bảo code examples trong documentation là đúng phiên bản API.
8. Nếu phát hành tài liệu public, kiểm tra cross-links và những nội dung nhạy cảm.
9. Không chỉ dựa vào một lệnh grep nguồn để kết luận summary được nhận.
10. Thực hiện lại kiểm tra khi nâng JDK/toolchain vì doclet HTML có thể đổi.

## 15. Phân biệt thẻ summary với các cơ chế tài liệu khác

| Công cụ / cú pháp | Dùng cho | Không nên hiểu là |
| --- | --- | --- |
| `{@summary ...}` | Chọn văn bản tóm tắt của một API description | Runtime annotation/validation |
| Câu đầu không tag | Chính sách summary mặc định | Luôn chính xác với mọi văn bản |
| `@param` | Mô tả tham số | Thay câu summary |
| `@return` | Mô tả giá trị trả về | Bắt buộc giống summary |
| `@throws` / `@exception` | Mô tả lỗi có thể ném | Thay đổi code exception |
| `@since` | Ghi mốc phiên bản API | Kích hoạt hỗ trợ của javac |
| `@deprecated` | Mô tả lý do API deprecated và cách thay thế | Tự động đổi hành vi code |
| `{@code ...}` | Hiển thị literal/code với formatting thích hợp | Dùng để chọn summary |
| `{@link ...}` | Liên kết phần tử API khác | Tự động chọn đoạn summary |
| `/// ...` (JDK 23+) | Dạng Markdown Javadoc comments | Tính năng Java 10 |
| `README.md` | Tài liệu cấp repo hoặc module | Javadoc comment cho một method cụ thể |

Khi một API đã deprecated, cách viết summary nên phản ánh contract rõ ràng và phần `@deprecated` mô tả lý do thay thế. Nhưng `{@summary}` **không tự đánh dấu API bị deprecated** và không thay annotation `@Deprecated`.

## 16. Câu hỏi thực tế trong dự án

### “Nếu câu đầu đã ngắn và đúng, có cần thêm tag không?”

Không. Có thể giữ cơ chế first-sentence mặc định. Thêm thẻ khi cần cố định ranh giới summary, giảm nhập nhằng, hoặc theo quy ước documentation của nhóm.

### “Có dùng tag trong Javadoc mô tả module không?”

Có trong phạm vi phần tử/nội dung mà standard doclet hỗ trợ. Nhưng vẫn phải theo cấu trúc comment đúng và xem kết quả trên JDK mục tiêu. Thẻ là cách định nghĩa summary, không thay nhu cầu mô tả purpose, exports/uses/provides của module nếu cần.

### “Dùng JDK 17 sinh tài liệu từ code Java 10 có được không?”

Có nếu source và API được toolchain hỗ trợ. `{@summary}` xuất hiện từ Java 10, nên có thể dùng trong comment truyền thống khi sinh Javadoc bằng JDK 17+. Không dùng `///` với JDK 17 vì đó là tính năng JDK 23+.

### “Lấy tên miền có nhiều dấu chấm vào summary được không?”

Có. Ví dụ thực tế `api.example.test.` đã xuất hiện trọn vẹn trong summary HTML do Javadoc tạo từ source.

### “Tại sao tag xuất hiện trong Method Detail dù không chọn được summary?”

Theo đặc tả, nội dung của tag được **render như văn bản**; ý nghĩa đặc biệt **chọn summary** chỉ có khi tag ở đầu main description. Trường hợp đặt giữa mô tả có thể tạo cảnh báo invalid use.

### “Đổi Javadoc có làm ảnh hưởng API binary compatibility?”

Chỉ thay documentation comment thông thường **không thay các method signatures hoặc Java runtime logic**, nhưng luôn chạy build/tests. Nếu code bị sửa thêm, cần kiểm tra binary/API compatibility riêng.

### “Có nên gắn summary với @since 10 để báo tính năng?”

Không. `@since` mô tả **phiên bản API được giới thiệu**, không phải phiên bản JDK đầu tiên nhận cú pháp Javadoc. Với một thư viện phát hành từ v3.4, `@since 3.4` có thể đúng hơn `@since 10`.

### “Có cách tự động nhìn summary mà không mở HTML không?”

Có thể kiểm tra generated HTML hoặc dùng công cụ kiểm thử documentation phù hợp. Nhưng không nên phụ thuộc DOM classes hoặc cách đặt tên file chỉ có ở một JDK version. Với code review, việc xem HTML trực tiếp thường rõ ràng và ít nhầm hơn.

## 17. Những lỗi phổ biến cần tránh

**Sai 1 — “Thẻ là `@summary`.”** Không. Cú pháp chuẩn là **`{@summary ...}`**.

**Sai 2 — “Đặt tag ở bất cứ đâu đều ghi đè summary.”** Không. Chỉ có ý nghĩa summary ở **đầu main description**.

**Sai 3 — “Javadoc sẽ tự nhận tag sau câu mở đầu.”** Sai. Thử nghiệm cho warning và bảng Summary tiếp tục dùng câu đầu.

**Sai 4 — “Có tag summary nghĩa là phần mô tả chi tiết biến mất.”** Không. Nội dung summary và chi tiết vẫn được render.

**Sai 5 — “Tag hoạt động như annotation runtime.”** Không. Đây là cách chỉ dẫn doclet sinh tài liệu.

**Sai 6 — “Một thẻ tự giải quyết các tài liệu thiếu `@param` / `@return`.”** Không. Các block tags có vai trò riêng.

**Sai 7 — “Dấu chấm trong hostname luôn làm nội dung tag bị cắt.”** Không; phần nội dung tag định nghĩa ranh giới explicit.

**Sai 8 — “Viết nhiều câu dài trong tag càng tốt.”** Không. Summary table nên ngắn, có nghĩa, dễ lướt.

**Sai 9 — “Thẻ chỉ có ở JDK 10 và đã bị bỏ ở JDK mới.”** Không. Đặc tả Java 25/26 vẫn hỗ trợ.

**Sai 10 — “Dạng `///` dùng được với JDK 17 vì summary có từ Java 10.”** Không. Markdown Javadoc comments là khả năng của JDK 23+.

**Sai 11 — “`javac` thành công chứng minh Method Summary HTML đúng.”** Không; phải chạy `javadoc` và kiểm tra output.

**Sai 12 — “DocLint không cảnh báo thẻ sai vị trí.”** Không chắc. JDK 24 đã cho warning `invalid use of @summary`.

**Sai 13 — “Có tag là không cần kiểm tra grammar/nội dung.”** Không. Nội dung ngắn gọn, chính xác vẫn do tác giả chịu trách nhiệm.

**Sai 14 — “Mỗi summary nên lặp tên method và toàn bộ signature.”** Không. Các cột khác thường đã trình bày signature; dùng câu để nói ý nghĩa/hành vi.

**Sai 15 — “Block tag đặt rồi vẫn có thể viết tiếp main description ở dưới.”** Không; main description kết thúc khi bắt đầu block tags.

**Sai 16 — “Tài liệu sinh bằng bất kỳ third-party doclet nào cũng có HTML giống standard doclet.”** Không. Đặc tả dùng để mô tả standard doclet; doclet khác có thể hỗ trợ/hiển thị khác.

**Sai 17 — “`@since 10` chính là cách bật summary.”** Không. Thẻ có mặt khi Javadoc tool hỗ trợ; @since là metadata phiên bản API.

**Sai 18 — “Có thể bỏ mọi thông tin điều kiện đầu vào và ném lỗi vì summary đã đủ.”** Không. Summary chỉ cho cái nhìn nhanh, chi tiết contract vẫn rất quan trọng.

**Sai 19 — “Summary không thể viết tiếng Việt hoặc chứa Unicode.”** Không. Với toolchain dùng UTF-8, Javadoc có thể hiển thị nội dung Unicode đúng; demo đã sinh và kiểm tra HTML tiếng Việt.

**Sai 20 — “Có thể dùng thẻ này để tự động tạo Markdown README từ runtime.”** Không. Javadoc inline tag được toolchain sinh tài liệu xử lý, không phải cơ chế tạo README từ JVM đang chạy.

## 18. Checklist review Javadoc với {@summary}

- [ ] Dùng JDK đang được hỗ trợ và có standard doclet hiểu thẻ từ JDK 10.
- [ ] Comment đúng loại `/** ... */` hoặc `///` nếu dùng JDK 23+.
- [ ] `{@summary ...}` nằm **ngay đầu main description**, trước mọi câu mô tả khác.
- [ ] Không gõ nhầm `@summary` dạng block tag.
- [ ] Dấu ngoặc nhọn của inline tag cân bằng và đóng đầy đủ.
- [ ] Văn bản summary ngắn, chính xác, không mơ hồ.
- [ ] Không dùng quá nhiều câu hoặc list/bảng trong summary.
- [ ] Summary có ích với người đọc phần API index/summary table.
- [ ] Mô tả chi tiết vẫn giải thích trường hợp góc, điều kiện, giới hạn.
- [ ] `@param` và `@return` khớp signature và logic.
- [ ] `@throws` phản ánh các exceptional cases quan trọng.
- [ ] Dùng `{@code}`/escaping đúng cho dấu HTML đặc biệt.
- [ ] Nếu code comment dùng Markdown, CI có JDK 23+ tương thích.
- [ ] Đã chạy `javadoc -Xdoclint:all` và xử lý warnings/errors.
- [ ] Có kiểm tra HTML Method Summary/Class Summary thực tế.
- [ ] Có kiểm tra Method Detail vẫn đầy đủ.
- [ ] Không phụ thuộc CSS/HTML internals của một bản doclet cụ thể.
- [ ] Không ghi `@since` theo version Java 10 nếu đó không phải phiên bản public API.
- [ ] Không đưa internal secrets vào tài liệu xuất bản.
- [ ] Đã chạy `javac`/unit tests để đảm bảo sửa comment không che thay đổi code.

## 19. Câu hỏi tự kiểm tra và đáp án

**1. Thẻ nào được bổ sung vào JDK 10 để khai báo summary tường minh?**

**Đáp án:** `{@summary nội dung}`, được ghi trong JDK-8173425.

**2. Khi không có thẻ summary, standard doclet chọn tóm tắt thế nào?**

**Đáp án:** Từ câu đầu của main description theo heuristic của Javadoc.

**3. Vị trí bắt buộc để tag có ý nghĩa chọn summary là đâu?**

**Đáp án:** Ở **đầu main description**, trước các câu mô tả khác.

**4. Nếu tag đặt sau câu đầu, Javadoc có chắc dùng nội dung tag làm summary không?**

**Đáp án:** Không. Trong thử nghiệm JDK 24, tag sai vị trí bị warning và câu đầu vẫn là summary.

**5. Có phải toàn bộ mô tả sau summary biến mất trên HTML không?**

**Đáp án:** Không. Phần còn lại vẫn được render trong detail.

**6. Vì sao summary explicit hữu ích khi có chuỗi v1.2.3 hoặc api.example.test?**

**Đáp án:** Giúp định nghĩa ranh giới tóm tắt rõ ràng mà không dựa vào heuristic dấu câu.

**7. `@summary` và `{@summary ...}` có giống nhau không?**

**Đáp án:** Không. Dạng chuẩn là **inline tag có ngoặc nhọn**.

**8. Thẻ này có làm thay đổi `main()` hoặc bytecode runtime không?**

**Đáp án:** Không. Nó là metadata cho công cụ sinh tài liệu, không phải logic thực thi.

**9. Lệnh nào kiểm tra đầu ra Javadoc của demo?**

**Đáp án:** `javadoc -Xdoclint:all -d docs SummaryTagDemo.java`, rồi mở trang HTML.

**10. `javac --release 17` có dùng thẻ summary được không?**

**Đáp án:** Có trong Javadoc comment truyền thống, vì tag đã có từ JDK 10.

**11. Dạng comment Markdown `///` xuất hiện từ JDK nào?**

**Đáp án:** JDK 23, theo JEP 467.

**12. Dùng `///` với JDK 17 để có summary có đúng không?**

**Đáp án:** Không. Hãy dùng comment truyền thống `/** ... */` cho JDK 17.

**13. `@return` có thay chức năng của summary không?**

**Đáp án:** Không. Nó mô tả giá trị được trả về, khác tóm tắt trách nhiệm API.

**14. Có thể dùng `{@summary}` cho class và field không?**

**Đáp án:** Có trong phạm vi comments được standard doclet hỗ trợ.

**15. Nếu summary chứa tên miền có nhiều dấu chấm thì sao?**

**Đáp án:** Toàn bộ text của tag được dùng theo khai báo; demo đã kiểm tra output có `api.example.test.`.

**16. Vì sao Javadoc có thể cảnh báo dù Java source compile bình thường?**

**Đáp án:** Công cụ tạo tài liệu kiểm tra cú pháp/vị trí của Javadoc tags; compiler và doclet có nhiệm vụ khác nhau.

**17. `@since 10` có phải điều kiện cần cho thẻ summary không?**

**Đáp án:** Không. @since ghi phiên bản API, không bật một thẻ Javadoc.

**18. Có nên ép tất cả methods phải chứa thẻ summary không?**

**Đáp án:** Không bắt buộc. Nếu câu đầu rõ nghĩa và doclet lấy đúng, mặc định vẫn hợp lệ.

**19. Chỉ có output `normalized=JAVA` chứng minh summary HTML đúng không?**

**Đáp án:** Không. Output kiểm tra code, còn summary cần kiểm tra file HTML sinh bởi Javadoc.

**20. Một câu tóm tắt chất lượng cao cần điều gì?**

**Đáp án:** Ngắn gọn, chính xác về hành vi, hữu ích khi lướt API và không lấn át phần mô tả chi tiết.

## 20. Tài liệu chính thức, còn áp dụng

1. [Oracle JDK 10 Release Notes — Comment Tag for Summary of an API Description](https://www.oracle.com/java/technologies/javase/10all-relnotes.html): xác nhận tính năng thêm ở JDK 10, issue JDK-8173425 và lý do không thể luôn suy summary chính xác từ câu đầu.
2. [Oracle Java SE 25 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html): cú pháp chính thức `{@summary text}`, vị trí ở đầu main description, quy tắc render và các declaration được hỗ trợ.
3. [Oracle Java SE 26 — Documentation Comment Specification for the Standard Doclet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html): đối chiếu thẻ vẫn hiện diện trong đặc tả Javadoc mới.
4. [Oracle Java SE 24 — Markdown in Documentation Comments](https://docs.oracle.com/en/java/javase/24/javadoc/using-markdown-documentation-comments.html): cách dùng cú pháp `///` từ JDK 23, kết hợp inline Javadoc tags.
5. [OpenJDK JEP 467 — Markdown Documentation Comments](https://openjdk.org/jeps/467): mốc JDK 23 cho dạng Markdown Javadoc comments, khác tính năng `{@summary}` từ JDK 10.
6. [Oracle Java SE 25 — The javadoc Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javadoc.html): các option `-Xdoclint`, `-Werror`, encoding, doclet và xuất HTML.
7. [Oracle Java SE 25 — The javac Command](https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html): `--release`, `-Xdoclint` và phân biệt kiểm tra Java code/Javadoc comments.
8. [dev.java — Javadoc Documentation Generator](https://dev.java/learn/jvm/core-tools/javadoc/): các khái niệm, cách sinh và kiểm tra HTML API documentation.

**Kết luận:** `{@summary ...}` được giới thiệu ở **Java 10** để tác giả Javadoc có thể **chọn chính xác nội dung phần tóm tắt**, thay vì hoàn toàn phụ thuộc heuristic tách câu đầu. Đặt thẻ ở **đầu main description**, viết một câu ngắn có ý nghĩa, rồi để phần mô tả dài và `@param`/`@return`/`@throws` theo sau. Công cụ `javadoc` sẽ hiển thị nội dung đó trong các bảng Summary/Index và vẫn render mô tả chi tiết. Đây là tính năng **vẫn áp dụng trên JDK hiện hành**; nếu dùng JDK 23+, có thể viết comment Markdown `///`, còn với JDK 17/21, comment truyền thống `/** ... */` là lựa chọn tương thích.
