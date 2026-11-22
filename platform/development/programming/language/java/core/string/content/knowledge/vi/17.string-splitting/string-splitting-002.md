# `String.split(regex, limit)`: dương, bằng 0 và âm

Tham số `limit` trả lời hai câu hỏi: **số phần kết quả được giới hạn ra sao** và **các phần rỗng cuối có bị bỏ hay không**. Ví dụ, dấu `=` đầu tiên có thể ngăn cách key với value chứa thêm nhiều dấu `=`; dữ liệu bảng lại cần bảo toàn các trường rỗng cuối.

## 1. Ba chế độ tách

| `limit` | Quy tắc | Phần rỗng cuối |
| --- | --- | --- |
| Số dương `n` | Áp dụng regex tối đa `n-1` lần, kết quả **không quá `n` phần tử** | Giữ nếu đã tạo ra |
| `0` | Tách tối đa | Bỏ **toàn bộ** phần tử rỗng ở cuối |
| Số âm (thường `-1`) | Tách tối đa | Giữ phần tử rỗng ở cuối |

`split(regex)` đồng nghĩa `split(regex, 0)`. Giá trị âm `-1` và `-5` cùng quy tắc; số âm không có nghĩa tách ngược từ phải sang trái. `limit=1` không thực hiện lần tách nào và trả lại toàn chuỗi trong một phần tử.

Xét `String s = "a:b::";`:

| Lời gọi | Nội dung kết quả | `length` |
| --- | --- | --- |
| `s.split(":", 1)` | `["a:b::"]` | 1 |
| `s.split(":", 2)` | `["a", "b::"]` | 2 |
| `s.split(":", 3)` | `["a", "b", ":"]` | 3 |
| `s.split(":", 4)` | `["a", "b", "", ""]` | 4 |
| `s.split(":", 10)` | `["a", "b", "", ""]` | 4 |
| `s.split(":", 0)` | `["a", "b"]` | 2 |
| `s.split(":", -1)` | `["a", "b", "", ""]` | 4 |

Với `limit=3`, chỉ có hai lần cắt. Phần cuối `":"` là **phần dư chưa bị tách**, không phải một ký tự dấu phân cách bị bỏ quên. `limit=10` chỉ đặt mức trần, không tự chèn thêm sáu phần trống.

## 2. Chương trình Java 17+ kiểm chứng mọi nhánh

Lưu `SplitLimitDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class SplitLimitDemo {
    static void show(String label, String[] parts) {
        String visible = Arrays.stream(parts)
                .map(s -> "\"" + s + "\"")
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " len=" + parts.length + " " + visible);
    }

    public static void main(String[] args) {
        String text = "a:b::";
        show("limit=1", text.split(":", 1));
        show("limit=2", text.split(":", 2));
        show("limit=3", text.split(":", 3));
        show("limit=4", text.split(":", 4));
        show("limit=0", text.split(":", 0));
        show("limit=-1", text.split(":", -1));

        show("empty", "".split(":", 0));
        show("delimiter only", ":".split(":", 0));
        show("key/value", "host=a=b".split("=", 2));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SplitLimitDemo.java
java SplitLimitDemo
```

```text
limit=1 len=1 ["a:b::"]
limit=2 len=2 ["a", "b::"]
limit=3 len=3 ["a", "b", ":"]
limit=4 len=4 ["a", "b", "", ""]
limit=0 len=2 ["a", "b"]
limit=-1 len=4 ["a", "b", "", ""]
empty len=1 [""]
delimiter only len=0 []
key/value len=2 ["host", "a=b"]
```

Hàm `show` cố ý in `length` và bọc token trong dấu nháy. `Arrays.toString` mặc định khó phân biệt mảng không phần tử với mảng chứa một chuỗi rỗng.

Hai trường hợp biên: `"".split(":", 0)` có **một** phần tử `""` vì regex không tìm thấy dấu `:` nào; `":".split(":", 0)` tạo các đoạn đều rỗng và chúng bị xóa hết ở cuối, nên có **0** phần tử.

## 3. Ứng dụng: chỉ tách key/value một lần

`limit=2` thường là lựa chọn đúng khi dấu phân cách chỉ có ý nghĩa ở lần xuất hiện đầu tiên:

```java
String line = "endpoint=https://example.org?q=a=b";
String[] pair = line.split("=", 2);
// ["endpoint", "https://example.org?q=a=b"]
```

Nếu dùng `split("=")`, value bị chia vụn theo những dấu `=` bên trong chính nó. Với `"enabled="`, `split("=", 2)` trả `["enabled", ""]`, còn mặc định chỉ `["enabled"]` vì bỏ trường rỗng cuối. Kiểm tra `pair.length == 2` trước khi truy cập `pair[1]`: đầu vào không có dấu `=` cho mảng chỉ một phần tử.

`limit=2` cũng áp dụng cho cấu hình `"level:WARN:retry-later"` khi dấu `:` đầu tiên phân tách khóa và toàn bộ thông điệp còn lại.

## 4. Giữ phần rỗng cuối và các giới hạn của `limit`

`"A,B,,".split(",")` chỉ cho `["A", "B"]`; `split(",", -1)` trả đủ `["A", "B", "", ""]`. Dù ở `limit=0`, phần rỗng **giữa** `"A,,B"` và phần rỗng **đầu** `",A,B"` vẫn được giữ nếu delimiter khớp độ dài dương. Bài về trường rỗng cuối dùng các trường hợp này để kiểm tra schema và khôi phục dữ liệu.

Cần phân biệt thêm:

- Regex khớp **độ rộng 0** ngay vị trí đầu chuỗi không tạo phần tử rỗng đầu; quy tắc này khác chuyện bỏ rỗng **cuối** theo `limit=0`.
- `limit` không biến regex thành dấu phân cách literal. Dấu chấm cần `"\\."` hoặc `Pattern.quote(".")`.
- `stream.limit(n)` sau `Pattern.splitAsStream` chỉ lấy tối đa `n` token, trong khi `split(input, n)` đưa **toàn phần dư** vào phần tử cuối.
- Không giá trị `limit` nào thay parser CSV có dấu nháy.

## 5. Tự kiểm tra

1. `"user=hello=world".split("=", 2)` giữ dấu `=` thứ hai không?
2. `"x:y::".split(":", 3)` có phần tử thứ ba nào?
3. `"x:y::".split(":", 0)` và `split(":", -1)` khác nhau thế nào?
4. `"a:b".split(":", 10)` có đúng mười phần không?
5. `"a,b".split(":", 0)` có trả mảng rỗng khi không có dấu `:` không?

**Đáp án:** (1) Có, trong `"hello=world"`. (2) `":"`. (3) Mảng hai phần so với mảng bốn phần có hai chuỗi rỗng cuối. (4) Không, hai phần. (5) Không, một phần tử `"a,b"`.

**Ghi nhớ:** `limit>0` là mức trần **số phần**, `0` xóa chuỗi rỗng cuối, còn số âm giữ chúng.