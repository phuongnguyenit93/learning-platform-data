# StringBuilder.reverse() và ký tự biểu diễn bằng cặp surrogate

Đảo chuỗi tưởng như chỉ là đọc từng ký tự từ cuối về đầu. Nhưng trong Java, một giá trị `char` có thể chỉ chứa một nửa biểu diễn của một ký tự Unicode. Bài này giúp bạn xác định đơn vị đang đảo, quan sát `reverse()` với emoji, và nhận ra giới hạn khi xử lý chữ có dấu hoặc emoji ghép.

## 1. Ba đơn vị cần phân biệt

| Đơn vị | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| Đơn vị mã UTF-16 (code unit) | Một giá trị `char` 16 bit | `0xD83D` |
| Điểm mã Unicode (code point) | Giá trị nhận diện trong không gian mã Unicode | `U+1F600` cho 😀 |
| Cụm ký tự (grapheme cluster) | Cụm mà người đọc thường cảm nhận như một ký tự | `a` cùng dấu sắc kết hợp |

Trong UTF-16, ký tự bổ sung ngoài BMP được biểu diễn bằng hai đơn vị mã: high surrogate trong khoảng `D800–DBFF`, theo sau bởi low surrogate trong khoảng `DC00–DFFF`. Thứ tự này tạo thành cặp surrogate hợp lệ. Một nửa đứng riêng không biểu diễn được ký tự bổ sung đó. [Tài liệu Character](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html)

Với chuỗi `A😀B`, biểu diễn cần quan sát là:

```text
Chỉ số char:        0       1       2       3
Đơn vị mã:        0041    D83D    DE00    0042
Điểm mã:          U+0041  [   U+1F600   ] U+0042
```

Chuỗi này dài **4 đơn vị mã** nhưng có **3 điểm mã**. Đếm bằng mắt hoặc lấy `length()` rồi gọi đó là “số ký tự” dễ dẫn đến giả định sai.

## 2. reverse() bảo vệ cặp surrogate như thế nào?

