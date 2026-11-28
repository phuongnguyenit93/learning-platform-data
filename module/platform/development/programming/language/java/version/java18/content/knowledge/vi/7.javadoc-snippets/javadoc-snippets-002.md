# Lựa chọn @snippet cho ví dụ nhiều dòng và @code cho định danh hoặc biểu thức ngắn

## 1. Mục tiêu học tập và bối cảnh

Trong module `JAVA_VERSION_JAVA18`, Javadoc snippet là một trong những cải tiến của Java 18 vẫn hữu ích trên JDK hiện đại, bên cạnh các chủ đề như UTF-8 mặc định và máy chủ web đơn giản. Bài này tập trung vào **lựa chọn cách trình bày mã trong tài liệu API** và bảo đảm ví dụ không mâu thuẫn với hợp đồng của API.

Sau bài học, bạn có thể:

- Dùng `{@code ...}` cho **tên kiểu, tên phương thức, giá trị, biểu thức ngắn** nằm trong một câu văn.
- Dùng `{@snippet ...}` cho **một hoặc nhiều câu lệnh** cần đọc thành một luồng xử lý, đặc biệt khi có xuống dòng, điều kiện, vòng lặp hoặc xử lý kết quả.
- Quyết định lúc nào cần đưa snippet vào tệp ngoài để **biên dịch, chạy và kiểm chứng**.
- Phân biệt mã chỉ được **hiển thị** với mã có **liên kết API** hoặc đã được **kiểm thử**.

Cả `{@code}` và `{@snippet}` đều là **inline tag của Javadoc**, được viết trong chú thích tài liệu của Java. `{@code}` đã được hỗ trợ từ lâu và vẫn hợp lệ; `{@snippet}` được chuẩn hóa qua **JEP 413, từ JDK 18**, và tiếp tục được sử dụng trong các JDK mới. Hai thẻ không tạo ra lệnh Java mới, không thực thi mã và không tự xác nhận rằng ví dụ đúng.

## 2. Quy tắc chọn nhanh

| Nội dung muốn truyền đạt | Nên chọn | Vì sao? |
| --- | --- | --- |
| Tên lớp `Path`, kiểu `List<String>`, biến `timeout` | `{@code ...}` | Nội dung ngắn, nên đọc liền trong câu. |
| Giá trị `null`, `"READY"`, `-1` | `{@code ...}` | Làm rõ giá trị ký tự hoặc mã nguồn. |
| Biểu thức `index < size`, `value.isBlank()` | `{@code ...}` | Cần giữ nguyên các ký tự đặc biệt và đọc như mã. |
| Một ví dụ có 3–10 câu lệnh, `if`, `try`, `return` | `{@snippet ...}` | Giữ xuống dòng, thụt lề và cấu trúc điều khiển. |
| Ví dụ dài, cần chia vùng, tái sử dụng hoặc kiểm thử chạy | `{@snippet file="..."}` | Lấy mã từ tệp riêng, tránh sao chép một bản ví dụ khó duy trì. |
| Muốn người đọc **nhấp vào** tên API | `{@link ...}` | `@code` chỉ định dạng chữ, không tạo liên kết. |

Có thể tự hỏi theo thứ tự: **(1)** Cần dẫn đến trang tài liệu API? Chọn `@link`. **(2)** Cần cho thấy nhiều thao tác hoặc cấu trúc mã? Chọn `@snippet`. **(3)** Chỉ cần nhắc tên hoặc một biểu thức ngắn trong câu? Chọn `@code`.

Đây là hướng dẫn lựa chọn theo **mục đích đọc hiểu**, không phải giới hạn cứng về số dòng. Một lệnh đơn lẻ nhưng cần định dạng như ví dụ độc lập vẫn có thể dùng `@snippet`. Ngược lại, một biểu thức ngắn không cần tạo hẳn một khối mã.

## 3. Dùng @code để diễn đạt chính xác ngay trong câu văn

Cú pháp:

```java
{@code nội_dung_cần_hiển_thị}
```

Với `@code`, Standard Doclet hiển thị nội dung theo kiểu chữ mã nguồn và **không coi các ký tự `<`, `>`, `&` là HTML**, cũng không phân tích các thẻ Javadoc lồng bên trong. Vì thế những đoạn mã ngắn có thể được viết trực tiếp, dễ đọc:

