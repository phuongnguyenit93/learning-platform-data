# Cú pháp inline snippet: thuộc tính, dấu hai chấm, nội dung và dấu đóng

## 1. Bối cảnh và mục tiêu

Trong module `JAVA_VERSION_JAVA18`, **JEP 413 – Code Snippets in Java API Documentation** đưa thẻ `{@snippet ...}` vào **Javadoc từ JDK 18**. Đây là tính năng chuẩn đã được duy trì trên các JDK hiện đại, phù hợp để trình bày ví dụ mã nhiều dòng trong tài liệu API. Bài học này tập trung vào **ngữ pháp của inline snippet**: khai báo thẻ, thuộc tính tùy chọn, dấu hai chấm, phần thân và dấu ngoặc nhọn đóng.

Học xong, bạn sẽ có thể:

- Viết đúng cấu trúc `{@snippet [thuộc tính] :`, phần thân nhiều dòng và `}` kết thúc.
- Phân biệt vai trò của `id`, `lang` với nội dung mã trong snippet.
- Hiểu **dòng mới sau dấu `:`** và cách Javadoc xử lý thụt lề.
- Xử lý các lỗi thường gặp liên quan đến dấu ngoặc nhọn, ký tự kết thúc chú thích và thuộc tính.
- Tự dựng tài liệu bằng `javadoc` để kiểm tra thẻ trước khi sử dụng làm tài liệu hợp đồng API.

Đây là cú pháp của **công cụ sinh tài liệu Javadoc**, không phải cấu trúc câu lệnh của Java và không làm thay đổi hành vi chương trình. Ví dụ trình bày tốt vẫn cần nhất quán với hợp đồng API được mô tả bằng `@param`, `@return`, `@throws` và những điều kiện khác.

## 2. Nhìn tổng thể một inline snippet

Dạng chuẩn của inline snippet:

```text
{@snippet [các thuộc tính tùy chọn] :
    nội dung dòng 1
    nội dung dòng 2
}
```

Ví dụ tối thiểu trong một chú thích Javadoc:

```java
/**
 * In lời chào:
 *
 * {@snippet :
 * System.out.println("Hello, Java!");
 * }
 */
public class Greeting {
}
```

Đây là **thẻ inline** nằm trong phần mô tả của chú thích `/** ... */`, dù nội dung có thể kéo dài nhiều dòng. Từ khóa `snippet` theo sau `{@`, còn nội dung sẽ được trình bày thành khối mã trong HTML mà Standard Doclet sinh ra.

| Thành phần | Có bắt buộc trong inline snippet? | Vai trò |
| --- | --- | --- |
| `{@snippet` | Có | Mở một inline tag Javadoc tên `snippet`. |
| `lang="java"`, `id="example-1"` | Không | Bổ sung ngôn ngữ hoặc định danh cho khối mã. |
| `:` | Có | Đánh dấu kết thúc phần khai báo thuộc tính và mở đầu phần thân. |
| Dấu **xuống dòng sau `:`** | Có | Nội dung trích dẫn bắt đầu sau dấu xuống dòng đầu tiên đứng sau dấu `:`. |
| Các dòng mã | Có, để ví dụ có nội dung | Là phần xuất hiện trên trang tài liệu (sau khi xử lý thụt lề/markup). |
| `}` khớp với `{` mở thẻ | Có | Kết thúc inline tag; không phải dấu đóng khối Java. |

Nếu **chỉ tham chiếu tệp ngoài**, Javadoc còn có dạng `{@snippet file="..." }`, không cần `:` và phần thân. Đó là **external snippet**, khác với inline snippet đang được học ở đây. Khi có cả `file` và nội dung, đó là **hybrid snippet**; cú pháp phần inline vẫn tuân các quy tắc nêu trong bài.

Có thể hình dung cấu trúc dưới dạng:

```text
{@snippet lang="java" id="demo" :
 ^^^^^^^ ^^^^^^^^^^^^^^^^^^^^^  ^   ← mở thẻ, thuộc tính, dấu phân cách
     int n = 42;                    ← phần thân sau dấu xuống dòng
     System.out.println(n);
}                                   ← dấu đóng tag
```

