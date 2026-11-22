# Tạo `String` từ `StringBuilder` hoặc `StringBuffer` trong Java

`StringBuilder` và `StringBuffer` dùng để xây dựng, nối hoặc chỉnh sửa chuỗi nhiều lần. Khi hoàn tất, chương trình thường cần một giá trị `String` để trả về từ phương thức, truyền cho API nhận `String`, lưu trong đối tượng dữ liệu hoặc hiển thị. Cách chuyển đổi phổ biến và rõ nghĩa nhất là gọi `toString()`.

## 1. Ba kiểu dữ liệu liên quan như thế nào?

- `String` là kiểu chuỗi **bất biến** (immutable): sau khi tạo, nội dung của một `String` không bị sửa tại chỗ. Những thao tác như `concat()` hoặc `replace()` tạo ra kết quả `String` khác khi cần.
- `StringBuilder` là vùng đệm ký tự **có thể thay đổi** (mutable). Các thao tác `append()`, `insert()`, `delete()`, `replace()` và `reverse()` thay đổi vùng đệm. Kiểu này không được thiết kế để nhiều luồng cùng thay đổi mà không có đồng bộ bên ngoài.
- `StringBuffer` cũng có thể thay đổi nội dung, nhưng nhiều phương thức công khai được đồng bộ hóa (`synchronized`). Nó hữu ích khi cần đặc tính đồng bộ hóa đó; tuy nhiên một chuỗi gồm nhiều lời gọi phương thức vẫn cần cơ chế bảo vệ phù hợp nếu phải thực hiện như một thao tác nguyên tử.

Cả hai lớp vùng đệm đều triển khai `CharSequence`, song `CharSequence` không phải là `String`. Một biến hoặc API yêu cầu đúng kiểu `String` cần được cung cấp giá trị chuyển đổi.

## 2. Chuyển đổi bằng `toString()`

Cú pháp chuẩn:

```java
StringBuilder builder = new StringBuilder("Hello");
builder.append(" Java");
String text = builder.toString();

StringBuffer buffer = new StringBuffer("Hello");
buffer.append(" Java");
String otherText = buffer.toString();
```

`toString()` trả về nội dung hiện tại dưới dạng `String`. Lời gọi này **không xóa, không đóng và không thay đổi** vùng đệm nguồn; có thể tiếp tục dùng `builder` hoặc `buffer` sau đó.

### Ví dụ chạy được: chụp nội dung `StringBuilder`

Lưu vào tệp `Main.java`:

```java
public class Main {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder("Hello");
        builder.append(" Java");

        String before = builder.toString();
        builder.append("!");

        String after = builder.toString();

        System.out.println("before = " + before);
        System.out.println("after = " + after);
        System.out.println("builder = " + builder);
    }
}
```

Biên dịch và chạy với JDK 17 trở lên:

```bash
javac Main.java
java Main
```

Kết quả:

```text
before = Hello Java
after = Hello Java!
builder = Hello Java!
```

`before` là một **ảnh chụp nội dung tại thời điểm chuyển đổi**. Khi `builder` được nối thêm dấu `!`, `before` vẫn giữ giá trị cũ; một lần gọi `toString()` tiếp theo lấy nội dung mới. Đây là khác biệt quan trọng giữa giá trị `String` và vùng đệm có thể thay đổi.

### Ví dụ chạy được: `StringBuffer`

Lưu vào tệp `BufferExample.java`:

```java
public class BufferExample {
    public static void main(String[] args) {
        StringBuffer buffer = new StringBuffer("A");
        buffer.append("B");

        String snapshot = buffer.toString();
        buffer.replace(0, 1, "X");

        System.out.println("snapshot = " + snapshot);
        System.out.println("buffer = " + buffer);
    }
}
```

Chạy bằng `javac BufferExample.java` rồi `java BufferExample`. Đầu ra:

```text
snapshot = AB
buffer = XB
```

Mặc dù `StringBuffer` có các phương thức đồng bộ, kết quả trả về vẫn là một `String` bất biến, không liên kết sống với nội dung của `buffer`.

## 3. Các cách chuyển đổi khác

Java cũng cung cấp constructor nhận trực tiếp đối tượng vùng đệm:

```java
StringBuilder builder = new StringBuilder("Java");
String fromBuilder = new String(builder);

StringBuffer buffer = new StringBuffer("Core");
String fromBuffer = new String(buffer);
```

