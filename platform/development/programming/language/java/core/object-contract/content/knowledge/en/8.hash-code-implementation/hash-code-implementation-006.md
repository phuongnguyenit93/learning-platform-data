# `Objects.hash()` cho nhiều trường và khác biệt với `hashCode()` của một trường

## 1. Ba lời gọi dễ nhầm lẫn

Trong Java, `java.util.Objects` cung cấp hai phương thức tiện ích khác nhau:

```java
public static int Objects.hash(Object... values);
public static int Objects.hashCode(Object o);
```

Các dòng trên chỉ mô tả **chữ ký**, không phải mã nguồn có thể đặt nguyên vào một lớp; tên `Objects.` được viết để chỉ rõ lớp sở hữu phương thức.

Phân biệt chúng với **phương thức thể hiện** `public int hashCode()` kế thừa từ `java.lang.Object`:

| Cách gọi | Ý nghĩa | Khi dữ liệu `null` |
| --- | --- | --- |
| `x.hashCode()` | Dùng thuật toán băm do đối tượng `x` cung cấp | Nếu **receiver `x` là `null`**, ném `NullPointerException` |
| `Objects.hashCode(x)` | Trả `x.hashCode()` nếu `x != null`; trả `0` nếu `x == null` | An toàn với `null` |
| `Objects.hash(x)` | Tính hash tổng hợp của **danh sách đối số** gồm một phần tử `x` | Nếu truyền một `null` như phần tử, kết quả thường khác `Objects.hashCode(null)` |
| `Objects.hash(a, b, c)` | Tạo hash tổng hợp theo thứ tự từ nhiều giá trị | Có thể chứa những phần tử `null` |

**Quy tắc cần nhớ:** `Objects.hash(x)` không có nghĩa là `Objects.hashCode(x)` và cũng không bảo đảm bằng `x.hashCode()`, kể cả khi chỉ có một tham số. `Objects.hash(...)` xử lý một dãy phần tử thông qua `Arrays.hashCode(Object[])`; nó áp dụng thêm bước khởi tạo và kết hợp.

## 2. Vì sao `Objects.hash(x)` khác `x.hashCode()`?

`Objects.hash(Object... values)` nhận tham số biến độ dài (**varargs**). Khi truyền các đối số riêng lẻ, Java đóng gói chúng vào một mảng `Object[]`, sau đó `Objects.hash` tính như `Arrays.hashCode(values)`.

Với dãy phần tử `values` khác `null`, thuật toán `Arrays.hashCode(Object[])` tương đương:

```java
int result = 1;
for (Object element : values) {
    result = 31 * result + (element == null ? 0 : element.hashCode());
}
return result;
```

Đây là **đoạn minh hoạ thuật toán**, không phải chương trình Java độc lập. Các phép tính là số nguyên `int`; nếu xảy ra tràn số thì Java thực hiện theo quy tắc số nguyên 32-bit, điều này được phép trong hash.

Vì `result` bắt đầu bằng `1`, với **một phần tử `x`** được truyền dưới dạng đối số đơn:

```text
Objects.hash(x) = 31 + Objects.hashCode(x)  (tính bằng số nguyên int 32-bit)
```

Đặc biệt, nếu `x` không phải `null`, `Objects.hashCode(x) == x.hashCode()`; còn `Objects.hash(x)` thêm bước kết hợp `31`. Đây là lý do trực tiếp cho việc kết quả khác nhau. Công thức này giả định một phần tử thực sự được truyền vào mảng varargs; có ngoại lệ cú pháp khi đối số là một mảng kiểu tham chiếu hoặc một giá trị `null` không ép kiểu, được giải thích ở phần lưu ý.

Ví dụ với chuỗi `"abc"`:

- `"abc".hashCode()` trả về `96354`.
- `Objects.hashCode("abc")` cũng trả về `96354`.
- `Objects.hash("abc")` trả về `31 + 96354 = 96385`.

Với một phần tử `null` được ghi rõ `(Object) null`, `Objects.hash((Object) null)` trả về `31`, trong khi `Objects.hashCode(null)` trả về `0`; biểu thức `((String) null).hashCode()` lại ném `NullPointerException`.

## 3. `Objects.hash(a, b, ...)` kết hợp nhiều trường

Khi `equals()` của một lớp xác định sự bằng nhau bằng **nhiều trường**, `hashCode()` cần tính toán nhất quán từ những trường đó. Ví dụ một khoá sách được nhận diện bằng `code` và `edition`:

```java
@Override
public int hashCode() {
    return Objects.hash(code, edition);
}
```

Đoạn trên là **phương thức nằm trong một lớp có các trường `code` và `edition`**, chưa phải chương trình độc lập. `Objects.hash(code, edition)` tạo ra một số `int` phụ thuộc cả hai giá trị và thứ tự của chúng. Trình biên dịch đóng hộp (`boxing`) trường nguyên thủy `edition` thành `Integer` khi cần đưa vào mảng varargs.