Ở đây `42` là giá trị của mã Java; còn `lang`, `id` và `:` trước phần thân thuộc **cú pháp Javadoc**.

## 3. Khai báo thuộc tính đúng cách

Đặc tả Standard Doclet cho phép viết các thuộc tính sau `snippet` dưới dạng `tên=giá_trị`, cách nhau bởi khoảng trắng hoặc dấu xuống dòng.

```java
/**
 * {@snippet lang="java" id="hello-basic" :
 * String greeting = "Hello";
 * System.out.println(greeting);
 * }
 */
```

### 3.1. Thuộc tính `lang`

- `lang` cho biết ngôn ngữ của đoạn mã được hiển thị.
- Với **inline snippet**, giá trị mặc định là **`java`**, vì vậy có thể lược bỏ `lang="java"`.
- Khi minh họa dạng nội dung khác, có thể khai báo rõ ngôn ngữ, ví dụ `lang="properties"`.

Ví dụ hiển thị đoạn cấu hình, không phải mã Java:

```java
/**
 * Cấu hình minh họa:
 *
 * {@snippet lang="properties" :
 * service.name=orders
 * service.timeoutMillis=5000
 * }
 */
```

Chỉ định `lang` hỗ trợ cách tài liệu hiển thị nội dung; nó **không** yêu cầu Javadoc biên dịch hoặc thực thi phần thân theo ngôn ngữ đó.

### 3.2. Thuộc tính `id`

`id` đặt một định danh cho snippet. Standard Doclet sử dụng giá trị này trên phần tử HTML bao ngoài khối mã, giúp xác định hoặc liên kết đến ví dụ ở trang tài liệu.

```java
/**
 * Ví dụ đầu tiên:
 *
 * {@snippet id="order-id-basic" :
 * int orderId = 42;
 * System.out.println(orderId);
 * }
 */
```

Nên chọn `id` ngắn, mang ý nghĩa và **duy nhất trên cùng trang HTML** để tránh xung đột khi tạo liên kết. Không cần `id` nếu không có nhu cầu dẫn đến ví dụ bằng một định danh cụ thể.

### 3.3. Quy tắc cú pháp của thuộc tính

Theo đặc tả, tên thuộc tính là **định danh đơn giản**. Giá trị có thể là một định danh, số nguyên không dấu, hoặc chuỗi đặt trong cặp dấu nháy đơn/nháy kép. Các thuộc tính cách nhau bằng khoảng trắng. Cú pháp còn cho phép thuộc tính hiện diện không kèm `=giá_trị` khi chỉ cần sự hiện diện của nó; tuy nhiên, với `id` và `lang`, hãy cung cấp giá trị rõ ràng.

```text
{@snippet lang=java id="order-demo" :
    // ...
}

{@snippet id='order-demo' lang="java" :
    // ...
}
```

Hai khai báo trên minh họa cách đặt giá trị thuộc tính; trên tài liệu thực tế, chỉ sử dụng một `id` duy nhất cho mỗi snippet.

**Không có quy tắc escape bằng dấu gạch chéo ngược bên trong giá trị thuộc tính.** Nếu phải chứa dấu nháy kép, cân nhắc dùng cặp nháy đơn thay vì cố gắng viết `\"`; với `id`, tốt nhất chọn tên đơn giản tránh ký tự gây nhầm lẫn.

Lưu ý: `file` và `class` dùng để lấy nội dung từ nguồn ngoài; dùng chúng với phần thân inline tạo **hybrid snippet**. Không cần khai báo các thuộc tính ấy khi mã được viết hoàn toàn trong chú thích.

## 4. Dấu hai chấm và dấu xuống dòng: điểm phân cách quan trọng

Trong inline snippet, dấu `:` đứng **sau phần thuộc tính** và **trước phần thân**. Nội dung thực sự được tính từ **sau ký tự xuống dòng đầu tiên tiếp theo dấu `:`** cho đến dấu `}` kết thúc thẻ.

Cách viết rõ ràng và an toàn:

```java
/**
 * {@snippet :
 * int quantity = 2;
 * int doubled = quantity * 2;
 * System.out.println(doubled);
 * }
 */
```