```java
/**
 * Chấp nhận một {@code List<String>} không null.
 *
 * <p>Giá trị {@code index} hợp lệ khi
 * {@code 0 <= index && index < size}.
 *
 * <p>Trả về {@code "READY"} khi hoàn tất,
 * hoặc {@code null} nếu không có dữ liệu.
 *
 * <p>Có thể kiểm tra chuỗi bằng {@code value.isBlank()}.
 */
```

Trang HTML sinh ra hiển thị các đoạn `List<String>`, `0 <= index && index < size` và `"READY"` như mã, không biến `<String>` thành HTML hay khiến `&&` ảnh hưởng đến nội dung trang.

Một vài mẫu hữu ích trong tài liệu API:

```java
/** Tham số {@code timeoutMillis} phải lớn hơn {@code 0}. */
/** Gọi {@code Objects.requireNonNull(value, "value")} trước khi dùng. */
/** Khóa có dạng {@code namespace + ":" + id}. */
/** Trạng thái mặc định là {@code "PENDING"}. */
```

**Điểm cần phân biệt:** `{@code String#isBlank()}` chỉ hiển thị dòng chữ `String#isBlank()`; muốn có liên kết đến phương thức, dùng `{@link String#isBlank()}`. `{@code ...}` cũng **không tự kiểm tra** biểu thức có biên dịch được hay đúng với hành vi API hay không.

### Khi không nên chọn @code

Nếu muốn người đọc hiểu một quy trình gồm **khởi tạo dữ liệu → gọi API → kiểm tra kết quả**, việc nhồi cả quy trình vào một chuỗi dài trong `{@code}` làm tài liệu khó đọc. `@code` không tự tạo bố cục khối mã với thụt lề và các tiện ích xử lý snippet. Khi nội dung cần trông như một ví dụ độc lập, chuyển sang `@snippet`.

Lưu ý chung cho inline tag Javadoc: dấu ngoặc nhọn có nghĩa cú pháp. Nếu nội dung chứa `{` và `}`, chúng phải cân bằng để công cụ xác định nơi kết thúc thẻ; không thể tùy ý chèn một ngoặc nhọn lẻ vào `{@code ...}`.

## 4. Dùng @snippet inline cho một quy trình ngắn có nhiều dòng

Cú pháp cơ bản:

```java
{@snippet :
    // Các dòng mã để hiển thị.
}
```

Phần thân bắt đầu sau dấu `:` và **dấu xuống dòng tiếp theo**. Trong chú thích Java thông thường `/** ... */`, bạn đặt từng dòng sau ký tự `*`; Javadoc loại bỏ phần trang trí của comment và xử lý thụt lề để hiển thị đoạn mã.

Giả sử có một API chuyển trạng thái nhận vào dạng chuỗi, bỏ khoảng trắng ở hai đầu và chuyển thành chữ hoa theo quy tắc locale ổn định. Cần nói rõ điều kiện `null` và chuỗi trắng. Tệp minh họa `src/main/java/demo/StatusNormalizer.java`:

```java
package demo;

import java.util.Locale;

/** Chuẩn hóa nhãn trạng thái trong ứng dụng. */
public final class StatusNormalizer {
    private StatusNormalizer() {
    }

    /**
     * Chuẩn hóa nhãn trạng thái thành chữ hoa.
     *
     * <p>Ví dụ, {@code " ready "} trở thành {@code "READY"}.
     * Phương thức dùng {@code Locale.ROOT} để tránh phụ thuộc
     * vào locale mặc định của môi trường.
     *
     * <p>Ví dụ đầy đủ:
     * {@snippet :
     * String result = StatusNormalizer.normalize(" ready ");
     * if (!"READY".equals(result)) {
     *     throw new AssertionError(result);
     * }
     * }
     *
     * @param value nhãn trạng thái, không được null hoặc chỉ chứa khoảng trắng
     * @return nhãn đã loại khoảng trắng hai đầu và chuyển thành chữ hoa
     * @throws IllegalArgumentException nếu value là null hoặc chỉ chứa khoảng trắng
     */
    public static String normalize(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("value must not be blank");
        }
        return value.strip().toUpperCase(Locale.ROOT);
    }
}
```