Ví dụ công thức với `code = "ab"`, `edition = 7`:

```text
"ab".hashCode() = 3105
result ban đầu = 1
result sau code = 31 * 1 + 3105 = 3136
result sau edition = 31 * 3136 + 7 = 97223
Objects.hash("ab", 7) = 97223
```

Không thể chỉ lấy `code.hashCode()` nếu `equals()` còn xét `edition`: hai đối tượng cùng `code` nhưng khác `edition` có thể cho chung hash một cách hợp lệ, tuy nhiên bỏ qua một trường thường làm phân phối hash kém hơn. Điều quan trọng bắt buộc là: **nếu hai đối tượng bằng nhau theo `equals()`, hash của chúng phải bằng nhau**. Chiều đảo không đúng: trùng hash không chứng minh hai đối tượng bằng nhau.

## 4. Ví dụ Java 17+ hoàn chỉnh, có thể chạy

Lưu mã sau vào tệp `ObjectsHashDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;
import java.util.Objects;

public class ObjectsHashDemo {
    static final class BookKey {
        private final String code;
        private final int edition;

        BookKey(String code, int edition) {
            this.code = Objects.requireNonNull(code);
            this.edition = edition;
        }

        @Override
        public boolean equals(Object obj) {
            if (this == obj) return true;
            if (!(obj instanceof BookKey other)) return false;
            return edition == other.edition && code.equals(other.code);
        }

        @Override
        public int hashCode() {
            return Objects.hash(code, edition);
        }
    }

    public static void main(String[] args) {
        String value = "abc";
        System.out.println("instance: " + value.hashCode());
        System.out.println("Objects.hashCode: " + Objects.hashCode(value));
        System.out.println("Objects.hash(one): " + Objects.hash(value));
        System.out.println("Objects.hashCode(null): " + Objects.hashCode(null));
        System.out.println("Objects.hash((Object) null): " + Objects.hash((Object) null));
        System.out.println("Objects.hash(ab, 7): " + Objects.hash("ab", 7));

        BookKey first = new BookKey("ab", 7);
        BookKey equal = new BookKey("ab", 7);
        BookKey different = new BookKey("ab", 8);

        Map<BookKey, String> books = new HashMap<>();
        books.put(first, "available");
        System.out.println("equal keys: " + first.equals(equal));
        System.out.println("equal hashes: " + (first.hashCode() == equal.hashCode()));
        System.out.println("lookup equal: " + books.get(equal));
        System.out.println("lookup different: " + books.get(different));
    }
}
```

Chạy bằng JDK 17 trở lên:

```bash
javac ObjectsHashDemo.java
java ObjectsHashDemo
```

Kết quả:

```text
instance: 96354
Objects.hashCode: 96354
Objects.hash(one): 96385
Objects.hashCode(null): 0
Objects.hash((Object) null): 31
Objects.hash(ab, 7): 97223
equal keys: true
equal hashes: true
lookup equal: available
lookup different: null
```

`BookKey` có `equals()` xét cả `code` và `edition`; `hashCode()` cũng nhận cả hai trường vào `Objects.hash`. Vì vậy hai khoá tương đương có thể tra cứu cùng một mục trong `HashMap`. Tạo khoá mới khác `edition` không tra cứu được mục đã lưu.

Kết quả `lookup different: null` nghĩa là `Map.get` không tìm thấy ánh xạ cho khoá đó trong ví dụ, không phải vì kết quả hash nhất định khác nhau. Dù có va chạm, `HashMap` vẫn kiểm tra tính bằng nhau của khoá để phân biệt.

## 5. So với tự viết công thức `hashCode()`

`Objects.hash(code, edition)` đơn giản và giúp tránh quên trường. Với hai trường ví dụ, có thể viết thủ công thuật toán tương đương:

```java
@Override
public int hashCode() {
    int result = 1;
    result = 31 * result + code.hashCode();
    result = 31 * result + Integer.hashCode(edition);
    return result;
}
```

Đây là **phương thức thay thế** trong lớp `BookKey`, không dán thêm bên cạnh phương thức `hashCode()` cũ. Với các trường `code` khác `null` và `edition` kiểu `int` như đã khai báo, công thức thủ công này cho đúng kết quả của `Objects.hash(code, edition)`.

So sánh ưu nhược điểm:

| Tiêu chí | `Objects.hash(code, edition)` | Viết công thức thủ công |
| --- | --- | --- |
| Độ ngắn gọn | Ngắn, dễ đọc khi nhiều trường | Dài hơn nhưng thấy rõ thuật toán |
| Xử lý `null` ở trường tham chiếu | Các phần tử `null` đóng góp `0` | Phải tự xử lý nếu trường có thể `null` |
| Chi phí bổ sung | Varargs tạo mảng; giá trị nguyên thủy có thể cần boxing | Có thể tránh tạo mảng và boxing |
| Hợp đồng `equals`/`hashCode` | Phải tự chọn đúng trường nhất quán với `equals()` | Cũng phải tự chọn đúng trường nhất quán với `equals()` |

