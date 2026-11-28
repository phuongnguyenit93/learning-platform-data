# JEP 413 và vai trò của đoạn mã minh họa trong hợp đồng tài liệu API

## 1. Mục tiêu và phạm vi

**JEP 413 – Code Snippets in Java API Documentation** đưa thẻ inline `{@snippet ...}` vào công cụ Javadoc từ **JDK 18**. Đây là tính năng đã được tích hợp chính thức, tiếp tục có trên các JDK hiện đại. Nó giúp tác giả tài liệu API đưa ví dụ mã có định dạng rõ ràng, có thể trích từ tệp bên ngoài, đánh dấu phần quan trọng và liên kết đến API liên quan.

Sau bài này, người học có thể:

- Giải thích vì sao ví dụ mã là một phần quan trọng của **tài liệu hợp đồng API** và phân biệt ví dụ với các điều kiện bắt buộc của hợp đồng.
- Viết thẻ `@snippet` dạng **inline**, **external** và nhận biết dạng **hybrid**.
- Dùng `region`, `@start`, `@end`, `@highlight`, `@link` và `@replace` để trình bày đúng phần mã cần đọc.
- Tạo tài liệu Javadoc, biên dịch và chạy ví dụ bên ngoài, phát hiện sự lệch nhau giữa mã minh họa với hành vi thực tế.

Phạm vi ở đây là **tài liệu API Java**, không phải cơ chế thực thi mã Java mới. `@snippet` được xử lý bởi công cụ **Javadoc** khi sinh tài liệu; bản thân nó không tạo phương thức, không thay đổi bytecode và không tự động chạy ví dụ.

## 2. Đoạn mã minh họa giúp thể hiện hợp đồng API như thế nào?

Một API hữu ích cần giải thích ít nhất: **đầu vào hợp lệ**, **kết quả**, **ngoại lệ**, **tác động phụ** và **cách sử dụng đúng**. Khai báo kiểu Java thường chưa đủ: `String create(String namespace, long id)` không cho biết chuỗi kết quả có định dạng gì hay `id` âm được xử lý ra sao.

| Thành phần tài liệu | Câu hỏi cần trả lời | Vai trò của snippet |
| --- | --- | --- |
| Mô tả phương thức | API làm gì, có tác động phụ không? | Cho người đọc thấy luồng gọi điển hình. |
| `@param` | Giá trị nào hợp lệ? | Đưa ví dụ với dữ liệu hợp lệ, dễ nhận biết. |
| `@return` | Giá trị trả về có hình thức hoặc ý nghĩa gì? | Cho thấy giá trị mong đợi trong tình huống cụ thể. |
| `@throws` | Khi nào có lỗi và lỗi thuộc loại nào? | Có thể minh họa một trường hợp lỗi, nhưng không thay mô tả điều kiện lỗi. |
| Ví dụ được kiểm thử | Người sử dụng cần viết mã thế nào? | Giúp phát hiện tài liệu lạc hậu khi API thay đổi. |

**Ranh giới cần giữ:** mô tả bằng lời, chữ ký phương thức và các thẻ `@param`, `@return`, `@throws` vẫn xác định các điều kiện cần công bố. Ví dụ mã làm rõ một hoặc vài trường hợp. Một ví dụ chạy thành công **không chứng minh** mọi đầu vào đều đúng, mọi ngoại lệ đã được mô tả hay API có bảo đảm mới ngoài hợp đồng đã viết.

Javadoc vốn hỗ trợ `{@code ...}` cho đoạn ngắn và `<pre>{@code ...}</pre>` cho nhiều dòng; chúng vẫn hợp lệ. `{@snippet}` đặc biệt hữu ích khi ví dụ đủ quan trọng để quản lý như mã nguồn, chọn một vùng cần hiển thị hoặc làm nổi bật cú pháp cần chú ý.

## 3. Ba cách khai báo snippet

Thẻ `@snippet` nằm **trong chú thích Javadoc** và có các hình thức chính:

```java
// Inline: nội dung xuất hiện trực tiếp sau dấu ":" và dòng mới.
{@snippet :
    String text = "Java 18";
    System.out.println(text);
}

// External: lấy mã từ tệp ví dụ (có thể chỉ lấy một vùng).
{@snippet file="EventKeyExamples.java" region=basic}

// Hybrid: vừa có mã inline, vừa trỏ đến tệp bên ngoài.
{@snippet file="EventKeyExamples.java" region=basic :
    String key = EventKeys.create("order", 7L);
    if (!"order:7".equals(key)) {
        throw new AssertionError(key);
    }
}
```