Ở ví dụ này, mỗi thẻ có một vai trò:

- `{@code " ready "}`, `{@code "READY"}`, `{@code Locale.ROOT}` là các **giá trị hoặc định danh ngắn** trong lời giải thích.
- `{@snippet : ... }` trình bày một **chuỗi thao tác nhiều dòng**, bao gồm lời gọi, nhánh kiểm tra và lỗi khi kết quả không đúng.
- `@param`, `@return`, `@throws` mô tả **hợp đồng API**. Snippet minh họa một trường hợp hợp lệ và không thay thế những điều kiện đó.

**Lưu ý:** lệnh `javadoc` sẽ đọc và trình bày snippet, nhưng **không tự biên dịch và chạy nội dung inline**. Bản thân việc trang HTML trông đúng chưa phải là bằng chứng rằng mã ví dụ chạy đúng trên JDK mục tiêu.

### Các quy tắc giúp inline snippet hoạt động ổn định

1. Dấu `:` phải xuất hiện trong thẻ và phần thân bắt đầu ở **dòng kế tiếp**, thay vì viết toàn bộ các câu lệnh sau dấu `:` trên cùng một dòng.
2. Trong chú thích `/** ... */`, **không chèn chuỗi `*/`** vào snippet vì nó kết thúc comment Java, dù chuỗi nằm trong literal hay trong dòng ghi chú.
3. Các dấu `{` và `}` trong thân phải cân bằng. Với đoạn mã chứa cú pháp khó nhúng an toàn vào comment, nên dùng external snippet.
4. Cách Javadoc căn lề không bảo đảm đoạn code có đầy đủ `import`, class hoặc `main`. Nếu cần chạy thật, hãy tổ chức một tệp ví dụ độc lập.

## 5. Khi cần biên dịch và chạy: chuyển sang external snippet

Một ví dụ nhiều dòng thường trở nên quan trọng khi tài liệu hứa một kết quả hoặc mô tả hợp đồng công khai. Khi đó, quản lý ví dụ như **mã nguồn có thể chạy được** giúp phát hiện lỗi sau mỗi lần sửa API.

Một cách tổ chức với package `demo`:

```text
src/main/java/
└── demo/
    ├── StatusNormalizer.java
    └── snippet-files/
        └── NormalizeExamples.java
```

Nội dung `src/main/java/demo/snippet-files/NormalizeExamples.java`:

```java
package demo;

public final class NormalizeExamples {
    private NormalizeExamples() {
    }

    public static void main(String[] args) {
        // @start region=basic
        String result = StatusNormalizer.normalize(" ready "); // @highlight substring="StatusNormalizer.normalize"
        if (!"READY".equals(result)) {
            throw new AssertionError(result);
        }
        // @end region=basic
    }
}
```

Trong Javadoc của phương thức, **thay phần inline snippet** ở mục trước bằng:

```java
/**
 * Chuẩn hóa nhãn trạng thái thành chữ hoa.
 *
 * <p>Ví dụ sử dụng:
 * {@snippet file="NormalizeExamples.java" region=basic}
 *
 * @param value nhãn trạng thái, không được null hoặc chỉ chứa khoảng trắng
 * @return nhãn đã loại khoảng trắng hai đầu và chuyển thành chữ hoa
 * @throws IllegalArgumentException nếu value là null hoặc chỉ chứa khoảng trắng
 */
```

Điểm cần hiểu:

- `file="NormalizeExamples.java"` yêu cầu Javadoc tìm tệp ví dụ tương ứng, mặc định trong thư mục `snippet-files` gắn với package chứa tài liệu. Có thể cấu hình thêm đường dẫn tìm kiếm bằng `--snippet-path`.
- `// @start region=basic` và `// @end region=basic` khoanh vùng cần hiển thị. Người đọc chỉ thấy thân ví dụ, còn lớp và `main` vẫn tồn tại trong tệp để có thể chạy.
- `@highlight` là markup comment của snippet, đánh dấu lời gọi chính trong tài liệu. Comment này không thay đổi hành vi Java.
- Tệp có thể chứa nhiều vùng mang tên khác nhau cho những tình huống độc lập; chỉ chọn vùng thực sự cần xuất hiện ở vị trí hiện tại.