Nếu có thuộc tính:

```java
/**
 * {@snippet lang="java" id="quantity-double" :
 * int quantity = 2;
 * System.out.println(quantity * 2);
 * }
 */
```

**Phân biệt các dấu hai chấm:** dấu `:` trong **phần mở thẻ** là dấu phân cách cú pháp; dấu `:` xuất hiện **trong chuỗi hoặc biểu thức của phần thân** chỉ là nội dung mã.

```java
/**
 * {@snippet :
 * String key = "order:42";
 * System.out.println(key);
 * }
 */
```

Ở ví dụ trên, chỉ dấu `:` sau `{@snippet` mới mở phần thân. Dấu `:` trong `"order:42"` là ký tự bình thường của chuỗi.

### Vì sao nên đặt phần thân ở dòng kế tiếp?

Ví dụ dễ gây nhầm lẫn:

```text
{@snippet : System.out.println("Hello");}
```

Nội dung inline được xác định từ **dấu xuống dòng sau dấu hai chấm**, nên không thể dựa vào dạng trên để hiển thị trọn vẹn câu lệnh cùng dòng. Hãy xuống dòng ngay sau `:`, rồi viết từng câu lệnh trên các dòng riêng.

Ví dụ sai khác:

```text
{@snippet lang="java"
    System.out.println("Hello");
}
```

Dạng này thiếu dấu `:` để bắt đầu thân inline. Cách sửa:

```text
{@snippet lang="java" :
    System.out.println("Hello");
}
```

Các đoạn mang nhãn sai trong phần này dùng để **nhận diện lỗi**, không nên sao chép nguyên vào chú thích Javadoc đang phát hành.

## 5. Phần thân: mã nguồn, thụt lề và dấu sao đầu dòng

Khi viết trong chú thích truyền thống, tác giả thường thêm `*` ở đầu mỗi dòng để dễ đọc:

```java
/**
 * Đoạn mã minh họa:
 *
 * {@snippet :
 * if (args.length > 0) {
 *     System.out.println(args[0]);
 * } else {
 *     System.out.println("no args");
 * }
 * }
 */
```

Công cụ Javadoc bỏ phần trình bày của comment (khoảng trắng và dấu `*` đầu dòng) và xử lý phần thân snippet như một đoạn mã. Người đọc HTML không thấy các dấu `*` của chú thích.

### Thụt lề được xử lý như thế nào?

Phần thân được bỏ khoảng trắng thụt đầu dòng không chủ đích theo quy tắc tương tự `String.stripIndent()`. Điều này giữ quan hệ thụt lề giữa những câu lệnh, nhưng mức thụt lề được loại bỏ **phụ thuộc vào cách sắp xếp toàn bộ khối**, kể cả dòng chứa dấu `}` đóng thẻ.

Ví dụ trình bày một nội dung ở bên trong tài liệu:

```text
{@snippet :
    int amount = 3;
    System.out.println(amount);
}
```

Nếu muốn các dòng hiển thị bắt đầu sát lề trái hơn, có thể điều chỉnh mức thụt lề của dấu `}` đóng và các dòng mã cho thống nhất. Đừng cố chèn nhiều dấu cách để căn hình trong HTML khi chưa kiểm tra kết quả thật.

**Quy trình đáng tin cậy:** sinh Javadoc và xem trang HTML thực tế. Thay đổi mức thụt lề của dòng đóng thẻ khi cần, giữ các dấu ngoặc Java bên trong phần thân cân bằng và có cấu trúc rõ ràng.

### Phần thân không nhất thiết là chương trình Java hoàn chỉnh

Ví dụ sau hợp lệ về **ý đồ trình bày** dù chỉ là hai câu lệnh:

```java
/**
 * {@snippet :
 * var message = "ready";
 * System.out.println(message);
 * }
 */
```

Javadoc có thể hiển thị một **mảnh mã**; nó không yêu cầu đoạn đó có đầy đủ `class`, `main`, `import`. Nhưng nếu ví dụ tuyên bố một kết quả cụ thể của hợp đồng API thì cần kiểm chứng bằng biên dịch/chạy hoặc bài kiểm thử riêng.