`StringBuilder.reverse()` thay đổi chính builder và trả lại tham chiếu tới builder đó. Cặp high–low hợp lệ được coi như một đơn vị khi đảo; thứ tự hai nửa trong cặp được giữ nguyên. [Hợp đồng reverse()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#reverse())

Áp dụng cho ví dụ trên:

```text
Trước:       0041 [D83D DE00] 0042     A😀B
Sau reverse: 0042 [D83D DE00] 0041     B😀A
```

Cả cặp chuyển sang vị trí mới nhưng bên trong vẫn là `D83D DE00`. Emoji vì thế vẫn được biểu diễn bằng cùng một điểm mã.

Nếu tự duyệt lùi bằng `charAt(i)` và nối từng `char`, kết quả lại là:

```text
0042 DE00 D83D 0041
```

Hai nửa đã thành low–high. Chương trình vẫn có thể chứa chuỗi này, nhưng biểu diễn UTF-16 của emoji đã bị phá. Terminal có thể hiện dấu hỏi hoặc ký hiệu thay thế; hình dạng hiển thị phụ thuộc môi trường nên không dùng nó để kết luận dữ liệu còn nguyên.

## 3. Chương trình chạy đầy đủ

Lưu thành **ReverseSurrogateDemo.java**. Các Unicode escape trong mã giúp ví dụ không phụ thuộc việc sao chép emoji. Hàm `units()` in từng đơn vị mã ở hệ thập lục phân, nên stdout chỉ có ASCII.

```java
public class ReverseSurrogateDemo {
    private static String units(String text) {
        StringBuilder result = new StringBuilder();
        for (int i = 0; i < text.length(); i++) {
            if (i > 0) result.append(' ');
            result.append(String.format("%04X", (int) text.charAt(i)));
        }
        return result.toString();
    }

    // Phien ban sai neu muc tieu la giu nguyen ky tu bo sung.
    private static String reverseChars(String text) {
        StringBuilder result = new StringBuilder();
        for (int i = text.length() - 1; i >= 0; i--) {
            result.append(text.charAt(i));
        }
        return result.toString();
    }

    public static void main(String[] args) {
        String original = "A\uD83D\uDE00B";
        StringBuilder builder = new StringBuilder(original);
        StringBuilder returned = builder.reverse();

        System.out.println("original units: " + units(original));
        System.out.println("length: " + original.length());
        System.out.println("code points: "
                + original.codePointCount(0, original.length()));
        System.out.println("reverse units: " + units(builder.toString()));
        System.out.println("same builder: " + (returned == builder));
        System.out.println("naive units: " + units(reverseChars(original)));

        String combining = "a\u0301b";
        System.out.println("combining before: " + units(combining));
        System.out.println("combining after: "
                + units(new StringBuilder(combining).reverse().toString()));

        String malformed = "\uDE00\uD83D";
        String once = new StringBuilder(malformed).reverse().toString();
        String twice = new StringBuilder(once).reverse().toString();
        System.out.println("malformed before: " + units(malformed));
        System.out.println("malformed once: " + units(once));
        System.out.println("malformed twice: " + units(twice));
        System.out.println("round trip equal: " + malformed.equals(twice));
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 ReverseSurrogateDemo.java
java ReverseSurrogateDemo
```

Stdout:

```text
original units: 0041 D83D DE00 0042
length: 4
code points: 3
reverse units: 0042 D83D DE00 0041
same builder: true
naive units: 0042 DE00 D83D 0041
combining before: 0061 0301 0062
combining after: 0062 0301 0061
malformed before: DE00 D83D
malformed once: D83D DE00
malformed twice: D83D DE00
round trip equal: false
```

Dòng `same builder: true` xác nhận phép đảo không tạo builder độc lập. Biến `original` vẫn chứa dữ liệu ban đầu vì đó là `String` được dùng để khởi tạo builder.

## 4. Giữ cặp surrogate chưa đủ để giữ ký tự người dùng nhìn thấy

Đọc hai dòng `combining` trong stdout:

```text
a + dấu sắc kết hợp + b
0061 0301 0062

b + dấu sắc kết hợp + a
0062 0301 0061
```

Chuỗi ban đầu dùng `a\u0301` để biểu diễn chữ a với dấu sắc. Phép đảo chuyển dấu sang giữa b và a. Nó không giữ cụm a–dấu như một khối.

Đây là sự khác biệt giữa đảo điểm mã và đảo cụm ký tự. Unicode dùng quy tắc phân đoạn để nhận diện ranh giới cụm ký tự; một cụm có thể gồm nhiều điểm mã. Emoji có dấu điều chỉnh màu da, emoji nối bằng ZWJ và cờ tạo bởi các ký hiệu vùng cũng cần được xem xét ở tầng này. [Unicode Text Segmentation, phần grapheme cluster](https://www.unicode.org/reports/tr29/#Grapheme_Cluster_Boundaries)

Trước khi chọn thuật toán, hãy xác định yêu cầu:

- **Đảo dữ liệu đơn giản như ASCII:** `reverse()` thường đáp ứng trực tiếp.
- **Đảo thứ tự điểm mã của UTF-16 hợp lệ:** `reverse()` giữ nguyên các cặp surrogate, phù hợp với đơn vị này.
- **Đảo văn bản theo cụm ký tự:** cần phân đoạn thành các cụm, đảo thứ tự cụm rồi nối lại, giữ nguyên bên trong từng cụm.
- **Đảo theo từ hoặc xử lý văn bản hai chiều:** cần quy tắc riêng theo yêu cầu; đảo chuỗi không tự giải quyết thứ tự đọc hoặc bố cục hiển thị.

Tự đổi vòng lặp sang `codePoints()` chỉ giải quyết việc ghép cặp surrogate, vẫn chưa tự giữ dấu kết hợp bên cạnh chữ gốc. Khi yêu cầu là cụm ký tự, cần kiểm tra công cụ phân đoạn và phiên bản Unicode mà môi trường triển khai hỗ trợ.

## 5. Surrogate không ghép cặp: đảo hai lần có thể không về ban đầu

Hai đơn vị cuối chương trình được tạo cố ý theo thứ tự sai:

```text
Ban đầu:       DE00 D83D      low rồi high
Đảo lần 1:     D83D DE00      trở thành một cặp hợp lệ
Đảo lần 2:     D83D DE00      cặp hợp lệ được giữ nguyên
```

Vì vậy `round trip equal` là `false`. Đây là hệ quả của việc những surrogate rời rạc có thể trở thành cặp sau phép đảo, một tình huống được API nêu rõ. [Lưu ý về surrogate rời trong reverse()](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/StringBuilder.html#reverse())

Với UTF-16 hợp lệ, đảo hai lần khôi phục chuỗi ban đầu. Không mở rộng tính chất đó thành lời khẳng định cho mọi dãy `char`. Cũng không dùng `reverse()` để kiểm tra hoặc sửa dữ liệu Unicode: ví dụ trên chỉ tình cờ tạo được cặp, không phải một cơ chế xác thực.

## 6. Cách áp dụng và lỗi thường gặp

Khi cần tạo kết quả đảo nhưng vẫn giữ nguồn dưới dạng `String`, có thể dùng đoạn mã sau bên trong phương thức:

```java
String source = "A\uD83D\uDE00B";
String reversed = new StringBuilder(source).reverse().toString();
```

Nếu nguồn là một builder cần giữ nguyên, hãy tạo bản sao trước khi đảo:

```java
StringBuilder source = new StringBuilder("A\uD83D\uDE00B");
String reversed = new StringBuilder(source).reverse().toString();
```

Hai đoạn này minh họa cách gọi, không phải các chương trình độc lập.

Các lỗi cần tránh:

| Giả định | Cách kiểm tra hoặc sửa |
| --- | --- |
| Một `char` luôn là một ký tự hoàn chỉnh | Quan sát cặp `D83D DE00` trong ví dụ |
| Duyệt lùi bằng `charAt()` tương đương `reverse()` | So sánh dòng `naive units` và `reverse units` |
| Bảo vệ surrogate nghĩa là bảo vệ mọi emoji hoặc chữ có dấu | Xác định có cần đảo theo cụm ký tự không |
| Đảo hai lần luôn khôi phục mọi dãy `char` | Kiểm tra trường hợp low–high rời rạc |
| Chỉ nhìn kết quả terminal là đủ | In đơn vị mã hoặc điểm mã để quan sát dữ liệu |
| `reverse()` trả builder mới | Chú ý tham chiếu trả về và tác động lên đối tượng nguồn |

## 7. Tự kiểm tra

1. Với `X\uD83D\uDE80Y`, hãy dự đoán đơn vị mã sau `reverse()`.
2. Thay emoji trong chương trình bằng hai emoji liên tiếp. Cặp nào phải giữ nguyên?
3. Với `a\u0301b`, kết quả mong muốn khi đảo theo cụm ký tự là dãy đơn vị mã nào?
4. Vì sao dữ liệu `\uDE00\uD83D` không phù hợp để kiểm chứng tính chất “đảo hai lần”?

Đối chiếu:

1. `0059 D83D DE80 0058`.
2. Mỗi cặp high–low của từng emoji giữ nguyên bên trong; thứ tự hai emoji đổi chỗ.
3. `0062 0061 0301`: b đứng trước, cụm a–dấu được giữ nguyên. Đây khác kết quả của `StringBuilder.reverse()`.
4. Chuỗi ban đầu chứa surrogate rời; lần đảo đầu tạo cặp mới, lần đảo sau giữ cặp đó.