Nếu dùng PowerShell và có JDK 18 trở lên, có thể chạy những lệnh sau từ thư mục gốc của ví dụ:

```powershell
New-Item -ItemType Directory -Force build/classes | Out-Null

javadoc -encoding UTF-8 -d build/docs -sourcepath src/main/java demo

javac -encoding UTF-8 -d build/classes src/main/java/demo/StatusNormalizer.java src/main/java/demo/snippet-files/NormalizeExamples.java

java -cp build/classes demo.NormalizeExamples
```

Khi chương trình kết thúc bình thường, trường hợp `" ready "` cho kết quả mong đợi. Nếu sửa kết quả kỳ vọng trong lớp ví dụ thành `"NOT_READY"`, quá trình biên dịch vẫn có thể thành công, nhưng chương trình sẽ ném `AssertionError`. Hai bước kiểm tra trả lời hai câu hỏi khác nhau:

- **Sinh Javadoc:** thẻ, đường dẫn tệp, vùng trích dẫn và định dạng tài liệu có hợp lệ không?
- **Biên dịch/chạy:** mã ví dụ có sử dụng API đúng và kết quả có phù hợp kỳ vọng không?

Hãy chạy cả hai bước trong quy trình kiểm tra của dự án nếu ví dụ là một phần quan trọng của tài liệu API. Với mã sản phẩm, có thể chuyển các kỳ vọng thành unit test để kiểm tra thêm nhiều đầu vào và trường hợp ngoại lệ.

## 6. Phối hợp @code và @snippet trong cùng một đoạn Javadoc

Một chú thích tốt thường kết hợp hai thẻ để giữ nhịp đọc hợp lý: **lời văn ngắn dùng @code**, **quy trình dùng @snippet**.

```java
/**
 * Chuẩn hóa {@code value} sang nhãn trạng thái.
 *
 * <p>Giá trị {@code null} và chuỗi trắng bị từ chối.
 * Với đầu vào {@code " open "}, kết quả là {@code "OPEN"}.
 *
 * <p>Một cách sử dụng:
 * {@snippet :
 * String status = StatusNormalizer.normalize(" open ");
 * if (!status.equals("OPEN")) {
 *     throw new AssertionError(status);
 * }
 * }
 *
 * @param value nhãn trạng thái đầu vào
 * @return nhãn sau chuẩn hóa
 * @throws IllegalArgumentException nếu value null hoặc chỉ chứa khoảng trắng
 */
```

Thử đọc đoạn tài liệu này như một người mới dùng API: câu đầu cho biết mục đích, câu thứ hai nói về biên đầu vào, câu thứ ba đưa ví dụ cụ thể, rồi đoạn nhiều dòng cho thấy phải gọi và kiểm tra thế nào. Phần mô tả không bị ngắt bởi các khối mã nhỏ không cần thiết.

Một số nhầm lẫn nên tránh:

| Nhầm lẫn | Cách hiểu đúng |
| --- | --- |
| Dùng `{@snippet}` riêng cho mọi tên biến hoặc giá trị. | Tên và giá trị ngắn phù hợp với `{@code}` trong câu. |
| Viết nguyên một quy trình dài trong `{@code}`. | Dùng `{@snippet}` khi cần giữ xuống dòng, cấu trúc và thụt lề. |
| Nghĩ `{@code SomeClass}` tự liên kết đến tài liệu lớp. | Dùng `{@link SomeClass}` nếu cần liên kết. |
| Nghĩ `{@snippet}` tự bảo đảm code biên dịch. | Javadoc xử lý để trình bày; muốn kiểm chứng hành vi phải biên dịch/chạy hoặc viết kiểm thử riêng. |
| Nghĩ đoạn mã được hiển thị chính là toàn bộ hợp đồng API. | Cần nêu điều kiện đầu vào, kết quả, ngoại lệ và các bảo đảm bằng lời cùng thẻ tài liệu thích hợp. |
| Đặt snippet dài trong comment nhưng có dấu kết thúc comment. | Chuyển mã sang external snippet, nơi không có giới hạn này của `/** ... */`. |