Hai constructor `String(StringBuilder)` và `String(StringBuffer)` tạo `String` từ nội dung hiện tại của đối tượng nguồn. Với mục đích chuyển đổi thông thường, `toString()` dễ đọc hơn và là lựa chọn mặc định.

Có thể dùng `String.valueOf(Object)`:

```java
StringBuilder builder = new StringBuilder("Java");
String text = String.valueOf(builder); // "Java"
```

Với tham chiếu **không null**, cách gọi trên sử dụng biểu diễn `toString()` của đối tượng. Điểm khác là `String.valueOf(Object)` với tham chiếu `null` trả về chuỗi ký tự `"null"`, còn gọi `toString()` trên tham chiếu `null` gây `NullPointerException`:

```java
StringBuilder builder = null;
String safeRepresentation = String.valueOf(builder); // "null"
// String text = builder.toString();                 // NullPointerException
```

Đừng nhầm chuỗi ký tự `"null"` với giá trị tham chiếu `null`. Nếu quy ước nghiệp vụ muốn chuỗi rỗng, cần xử lý rõ:

```java
StringBuilder builder = null;
String text = builder == null ? "" : builder.toString();
```

| Cách viết | Kết quả | Nên dùng khi |
| --- | --- | --- |
| `builder.toString()` / `buffer.toString()` | `String` chứa nội dung hiện tại | Chuyển đổi thông thường, nguồn được đảm bảo không `null` |
| `new String(builder)` / `new String(buffer)` | `String` từ nội dung vùng đệm | Cần biểu đạt rõ ý định tạo bằng constructor |
| `String.valueOf(builder)` | Chuỗi từ `toString()`; nguồn `null` thành `"null"` | Muốn chuyển đối tượng thành biểu diễn chuỗi và chấp nhận quy tắc `null` này |

Tránh `new String(builder.toString())`: phần bọc constructor thường không mang lại ý nghĩa bổ sung so với `builder.toString()` và có thể tạo thêm công việc không cần thiết.

## 4. Thời điểm chuyển đổi và tính bất biến

Quy trình điển hình:

1. Khởi tạo `StringBuilder` hoặc `StringBuffer`.
2. Thêm, chèn hoặc sửa nội dung bằng các thao tác của vùng đệm.
3. Gọi `toString()` **sau khi đã hoàn thành** nội dung cần dùng.
4. Lưu, truyền hoặc trả về `String` kết quả.

Nếu tiếp tục sửa vùng đệm sau bước 3, kết quả đã tạo không tự cập nhật. Muốn lấy phiên bản mới, phải gọi `toString()` lại.

Không so sánh nội dung hai kết quả bằng `==`. Toán tử này so sánh tham chiếu của hai đối tượng; dùng `equals()` để so sánh nội dung:

```java
StringBuilder builder = new StringBuilder("abc");
String a = builder.toString();
String b = new String(builder);

System.out.println(a.equals(b)); // true
```

Ví dụ trên cố ý chỉ kiểm tra nội dung. Không nên dựa vào việc hai lần chuyển đổi trả về cùng hay khác đối tượng theo toán tử `==`; điều cần bảo đảm trong ứng dụng là giá trị chuỗi.

Chuyển đổi thường cần tạo giá trị `String` tương ứng với lượng nội dung trong vùng đệm, nên không cần gọi `toString()` lặp lại sau **mỗi** lần `append()` nếu chỉ dùng kết quả cuối cùng. Có thể tái sử dụng một biến `String` khi cần nhiều chỗ dùng cùng một ảnh chụp.

## 5. Ví dụ thực tế: xây dựng một dòng báo cáo

Ta ghép nhiều phần bằng `StringBuilder`, rồi trả về `String` cho mã gọi:

```java
public class ReportExample {
    static String buildSummary(String[] names) {
        StringBuilder result = new StringBuilder();

        for (int i = 0; i < names.length; i++) {
            if (i > 0) {
                result.append(", ");
            }
            result.append(names[i]);
        }

        return result.toString();
    }

    public static void main(String[] args) {
        String summary = buildSummary(new String[] {"Lan", "Minh", "An"});
        System.out.println(summary);
    }
}
```

Lưu vào `ReportExample.java`, chạy `javac ReportExample.java` và `java ReportExample`. Đầu ra:

```text
Lan, Minh, An
```

Trong `buildSummary()`, vùng đệm là chi tiết triển khai nội bộ; phương thức trả về kiểu `String` bất biến theo hợp đồng đã khai báo. Lời gọi `toString()` cuối phương thức giúp tránh lấy bản trung gian khi vòng lặp chưa hoàn tất. Với nhu cầu nối danh sách đơn giản như ví dụ, `String.join(", ", names)` cũng là một lựa chọn rõ ràng; không cần tự dùng `StringBuilder` trong mọi trường hợp.