Các dạng trên là **minh họa cú pháp của nội dung nằm trong Javadoc**, không phải những câu lệnh Java được đặt trực tiếp trong thân lớp. Hai thuộc tính thông dụng khác:

- `lang="java"`: khai báo ngôn ngữ hiển thị; mã inline mặc định là Java. Có thể dùng `lang="properties"` khi minh họa cấu hình.
- `id="example-name"`: tạo định danh cho snippet trong HTML, hữu ích khi muốn dẫn đến một ví dụ cụ thể.

Với snippet inline, phần nội dung bắt đầu **sau dòng mới theo sau dấu `:`**; các cặp dấu ngoặc nhọn `{` và `}` trong thân phải cân bằng để Javadoc xác định dấu kết thúc thẻ. Khoảng thụt lề chung được loại bỏ theo quy tắc tương đương `String.stripIndent()`.

## 4. Viết snippet inline để giải thích một hợp đồng cụ thể

Giả sử thư viện cung cấp `EventKeys.create(namespace, id)` để tạo khóa sự kiện. Hợp đồng mong muốn:

- `namespace` không được `null`, rỗng hoặc chỉ gồm khoảng trắng; giữ nguyên ký tự của chuỗi hợp lệ.
- `id` phải không âm.
- Kết quả có dạng `namespace:id`; phương thức không sửa dữ liệu đầu vào và không ghi trạng thái bên ngoài.

Tệp `src/main/java/example/EventKeys.java`:

```java
package example;

import java.util.Objects;

/** Các thao tác tạo khóa định danh cho sự kiện. */
public final class EventKeys {
    private EventKeys() {
    }

    /**
     * Tạo khóa sự kiện ở dạng {@code namespace:id}.
     *
     * <p>Phương thức giữ nguyên namespace và không có tác động phụ.
     * Ví dụ với một mã sự kiện hợp lệ:
     *
     * {@snippet :
     * String key = EventKeys.create("order", 7L);
     * if (!"order:7".equals(key)) {
     *     throw new AssertionError(key);
     * }
     * }
     *
     * @param namespace không được null, rỗng hoặc chỉ chứa khoảng trắng
     * @param id số nguyên không âm
     * @return chuỗi gồm namespace, dấu hai chấm và id dạng thập phân
     * @throws NullPointerException nếu namespace là null
     * @throws IllegalArgumentException nếu namespace rỗng hoặc chỉ gồm khoảng trắng
     *         hoặc id âm
     */
    public static String create(String namespace, long id) {
        Objects.requireNonNull(namespace, "namespace");
        if (namespace.isBlank()) {
            throw new IllegalArgumentException("namespace is blank");
        }
        if (id < 0) {
            throw new IllegalArgumentException("id must be non-negative");
        }
        return namespace + ":" + id;
    }
}
```

Khi chạy Javadoc, ví dụ được trình bày như đoạn mã dễ sao chép, không hiển thị dấu `*` đầu dòng của chú thích. Người đọc thấy được **lời gọi thực tế và kết quả kỳ vọng**. Phần `@throws` mới là nơi công bố chính xác điều kiện lỗi; snippet trên chỉ minh họa một đầu vào hợp lệ.

Lưu ý: đoạn inline không được Javadoc tự động biên dịch. Việc nó nằm cạnh phương thức cũng không chứng minh nó đã được kiểm thử. Ngoài ra, inline snippet nằm trong `/** ... */`, nên **không thể chứa chuỗi kết thúc chú thích** `*/`, kể cả khi chuỗi đó ở trong literal; dấu ngoặc nhọn không cân bằng cũng gây lỗi. Khi ví dụ cần nhiều đoạn chú thích, nhiều dòng hoặc kiểm thử chạy được, hãy chuyển sang external snippet.

## 5. External snippet: một ví dụ vừa xuất hiện trong tài liệu vừa chạy được

Đưa mã minh họa vào tệp riêng giúp dùng công cụ Java thông thường để **biên dịch và chạy đúng nguồn mã mà tài liệu trích dẫn**. Với package `example`, có thể tổ chức:

```text
src/main/java/
└── example/
    ├── EventKeys.java
    └── snippet-files/
        └── EventKeyExamples.java
```

Tệp `src/main/java/example/snippet-files/EventKeyExamples.java` chứa một lớp có thể thực thi:

```java
package example;

public final class EventKeyExamples {
    private EventKeyExamples() {
    }

    public static void main(String[] args) {
        // @start region=basic
        String key = EventKeys.create("order", 7L);
        if (!"order:7".equals(key)) {
            throw new AssertionError(key);
        }
        // @end region=basic
    }
}
```

Trong Javadoc của phương thức `EventKeys.create`, thay thẻ inline bằng:

```java
/**
 * Tạo khóa sự kiện có dạng {@code namespace:id}.
 *
 * <p>Ví dụ sử dụng:
 * {@snippet file="EventKeyExamples.java" region=basic}
 *
 * @param namespace không được null, rỗng hoặc chỉ chứa khoảng trắng
 * @param id số nguyên không âm
 * @return chuỗi gồm namespace, dấu hai chấm và id
 * @throws NullPointerException nếu namespace là null
 * @throws IllegalArgumentException nếu namespace rỗng hoặc chỉ gồm khoảng trắng
 *         hoặc id âm
 */
```

Trong trường hợp này:

1. Thuộc tính `file` tìm tệp ví dụ trong thư mục `snippet-files` của package có Javadoc (hoặc theo đường dẫn bổ sung qua tùy chọn `--snippet-path`).
2. `// @start region=basic` và `// @end region=basic` xác định **phần mã** cần trích; các dòng định nghĩa lớp và `main` vẫn có mặt để chạy ví dụ nhưng không chiếm chỗ trong trang tài liệu.
3. Các dấu đánh dấu vùng là **markup comment** cho Javadoc, được bỏ khỏi nội dung hiển thị.
4. Nếu cần trích nhiều tình huống từ một tệp, mỗi tình huống có thể đặt trong một vùng mang tên khác nhau.

Ví dụ lệnh thực hành trên JDK có hỗ trợ `@snippet` (JDK 18 trở lên), chạy từ thư mục gốc dự án:

```sh
# Tạo tài liệu API cho package example.
javadoc -encoding UTF-8 -d build/docs -sourcepath src/main/java example

# Biên dịch cả API lẫn tệp chứa snippet có thể chạy.
javac -encoding UTF-8 -d build/classes \
  src/main/java/example/EventKeys.java \
  src/main/java/example/snippet-files/EventKeyExamples.java

# Chạy kiểm tra hành vi: thành công nếu chương trình kết thúc bình thường.
java -cp build/classes example.EventKeyExamples
```

**Điểm cốt lõi:** lệnh `javadoc` tạo tài liệu và xử lý chỉ thị trình bày; việc biên dịch/chạy `EventKeyExamples` là bước **riêng**. Nếu gọi `javadoc` thành công nhưng bỏ qua `javac` và lệnh chạy, vẫn chưa có bằng chứng snippet thực sự tương thích với API.

## 6. Markup comment giúp hướng sự chú ý mà không sửa mã gốc

Các chỉ thị này đặt trong **comment của mã snippet**. Khi hiển thị HTML, Javadoc xử lý và ẩn comment chứa markup. Có thể đặt cuối dòng mã hoặc đặt một dòng comment riêng với dấu `:` cuối comment để áp dụng cho dòng kế tiếp.

| Chỉ thị | Tác dụng | Điểm cần nhớ |
| --- | --- | --- |
| `@highlight` | Tô đậm hoặc đánh dấu toàn dòng, một `substring` hoặc chuỗi khớp `regex`. | Điều khiển **cách nhìn**, không thay hành vi Java. |
| `@link` | Tạo liên kết từ văn bản trong snippet đến khai báo API. | `target` có cách tham chiếu tương tự thẻ Javadoc `{@link ...}`. |
| `@replace` | Thay ký tự khi **hiển thị** bằng một chuỗi khác. | Mã nguồn thật vẫn giữ nguyên để có thể biên dịch/chạy. |
| `@start region=ten` / `@end region=ten` | Khoanh vùng để trích dẫn hoặc áp dụng markup. | Chọn tên vùng rõ nghĩa, đóng vùng đầy đủ. |

Ví dụ inline đơn giản làm nổi bật lời gọi quan trọng:

```java
/**
 * {@snippet :
 * String key = EventKeys.create("order", 7L); // @highlight substring="EventKeys.create"
 * System.out.println(key);                    // @link substring="println" target="java.io.PrintStream#println(String)"
 * }
 */
```