Trong nghiệp vụ thông thường, ưu tiên mã rõ ràng và đúng hợp đồng. Ở đoạn mã được gọi liên tục với yêu cầu hiệu năng cao, cân nhắc đo đạc rồi mới thay `Objects.hash` bằng cách tính thủ công; không khẳng định mọi trường hợp `Objects.hash` đều là nút thắt.

## 6. Những bẫy quan trọng khi dùng varargs, `null` và mảng

### `Objects.hash(null)` có thể mang ý nghĩa bất ngờ

Đối số `null` trần có thể được trình biên dịch diễn giải là **mảng varargs `Object[]` bị `null`**, thay vì một phần tử `null`, kèm cảnh báo biên dịch. Khi đó `Arrays.hashCode((Object[]) null)` trả về `0`. Để biểu đạt rõ một đối số là giá trị `null`, viết `Objects.hash((Object) null)` và nhận `31`. Nếu mục tiêu chỉ là lấy hash của **một** tham chiếu có thể `null`, viết `Objects.hashCode(x)` thường phù hợp hơn.

### Mảng không mặc nhiên được băm theo nội dung

Với một biến `Object[] elements`, lời gọi `Objects.hash(elements)` có thể dùng chính mảng đó như **toàn bộ mảng varargs**, tức băm từng phần tử, không phải tạo một mảng một phần tử chứa `elements`. Trái lại, `Objects.hash((Object) elements)` băm một phần tử có kiểu mảng; phương thức `hashCode()` mặc định của mảng dựa trên danh tính mảng.

Nếu `equals()` so sánh nội dung mảng, hãy ghép đúng cặp `Arrays.equals(a, b)` với `Arrays.hashCode(a)` (hoặc `Arrays.deepEquals`/`Arrays.deepHashCode` phù hợp cho cấu trúc mảng lồng nhau), thay vì tự động dùng `Objects.hash(array)` mà chưa xét cách varargs được truyền.

### `Objects.hash()` không thay thế hợp đồng `equals()`

Ghi đè `equals()` mà không ghi đè `hashCode()` nhất quán có thể làm `HashMap.get` và `HashSet.contains` tìm sai. Ngay cả khi dùng `Objects.hash`, vẫn phải chọn các trường quyết định tính bằng nhau, đồng thời tránh thay đổi chúng sau khi đã dùng đối tượng làm khoá trong cấu trúc băm.

`Objects.hash()` cũng không phải hàm băm mật mã, không bảo đảm duy nhất, không dùng làm mã định danh ổn định giữa các hệ thống. Kết quả `int` có thể âm và có thể va chạm.

## 7. Cách chọn nhanh

- **Một trường tham chiếu chắc chắn không `null`:** `field.hashCode()` là cách trực tiếp, không có bước kết hợp varargs.
- **Một trường có thể `null`:** `Objects.hashCode(field)` trả `0` khi `null` và hash thông thường khi khác `null`.
- **Nhiều trường tham gia `equals()`:** `Objects.hash(fieldA, fieldB, ...)` giúp tạo hàm băm tổng hợp rõ ràng, miễn là nhất quán với `equals()`.
- **Tối ưu mã nóng:** Có thể viết phép kết hợp `31 * result + ...` hoặc dùng `Integer.hashCode`, `Long.hashCode` và các phương thức chuyên biệt sau khi đo hiệu năng.
- **Trường là mảng:** Chọn `Arrays.hashCode`/`Arrays.deepHashCode` đúng với phép so sánh nội dung đã chọn.

## 8. Tự kiểm tra

1. Vì sao `Objects.hash("abc")` là `96385`, trong khi `"abc".hashCode()` là `96354`? — Vì thuật toán của mảng varargs bắt đầu với `result = 1`, sau đó cộng thêm `31 * 1` trước hash phần tử.
2. `Objects.hashCode(null)` và `Objects.hash((Object) null)` có bằng nhau? — Không: lần lượt là `0` và `31`.
3. Nếu `equals()` xét cả `code` và `edition`, hash chỉ dựa trên `code` có tự động vi phạm hợp đồng? — Không tự động: các khoá bằng nhau vẫn cùng `code`. Nhưng bỏ `edition` có thể tăng va chạm; dùng cả hai thường phân phối tốt hơn.
4. Nếu hai khoá trùng kết quả `Objects.hash`, chúng có bắt buộc bằng nhau? — Không. Cấu trúc băm vẫn phải xét `equals()`.

**Ghi nhớ:** `x.hashCode()` lấy hash do một đối tượng cung cấp; `Objects.hashCode(x)` là phiên bản an toàn với tham chiếu `null`; còn `Objects.hash(...)` là phép **kết hợp các phần tử trong dãy đối số**. Chúng khác nhau cả về mục đích lẫn giá trị trả về khi chỉ có một phần tử.