## 6. Dấu đóng của inline tag và các cặp ngoặc nhọn

Inline tag bắt đầu bằng `{@snippet` và kết thúc ở dấu `}` **khớp với dấu `{` mở thẻ**. Nếu phần thân chứa Java block, các dấu ngoặc nhọn trong thân phải **cân bằng** để Javadoc không nhận nhầm dấu đóng thẻ.

Ví dụ đúng, có hai dấu `}` đóng với hai vai trò khác nhau:

```java
/**
 * {@snippet :
 * if (true) {
 *     System.out.println("ok");
 * }
 * }
 */
```

Trong đoạn minh họa này, hai dấu `}` cuối có hình thức giống nhau nhưng vai trò khác nhau:

1. Dấu `}` thứ nhất kết thúc thân lệnh `if`.
2. Dấu `}` thứ hai đóng thẻ `{@snippet ...}` của Javadoc.

Nếu Java có các khối lồng nhau, mỗi dấu `{` và `}` trong phần thân cũng phải cân bằng.

### Chú ý: dấu ngoặc nhọn trong chuỗi cũng có thể gây lỗi

Parser của inline tag xử lý dấu ngoặc nhọn theo **cấu trúc thẻ**, không biên dịch cú pháp Java để suy ra rằng dấu ngoặc là ký tự nằm trong string literal. Vì vậy một dấu `}` lẻ trong chuỗi, comment hoặc dữ liệu ví dụ có thể gây kết thúc thẻ sớm.

Ví dụ cần tránh trong inline snippet:

```text
{@snippet :
    String closingBrace = "}";
}
```

Ở đây dấu `}` nằm trong chuỗi Java nhưng không có dấu `{` tương ứng trong phần thân. Cách an toàn là dùng **external snippet** nếu phải thể hiện nguyên vẹn nội dung có ngoặc nhọn không cân bằng. Không nên tự thêm các dấu ngoặc nhọn chỉ để đánh lừa parser vì sẽ làm sai ví dụ cần truyền đạt.

### Không thể chứa chuỗi kết thúc comment

Một inline snippet nằm trong `/** ... */`, nên phần thân **không được chứa cặp ký tự `*/`**, kể cả khi cặp đó nằm trong một chuỗi, biểu thức chính quy hoặc chú thích mã. Java sẽ xem đó là kết thúc comment của mã nguồn. Ví dụ một đoạn Java chứa block comment `/* ... */` sẽ va chạm với ràng buộc này.

Với trường hợp cần giữ nguyên những ký tự ấy, đưa ví dụ sang **external snippet** (`{@snippet file="SomeExamples.java" region=...}`). External snippet nằm ngoài chú thích, vì vậy không chịu giới hạn này của phần thân inline.

Một lưu ý khác đối với mã Java là **Unicode escape** được xử lý trong bước phân tích mã nguồn trước khi công cụ phân tích chú thích. Khi minh họa văn bản có chuỗi backslash–`u`, nên kiểm tra kỹ kết quả hoặc dùng tệp ngoài để thể hiện đúng dữ liệu mong muốn.

## 7. Ví dụ thực tế: viết Javadoc cho API định dạng mã sự kiện

Bây giờ ghép các thành phần thành một chú thích có **thuộc tính**, **dấu `:`**, **phần thân nhiều dòng**, **Java block cân bằng** và **dấu đóng tag riêng**.

Giả sử có API `EventCode.format(String category, int id)` với hợp đồng:

- `category` không được `null`, rỗng hoặc chỉ chứa khoảng trắng.
- `id` không được âm.
- Phương thức trả về `category`, dấu hai chấm và dạng thập phân của `id`; không sửa trạng thái bên ngoài.

Tệp `src/main/java/example/EventCode.java`:

```java
package example;

import java.util.Objects;

/** Định dạng mã sự kiện dùng trong ứng dụng. */
public final class EventCode {
    private EventCode() {
    }

    /**
     * Tạo mã có dạng {@code category:id}.
     *
     * <p>Ví dụ với category {@code "order"} và id {@code 42}:
     *
     * {@snippet id="event-code-basic" lang="java" :
     * String code = EventCode.format("order", 42);
     * if (!"order:42".equals(code)) {
     *     throw new AssertionError(code);
     * }
     * }
     *
     * @param category nhãn danh mục, không được null hoặc chỉ chứa khoảng trắng
     * @param id số nguyên không âm
     * @return mã có dạng {@code category:id}
     * @throws NullPointerException nếu category là null
     * @throws IllegalArgumentException nếu category rỗng, chỉ chứa khoảng trắng
     *         hoặc id âm
     */
    public static String format(String category, int id) {
        Objects.requireNonNull(category, "category");
        if (category.isBlank() || id < 0) {
            throw new IllegalArgumentException("category blank or id negative");
        }
        return category + ":" + id;
    }
}
```

Cách đọc cú pháp đoạn mẫu:

| Vị trí | Phần mã tương ứng | Ý nghĩa |
| --- | --- | --- |
| Mở thẻ | `{@snippet` | Báo cho Javadoc biết đây là snippet. |
| Thuộc tính | `id="event-code-basic" lang="java"` | Định danh khối và ngôn ngữ Java. |
| Phân cách | `:` cuối dòng mở thẻ | Phần thân bắt đầu từ dòng ngay sau đó. |
| Nội dung | `String code = ...` và `if (...) { ... }` | Minh họa lời gọi API và kiểm tra kết quả. |
| Dấu đóng Java | `}` sau `throw` | Kết thúc nhánh `if`. |
| Dấu đóng thẻ | `}` ở dòng kế tiếp | Kết thúc `{@snippet ...}`. |

Đoạn Javadoc trên mô tả một **hợp đồng có thể đối chiếu**: lời văn nói rõ các điều kiện lỗi; snippet minh họa một đường đi hợp lệ. Dấu `:` xuất hiện trong `"order:42"` chỉ là một phần kết quả, không thay đổi phân tích cú pháp của thẻ.

Có thể tạo tài liệu (JDK 18 trở lên, ví dụ chạy từ gốc thư mục có `src`):

```sh
javadoc -encoding UTF-8 -d build/docs src/main/java/example/EventCode.java
```

Mở tài liệu được sinh ra để kiểm tra mã có xuống dòng, thụt lề và định dạng đúng. Sau khi thay đổi thân phương thức, nên **kiểm thử Java riêng** để bảo đảm kết quả thực tế vẫn khớp với ví dụ. `javadoc` **không biên dịch hoặc chạy mã nằm trong phần thân inline snippet**.

## 8. Nhận diện lỗi cú pháp trước khi xuất bản

| Hiện tượng | Nguyên nhân có thể | Cách sửa |
| --- | --- | --- |
| Javadoc báo lỗi cú pháp thẻ inline. | Thiếu `:` hoặc viết sai phần mở `{@snippet`. | Viết `{@snippet [thuộc tính] :` rồi xuống dòng trước mã. |
| Ví dụ rỗng hoặc không hiển thị như mong đợi. | Đặt nội dung trên cùng dòng với `:`, hoặc đóng thẻ sai vị trí. | Đặt toàn bộ mã **sau dòng mới** và kiểm tra dấu `}` cuối. |
| Mã bị cắt hoặc chú thích kết thúc sớm. | Dấu `}` không cân bằng trong phần thân hoặc có chuỗi `*/`. | Kiểm tra các ký tự đặc biệt; chuyển sang external snippet nếu cần. |
| Liên kết đến snippet không dẫn đến đúng nơi. | Đặt `id` trùng trên cùng trang hoặc gõ sai định danh. | Dùng `id` rõ nghĩa và không trùng. |
| Thuộc tính không được phân tích như dự định. | Sai dấu nháy, có khoảng trắng trong giá trị không đặt trong nháy, hoặc dùng escape không được hỗ trợ. | Dùng giá trị đơn giản, nháy đơn/đôi đúng cặp, không phụ thuộc `\"`. |
| Mã có thụt lề lạ trong HTML. | Khoảng trắng đầu dòng hoặc vị trí `}` đóng thẻ ảnh hưởng xử lý thụt lề. | Chỉnh lại căn lề và kiểm tra HTML đã sinh. |
| Javadoc sinh thành công nhưng ví dụ không chạy được. | Snippet inline chỉ dùng để trình bày, không được JavaDoc kiểm thử hành vi. | Tạo kiểm thử riêng hoặc chuyển mã sang external snippet có thể biên dịch. |