`EventKeys.create` được đánh dấu để người đọc tập trung vào thao tác chính; `println` trở thành liên kết tới API tương ứng. Không cần thay đổi thân ví dụ để tạo hiệu ứng này.

Ví dụ dùng `@replace` để rút gọn một giá trị hiển thị:

```java
/**
 * {@snippet :
 * String key = EventKeys.create("some-long-namespace", 7L); // @replace substring='"some-long-namespace"' replacement='"demo"'
 * }
 */
```

Trang tài liệu hiển thị đối số `"demo"` tại vị trí được thay thế; chuỗi trong mã nguồn vẫn là `"some-long-namespace"`. Vì vậy, chỉ dùng `@replace` để **lược bỏ chi tiết không thiết yếu**, không dùng nó để che giấu khác biệt về quy tắc đầu vào, kiểu dữ liệu hoặc kết quả của API.

Khi cần làm nổi bật **nhiều dòng**, dùng vùng:

```java
/**
 * {@snippet :
 * // @highlight region=check substring="key" type=bold :
 * String key = EventKeys.create("order", 7L);
 * System.out.println(key);
 * // @end region=check
 * }
 */
```

Dấu `:` cuối comment chứa `@highlight` khiến chỉ thị bắt đầu tác động từ **dòng kế tiếp**. `@end region=check` kết thúc phạm vi đánh dấu. Với ví dụ external, vùng trích dẫn `@start region=basic` có thể độc lập với vùng dùng để làm nổi bật; tránh chọn tên vùng mơ hồ hoặc thiếu `@end`.

## 7. Hybrid snippet và vấn đề đồng bộ nội dung

Hybrid kết hợp ưu điểm của cả hai dạng: người đọc tệp nguồn thấy ví dụ ngay cạnh lời mô tả, còn Javadoc có một tệp bên ngoài để tham chiếu. Trong tài liệu của `EventKeys.create` có thể viết:

```java
/**
 * {@snippet file="EventKeyExamples.java" region=basic :
 * String key = EventKeys.create("order", 7L);
 * if (!"order:7".equals(key)) {
 *     throw new AssertionError(key);
 * }
 * }
 */
```

Với hybrid, Standard Doclet **đối chiếu kết quả xử lý** của phần inline và phần external; nếu không khớp, Javadoc báo lỗi. Cơ chế này giúp phát hiện một loại lệch nội dung khi người viết sửa một phía. Tuy nhiên, nó **không thay thế kiểm thử hành vi**: hai đoạn cùng sai logic vẫn có thể khớp về văn bản.

Vì phải duy trì hai bản thể hiện, chỉ nên dùng hybrid khi nhu cầu xem mã trực tiếp trong chú thích thực sự quan trọng. Với ví dụ dài, có nhiều test hoặc được sử dụng lại, external thường dễ bảo trì hơn.

## 8. Giữ hợp đồng API và ví dụ đồng nhất theo thời gian

Một luồng làm việc thực tế cho API công khai:

1. **Viết hợp đồng trước:** nêu rõ điều kiện hợp lệ, kết quả, ngoại lệ và tác động phụ. Ví dụ không được làm người đọc suy ra điều trái với hợp đồng.
2. **Chọn ví dụ điển hình:** bao gồm lời gọi tối thiểu và kết quả có thể kiểm chứng. Nếu trình bày lỗi, chỉ rõ loại lỗi kỳ vọng; không mặc định mọi lỗi cùng loại.
3. **Đặt mã quan trọng trong external snippet:** giữ tệp có thể biên dịch; ưu tiên ví dụ thực thi được thay vì đoạn minh họa mơ hồ.
4. **Kiểm thử trên JDK mục tiêu:** tạo Javadoc để bắt lỗi thẻ/vùng; biên dịch và chạy ví dụ để bắt lỗi API, chữ ký hoặc kết quả.
5. **Kiểm tra lại khi API thay đổi:** chẳng hạn chuyển `id` sang chuỗi, thay dấu phân cách, thay điều kiện chấp nhận khoảng trắng hoặc đổi ngoại lệ; cập nhật đồng thời lời mô tả, snippet và kiểm thử.

Với `EventKeys.create`, bài kiểm tra hợp đồng có thể bổ sung:

