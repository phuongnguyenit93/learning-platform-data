# Dấu phân cách ở đầu, liên tiếp và ở cuối

Khi xem dấu phân cách là **ranh giới giữa các trường**, vị trí của nó quyết định có phần tử rỗng hay không. `",a,b"` có phần trống ở đầu; `"a,,b"` có phần trống ở giữa; `"a,b,"` có phần trống cuối nếu chọn giữ lại.

## 1. Quan sát mọi vị trí

| Đầu vào | `split(",")` | `split(",", -1)` |
| --- | --- | --- |
| `",a,b"` | `["", "a", "b"]` | `["", "a", "b"]` |
| `"a,,b"` | `["a", "", "b"]` | `["a", "", "b"]` |
| `"a,b,,"` | `["a", "b"]` | `["a", "b", "", ""]` |
| `",,a,,"` | `["", "", "a"]` | `["", "", "a", "", ""]` |
| `",,"` | Mảng độ dài 0 | Ba phần `""` |
| `""` | Một phần `""` | Một phần `""` |

**Đầu chuỗi:** regex khớp đoạn có độ dài **dương** ngay tại vị trí 0 sinh phần tử rỗng trước nó. Regex có lần khớp **zero-width** ở vị trí 0 không sinh phần rỗng đầu; bài tiếp theo giải thích tường minh với lookahead/anchor.

**Giữa chuỗi:** mỗi dấu phẩy khớp riêng, nên hai dấu liền nhau tạo một khoảng trống `""` ở giữa. Việc xóa phần tử rỗng ở giữa có thể làm lệch cột dữ liệu.

**Cuối chuỗi:** mặc định `limit=0` bỏ mọi phần tử rỗng cuối; `limit=-1` giữ lại. Quy tắc rỗng **ở cuối** khác quy tắc khớp zero-width **ở đầu**.

## 2. Mỗi dấu riêng hay gộp cả cụm?

Để thấy sự khác nhau giữa `","` và `",+"`, lưu `SplitBoundariesDemo.java`:

```java
import java.util.Arrays;
import java.util.stream.Collectors;

public class SplitBoundariesDemo {
    private static void show(String label, String[] parts) {
        String visible = Arrays.stream(parts)
                .map(s -> "'" + s + "'")
                .collect(Collectors.joining(", ", "[", "]"));
        System.out.println(label + " n=" + parts.length + " " + visible);
    }

    public static void main(String[] args) {
        String input = ",a,,b,";
        show("individual", input.split(",", -1));
        show("default", input.split(","));
        show("grouped", input.split(",+", -1));
        show("first only", input.split(",", 2));
        show("zero width", "abc".split("(?=a)", -1));
    }
}
```

```bash
javac --release 17 -encoding UTF-8 SplitBoundariesDemo.java
java SplitBoundariesDemo
```

```text
individual n=5 ['', 'a', '', 'b', '']
default n=4 ['', 'a', '', 'b']
grouped n=4 ['', 'a', 'b', '']
first only n=2 ['', 'a,,b,']
zero width n=1 ['abc']
```

`","` xem **mỗi** dấu phẩy là một dấu phân cách; `",+"` xem **cụm dấu phẩy liền nhau** là một lần khớp. Với `",a,,b,"`, gộp cụm làm mất trường rỗng ở giữa. Chỉ dùng `+` nếu nhiều dấu liên tiếp **thực sự mang một ý nghĩa ngăn cách duy nhất**.

Chẳng hạn, `"  red   green  ".split("\\s+")` xem nhiều whitespace liền nhau là một ranh giới. Vì dấu cách đầu tạo lần khớp có độ dài dương tại vị trí đầu, vẫn có thể có chuỗi rỗng đầu; `limit=0` chỉ xóa rỗng cuối. `strip()` trước khi tách phù hợp nếu nghiệp vụ cho phép loại whitespace ngoài cùng, nhưng không phù hợp với định dạng yêu cầu bảo toàn khoảng trắng.

## 3. Khi regex xác định ranh giới khác một dấu đơn

- `"[,;]"` khớp từng dấu phẩy hoặc chấm phẩy; `"[,;]+"` gộp cả cụm gồm hai loại.
- `"::"` khớp chính xác hai dấu hai chấm; `":+"` khớp một hay nhiều dấu hai chấm.
- `Pattern.quote(delimiter)` dùng khi ký tự phân cách, ví dụ `"."` hoặc `"|"`, phải được hiểu nguyên văn.
- Với lookahead `"(?=:)"`, regex chỉ khớp **vị trí** trước dấu `:` mà không tiêu thụ ký tự. Khi ấy `:` vẫn nằm trong token; không thể áp dụng trực tiếp bảng của dấu phẩy tiêu thụ ký tự ở trên.

Một định dạng cột cố định thường cần từng dấu phân cách; một danh sách từ cách bởi nhiều whitespace thường cần gộp cụm. **Đặc tả dữ liệu** quyết định cách chọn regex.

## Tự kiểm tra

1. `",,x".split(",", -1)` có mấy phần rỗng ở đầu?
2. Vì sao `"x,,y".split(",+", -1)` có ít phần hơn `split(",", -1)`?
3. Có nên luôn `strip()` trước `split("\\s+")` không?
4. Dùng `split(",")` rồi loại **mọi** chuỗi rỗng có mô phỏng đúng `limit=0` không?

**Đáp án:** (1) Hai. (2) `,+` gộp hai dấu thành một ranh giới, không sinh trường giữa. (3) Chỉ khi whitespace ngoài cùng không là dữ liệu. (4) Không; `limit=0` chỉ loại rỗng cuối, không loại rỗng đầu/giữa.

**Ghi nhớ:** Hãy xác định **mỗi delimiter có là một ranh giới độc lập** hay **nhiều delimiter hợp thành một ranh giới**.