Nếu cần xây dựng nội dung trong mã dùng `StringBuffer`, bước trả về cũng tương tự:

```java
static String finish(StringBuffer buffer) {
    return buffer.toString();
}
```

Đoạn `finish` là một **phương thức minh họa**, cần đặt bên trong lớp Java phù hợp; nó không phải chương trình chạy độc lập.

## 6. Lưu ý khi có nhiều luồng

Với `StringBuilder`, không đọc/sửa cùng một đối tượng từ nhiều luồng mà thiếu đồng bộ phù hợp. Việc gọi `toString()` trong khi luồng khác đang thay đổi `StringBuilder` không tự tạo ra một ảnh chụp an toàn và nhất quán.

Với `StringBuffer`, các phương thức như `append()` và `toString()` được đồng bộ trên đối tượng. Một lần `toString()` có thể lấy nội dung nhất quán theo sự đồng bộ đó, nhưng **cả chuỗi hành động nhiều bước** (ví dụ: kiểm tra độ dài, sau đó thêm dữ liệu, rồi lấy chuỗi) không mặc nhiên trở thành một giao dịch nguyên tử giữa các luồng. Nếu phải giữ các bước đi cùng nhau, cần thiết kế đồng bộ cho toàn bộ thao tác.

Không chọn `StringBuffer` chỉ vì kết quả phải là `String`: cả hai lớp đều chuyển đổi được. Trong đoạn mã chỉ dùng một luồng, `StringBuilder` thường là lựa chọn thích hợp.

## 7. Lỗi thường gặp và cách xử lý

**1. Nhầm kết quả với vùng đệm đang thay đổi.** Sau `String snapshot = builder.toString();`, sửa `builder` không sửa `snapshot`. Hãy gọi `toString()` mới nếu muốn nội dung cập nhật.

**2. Gọi `toString()` trên đối tượng `null`.** Lỗi `NullPointerException` xuất hiện trước khi tạo `String`. Kiểm tra `null` hoặc dùng quy ước `String.valueOf()` khi thực sự muốn giá trị `"null"`.

**3. Gọi chuyển đổi quá sớm hoặc quá nhiều.** Nếu API cần bản hoàn chỉnh, nối/sửa xong mới gọi. Khi cần snapshot tại nhiều mốc có chủ đích, mỗi lần gọi đều hợp lý.

**4. Dùng `==` để kiểm tra kết quả.** Dùng `equals()` cho so sánh nội dung, `equalsIgnoreCase()` chỉ khi muốn so sánh bỏ qua hoa/thường.

**5. Tưởng `StringBuffer` khiến mọi chuỗi thao tác nhiều bước tự an toàn.** Đồng bộ từng phương thức không thay thế được thiết kế đồng bộ của cả quy trình.

**6. Tạo `new String(builder.toString())` như một bước bắt buộc.** Không cần bọc thêm `new String(...)` để nhận một `String`; `toString()` đã trả về đúng kiểu.

## 8. Tự kiểm tra

**Câu 1.** Nếu `StringBuilder b = new StringBuilder("A"); String s = b.toString(); b.append("B");`, giá trị của `s` và `b.toString()` là gì?

**Đáp án:** `s` vẫn là `"A"`, còn `b.toString()` là `"AB"`, vì `s` là giá trị bất biến được tạo trước khi nối thêm.

**Câu 2.** Có cần dùng `new String(buffer)` thì mới chuyển được `StringBuffer` sang `String` không?

**Đáp án:** Không. `buffer.toString()` là cách trực tiếp và thường được ưu tiên; constructor `new String(buffer)` cũng hợp lệ.

**Câu 3.** Vì sao có thể chọn `StringBuffer` trong mã nhiều luồng, và cần lưu ý gì?

**Đáp án:** Các phương thức của `StringBuffer` có đồng bộ hóa, bao gồm `toString()`. Tuy nhiên tính nguyên tử của cả một quy trình gồm nhiều lần gọi phương thức vẫn cần được kiểm soát riêng.

**Ghi nhớ:** Dùng `toString()` để nhận `String` từ `StringBuilder` hoặc `StringBuffer`. Giá trị tạo ra phản ánh nội dung tại thời điểm chuyển đổi và không thay đổi theo các lần sửa vùng đệm về sau.