```java
import example.EventKeys;

class EventKeysContractCheck {
    public static void main(String[] args) {
        if (!"order:7".equals(EventKeys.create("order", 7))) {
            throw new AssertionError("Kết quả không đúng");
        }

        try {
            EventKeys.create(" ", 7);
            throw new AssertionError("Phải từ chối namespace trắng");
        } catch (IllegalArgumentException expected) {
            // Đúng loại ngoại lệ đã mô tả.
        }

        try {
            EventKeys.create(null, 7);
            throw new AssertionError("Phải từ chối null");
        } catch (NullPointerException expected) {
            // Đúng loại ngoại lệ đã mô tả.
        }
    }
}
```

Đây là **mã minh họa kiểm tra bổ sung**, không phải nội dung Javadoc tự sinh hay mã mà `javadoc` tự chạy. Trong dự án thực, có thể chuyển các điều kiện đó thành unit test độc lập, chạy cùng quy trình CI. Cần thử thêm `id < 0` và các dữ liệu ranh giới đúng với hợp đồng dự án.

### Các lỗi dễ mắc

| Hiện tượng | Nguyên nhân thường gặp | Cách xử lý |
| --- | --- | --- |
| Javadoc không tìm thấy external snippet. | Đặt tệp sai `snippet-files`, dùng tên `file` sai hoặc chưa cấu hình `--snippet-path`. | Kiểm tra đường dẫn tương đối theo package của mã nguồn chứa thẻ. |
| Javadoc không tìm thấy `region`. | Viết sai tên hoặc thiếu `@start`/`@end`. | Đối chiếu chính xác tên vùng trong thẻ và trong comment. |
| Inline snippet lỗi cú pháp. | Có chuỗi kết thúc chú thích hoặc dấu `{`/`}` không cân bằng. | Đổi sang external snippet khi nội dung không biểu diễn an toàn trong Javadoc. |
| Trang tài liệu đẹp nhưng ví dụ không chạy. | Chỉ tạo HTML, chưa biên dịch/chạy file ví dụ. | Chạy kiểm tra biên dịch và thực thi riêng. |
| Tài liệu hứa một hành vi khác chương trình. | Thay đổi implementation nhưng quên sửa contract hoặc ví dụ. | Cập nhật cùng một thay đổi và kiểm tra lại các trường hợp ranh giới. |
| `@replace` hiển thị ví dụ gây hiểu nhầm. | Văn bản trình bày khác mã được kiểm thử về mặt ngữ nghĩa. | Chỉ rút gọn chi tiết phụ; giữ nguyên các giả định của hợp đồng. |

## 9. Tự thực hành

Hãy bổ sung phương thức `EventKeys.create(namespace, id)` bằng một đoạn external snippet mới cho trường hợp `id = 0`. Tệp chứa snippet cần:

- Được tham chiếu bằng một `region` có tên riêng, chẳng hạn `zeroId`.
- Biên dịch được bằng `javac` và có kiểm tra rằng kết quả bằng `"order:0"`.
- Được hiển thị trong tài liệu bằng `{@snippet file="EventKeyExamples.java" region=zeroId}`.
- Có một `@highlight` làm nổi bật lời gọi API, không che khuất dữ liệu đầu vào hay kết quả.

Sau đó cố ý thay `"order:0"` thành `"order-0"` trong kỳ vọng của ví dụ. Quan sát rằng **biên dịch có thể vẫn thành công nhưng chạy ví dụ phải thất bại**. Đây chính là lý do cần kiểm thử hành vi bên cạnh khả năng dựng tài liệu.

## 10. Ghi nhớ

- **JEP 413 là tính năng Javadoc từ Java 18 vẫn dùng được trên JDK hiện đại.** `@snippet` hỗ trợ trình bày mã; nó không thay đổi hành vi runtime.
- **Hợp đồng API gồm các quy tắc được công bố**, không chỉ các ví dụ. Mọi ví dụ cần nhất quán với `@param`, `@return`, `@throws` và mô tả phương thức.
- **External snippet có thể được kiểm thử như mã Java thật.** Dựng Javadoc và biên dịch/chạy snippet là hai công việc bổ sung cho nhau.
- **Markup comment điều chỉnh cách hiển thị**, còn hybrid kiểm tra sự khớp giữa hai bản trình bày; cả hai đều không thay thế bài kiểm tra hành vi.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle Javadoc Guide – Snippets (JDK 25)](https://docs.oracle.com/en/java/javase/25/javadoc/snippets.html).
- [Oracle – Documentation Comment Specification for the Standard Doclet (JDK 25)](https://docs.oracle.com/en/java/javase/25/docs/specs/javadoc/doc-comment-spec.html).