### Khi nào không cần tách tệp ngoài?

Với ví dụ rất ngắn, thuần minh họa cách kết hợp 2–3 thao tác và ít khả năng thay đổi, inline snippet thường đơn giản và dễ đọc tại chỗ. Khi ví dụ mô tả **kết quả bắt buộc của hợp đồng**, được dùng lặp lại hoặc có nhiều nhánh xử lý, tệp ngoài cho phép tái sử dụng và kiểm thử độc lập. Không phải mọi snippet đều cần `main`, nhưng tài liệu quan trọng nên có cơ chế để xác minh được ví dụ.

## 7. Bài tập phân loại và thực hành

### Bài tập A: Chọn thẻ thích hợp

Với từng tình huống, chọn `@code`, `@snippet` hoặc `@link`:

1. Giải thích tham số `retryCount` phải lớn hơn `0`.
2. Hiển thị kiểu `Map<String, Integer>` trong lời mô tả.
3. Trình bày cách khởi tạo đối tượng, gọi phương thức và xác nhận kết quả qua `if`.
4. Dẫn người đọc đến tài liệu phương thức `String#isBlank()`.
5. Trình bày một ví dụ nhiều bước cần chạy lại sau mỗi lần cập nhật API.

**Đáp án và lý do:** (1) `@code`; (2) `@code`; (3) `@snippet` inline; (4) `@link`; (5) `@snippet` từ tệp ngoài có thể chạy. Nếu tình huống (3) cần kiểm thử tự động hoặc được dùng ở nhiều nơi, cân nhắc chuyển sang external snippet.

### Bài tập B: Viết tài liệu cho API

Tạo phương thức `StatusNormalizer.normalize(String)` như ví dụ rồi:

1. Viết một câu dùng `{@code ...}` để giải thích chuỗi đầu vào `" pending "` và kết quả `"PENDING"`.
2. Thêm `{@snippet : ... }` để hiển thị tối thiểu ba dòng: gọi API, kiểm tra kết quả, ném `AssertionError` nếu sai.
3. Chuyển ví dụ vào `NormalizeExamples.java`, đặt vùng `region=pending` và tham chiếu bằng `{@snippet file="NormalizeExamples.java" region=pending}`.
4. Chạy Javadoc, biên dịch và chạy ví dụ trên JDK đang sử dụng. Thử thay đổi kỳ vọng để xem bước nào phát hiện sự sai lệch.
5. Bổ sung kiểm tra riêng cho `null`, chuỗi rỗng và chuỗi chỉ có khoảng trắng theo `@throws`.

**Tự kiểm:** Tài liệu dùng `@code` cho các biểu thức ngắn; khối nhiều dòng có thụt lề dễ đọc; hợp đồng về đầu vào/kết quả/ngoại lệ được ghi rõ; external snippet có thể chạy và lỗi khi kỳ vọng không khớp.

## 8. Những điều cần nhớ

- **`@code` phù hợp với những đoạn mã nhỏ nằm trong lời văn.** Nó bảo toàn các ký tự mã nguồn đặc biệt khi hiển thị và không tạo liên kết API.
- **`@snippet` phù hợp với ví dụ có cấu trúc và xuống dòng.** Đây là tính năng của Javadoc từ JDK 18 vẫn được hỗ trợ trên JDK hiện đại.
- **External snippet thuận lợi cho kiểm thử.** Javadoc có thể trích vùng mã, còn quy trình biên dịch/chạy cần được thực hiện riêng.
- **Ví dụ không thay thế hợp đồng API.** Lời mô tả, `@param`, `@return`, `@throws` và các kiểm thử phải đồng nhất với nhau.
- **Chọn thẻ theo thông tin cần truyền đạt:** nêu tên/giá trị → `@code`; trình diễn thao tác → `@snippet`; tạo liên kết đến API → `@link`.

## Tài liệu chính thống

- [OpenJDK — JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle — JavaDoc Documentation Comment Specification for the Standard Doclet, JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/javadoc/doc-comment-spec.html).
- [Oracle — JavaDoc Guide, JDK 27](https://docs.oracle.com/en/java/javase/27/javadoc/index.html).