**Không cần** tạo thêm các field như `file`, `region` hoặc markup comment khi mục tiêu chỉ là trình bày một ví dụ inline dễ đọc. Hãy nắm chắc phần mở, dấu `:`, phần thân và dấu đóng trước khi dùng các chức năng nâng cao.

## 9. Bài tập thực hành

### Bài tập 1: Hoàn chỉnh đoạn thẻ

Cho nội dung chưa hợp lệ sau:

```text
{@snippet lang="java" id="square"
    int value = 6;
    int square = value * value;
    System.out.println(square);
}
```

Hãy sửa lại để Javadoc hiển thị ba câu lệnh. **Đáp án:** thêm dấu `:` ngay sau `id="square"` và đặt mã ở dòng kế tiếp. Dấu `}` cuối giữ vai trò đóng tag.

### Bài tập 2: Giải thích từng dấu ngoặc nhọn

Xét đoạn:

```java
/**
 * {@snippet id="check-positive" :
 * int score = 7;
 * if (score > 0) {
 *     System.out.println("positive");
 * }
 * }
 */
```

Hãy chỉ ra ba dấu liên quan: `{` mở khối `if`, `}` đóng `if` và `}` đóng snippet; dấu `{` đầu `{@snippet` là dấu mở thẻ. Sau đó thử bỏ `}` đóng khối `if` và dự đoán Javadoc sẽ phân tích sai ở đâu.

### Bài tập 3: Dùng snippet để minh họa hợp đồng API

Viết một API `OrderToken.create(String prefix, int sequence)` với quy tắc từ chối `prefix` trắng và `sequence` âm; giá trị trả về dạng `prefix:sequence`. Trong Javadoc:

1. Thêm `{@snippet id="token-basic" lang="java" :` ở một dòng riêng.
2. Viết lời gọi `OrderToken.create("invoice", 3)` và kiểm tra chuỗi `"invoice:3"` bằng `if` rồi `throw new AssertionError(...)`.
3. Đóng `if` bằng `}` và đóng snippet bằng một `}` **khác**.
4. Viết `@param`, `@return` và `@throws` khớp với cách cài đặt.
5. Chạy `javadoc` để kiểm tra thẻ; kiểm thử ví dụ trên JDK sử dụng trong dự án.

**Tự kiểm:** thẻ mở đúng; thuộc tính tách bằng khoảng trắng; có dấu `:`; thân bắt đầu sau xuống dòng; không có `*/` trong phần thân; ngoặc nhọn cân bằng; nội dung hiển thị không lẫn dấu `*`; mô tả hợp đồng API không trái ví dụ.

## 10. Ghi nhớ

- **Cấu trúc cốt lõi:** `{@snippet [thuộc tính] :` → dòng mới → phần thân → `}` khớp với dấu mở.
- **`id` và `lang` là tùy chọn**; inline snippet mặc định dùng `java` nếu không ghi `lang`.
- **Thân được lấy sau dòng mới theo sau `:`** và được điều chỉnh thụt lề theo quy tắc tương tự `String.stripIndent()`.
- **Ngoặc nhọn trong thân phải cân bằng** và không chứa `*/` khi nằm trong chú thích truyền thống.
- **Javadoc xử lý cách trình bày**, không tự chạy ví dụ; cần kiểm thử riêng để xác nhận hành vi thực tế của API.

## Tài liệu chính thống

- [OpenJDK – JEP 413: Code Snippets in Java API Documentation](https://openjdk.org/jeps/413).
- [Oracle – JDK 26 Javadoc Snippets Guide](https://docs.oracle.com/en/java/javase/26/javadoc/snippets.html).
- [Oracle – JDK 26 Documentation Comment Specification, mục snippet](https://docs.oracle.com/en/java/javase/26/docs/specs/javadoc/doc-comment-spec.html).

