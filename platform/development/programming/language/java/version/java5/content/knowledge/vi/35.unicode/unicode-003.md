# Cặp surrogate cao và surrogate thấp trong Java

Một `char` của Java chỉ giữ được một đơn vị mã UTF-16 16 bit. Khi một điểm mã Unicode nằm trong khoảng `U+10000–U+10FFFF`, UTF-16 biểu diễn nó bằng **hai đơn vị mã liên tiếp**. Hai đơn vị ấy tạo thành cặp surrogate.

Mục tiêu của bài là đọc được cấu trúc cặp, chuyển đổi đúng giữa cặp và điểm mã, đồng thời phát hiện dữ liệu bị cắt hoặc ghép sai. Cơ chế này vẫn là nền tảng của cách API chuỗi Java xử lý ký tự bổ sung hiện nay.

## 1. Hai vai trò và thứ tự bắt buộc

| Thành phần | Thuật ngữ | Khoảng giá trị |
| --- | --- | --- |
| Surrogate cao | high surrogate, còn gọi là leading surrogate | `D800–DBFF` |
| Surrogate thấp | low surrogate, còn gọi là trailing surrogate | `DC00–DFFF` |

Một cặp hợp lệ luôn có dạng:

```text
high surrogate → low surrogate
```

Ví dụ, điểm mã `U+1F680` của 🚀 được biểu diễn thành:

```text
D83D DE80
│    └── surrogate thấp
└─────── surrogate cao
```

Mỗi thành phần là một đơn vị mã, không phải một ký tự độc lập. Ghép đúng hai đơn vị mã giúp khôi phục **một điểm mã bổ sung**. [Unicode FAQ: UTF-16](https://www.unicode.org/faq/utf_bom.html)

“Cao” và “thấp” nói về phần thông tin mà hai đơn vị mang trong phép chuyển đổi. Chúng không phải byte cao và byte thấp của một `char`. Thứ tự byte khi ghi UTF-16LE/UTF-16BE là vấn đề khác.

## 2. Nhận diện cặp hợp lệ và các dạng sai

| Dãy đơn vị mã | Kết luận |
| --- | --- |
| `D83D DE80` | Cặp hợp lệ |
| `DE80 D83D` | Sai thứ tự |
| `D83D` | Surrogate cao rời |
| `DE80` | Surrogate thấp rời |
| `D83D 0041` | Surrogate cao không có phần thấp theo sau |
| `D83D D83D DE80` | Surrogate cao đầu tiên bị rời; hai đơn vị sau tạo cặp |

Trong một chuỗi UTF-16 hợp lệ:

- Gặp surrogate cao thì đơn vị tiếp theo phải là surrogate thấp.
- Surrogate thấp không được xuất hiện một mình.
- Các đơn vị ngoài vùng surrogate có thể đi qua riêng từng đơn vị.

Java có thể chứa `String` với surrogate rời. Việc tạo được đối tượng chuỗi hoặc gọi được `length()` không chứng minh chuỗi là UTF-16 hợp lệ. Bạn cần kiểm tra khi hợp đồng dữ liệu yêu cầu điều đó.

## 3. Công thức chuyển đổi

Công thức giúp giải thích cơ chế; trong mã ứng dụng, nên dùng API Java đã có.

Với `cp` là điểm mã trong khoảng `0x10000–0x10FFFF`:

```text
u    = cp - 0x10000
high = 0xD800 + (u >> 10)
low  = 0xDC00 + (u & 0x3FF)
```

Sau khi trừ `0x10000`, giá trị `u` vừa trong 20 bit. Mười bit cao đi vào surrogate cao, mười bit thấp đi vào surrogate thấp. Hai vùng surrogate có các tiền tố riêng nên có thể nhận ra vai trò của từng đơn vị.

Với `cp = 0x1F680`:

```text
u       = 0xF680
u >> 10 = 0x003D
u & 3FF = 0x0280

high    = 0xD800 + 0x003D = 0xD83D
low     = 0xDC00 + 0x0280 = 0xDE80
```

Chiều ngược lại, sau khi xác nhận cặp hợp lệ:

```text
cp = 0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
```

Thay `D83D DE80` vào công thức:

```text
cp = 0x10000 + 0xF400 + 0x0280
   = 0x1F680
```

Không áp dụng công thức này cho hai `char` bất kỳ rồi xem kết quả là bằng chứng đầu vào hợp lệ.

## 4. Các API cần dùng

| Nhu cầu | API |
| --- | --- |
| Kiểm tra một đơn vị là surrogate cao | `Character.isHighSurrogate(ch)` |
| Kiểm tra một đơn vị là surrogate thấp | `Character.isLowSurrogate(ch)` |
| Kiểm tra thứ tự cao–thấp | `Character.isSurrogatePair(high, low)` |
| Từ điểm mã sang một hoặc hai đơn vị mã | `Character.toChars(cp)` |
| Từ cặp surrogate sang điểm mã | `Character.toCodePoint(high, low)` |

`toCodePoint` **không tự xác thực cặp**. Với dữ liệu bên ngoài, kiểm tra `isSurrogatePair` trước khi chuyển đổi. [Tài liệu Character.toCodePoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#toCodePoint(char,char))

`toChars` xử lý cả giá trị BMP lẫn điểm mã bổ sung; vì vậy đừng mặc định mảng trả về luôn có hai phần tử. Riêng ví dụ `0x1F680` bên dưới đã biết là điểm mã bổ sung nên mảng có đúng hai phần tử.

## 5. Chương trình chạy đầy đủ

Chương trình tạo một cặp từ điểm mã, chuyển ngược lại, rồi kiểm tra một số chuỗi hợp lệ và không hợp lệ. Hàm kiểm tra yêu cầu đầu vào khác `null`; chuỗi rỗng được chấp nhận.

Lưu thành **SurrogatePairDemo.java**:

```java
public class SurrogatePairDemo {
    private static boolean isWellFormedUtf16(String text) {
        for (int i = 0; i < text.length(); i++) {
            char current = text.charAt(i);

            if (Character.isHighSurrogate(current)) {
                if (i + 1 >= text.length()
                        || !Character.isLowSurrogate(text.charAt(i + 1))) {
                    return false;
                }
                i++;
            } else if (Character.isLowSurrogate(current)) {
                return false;
            }
        }
        return true;
    }

    public static void main(String[] args) {
        int codePoint = 0x1F680;
        char[] pair = Character.toChars(codePoint);
        char high = pair[0];
        char low = pair[1];

        System.out.printf("high=%04X, low=%04X%n", (int) high, (int) low);
        System.out.println("high check=" + Character.isHighSurrogate(high));
        System.out.println("low check=" + Character.isLowSurrogate(low));
        System.out.println("pair check=" + Character.isSurrogatePair(high, low));
        System.out.println("reversed pair="
                + Character.isSurrogatePair(low, high));

        if (!Character.isSurrogatePair(high, low)) {
            throw new IllegalArgumentException("Invalid surrogate pair");
        }
        int restored = Character.toCodePoint(high, low);
        System.out.printf("restored=U+%X%n", restored);

        String valid = "X" + new String(pair) + "Y";
        String loneHigh = String.valueOf(high);
        String loneLow = String.valueOf(low);
        String reversed = new String(new char[] {low, high});

        System.out.println("empty valid=" + isWellFormedUtf16(""));
        System.out.println("ordinary valid=" + isWellFormedUtf16("Java"));
        System.out.println("pair in text valid=" + isWellFormedUtf16(valid));
        System.out.println("lone high valid=" + isWellFormedUtf16(loneHigh));
        System.out.println("lone low valid=" + isWellFormedUtf16(loneLow));
        System.out.println("reversed valid=" + isWellFormedUtf16(reversed));

        System.out.println("units=" + valid.length());
        System.out.println("points=" + valid.codePointCount(0, valid.length()));
    }
}
```

Chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 SurrogatePairDemo.java
java SurrogatePairDemo
```

Stdout:

```text
high=D83D, low=DE80
high check=true
low check=true
pair check=true
reversed pair=false
restored=U+1F680
empty valid=true
ordinary valid=true
pair in text valid=true
lone high valid=false
lone low valid=false
reversed valid=false
units=4
points=3
```

Chuỗi hợp lệ có dạng `X🚀Y`: X và Y mỗi phần chiếm một đơn vị mã, tên lửa chiếm hai. Vì thế tổng là bốn đơn vị mã nhưng ba điểm mã.

Trong hàm kiểm tra, `i++` bên trong nhánh surrogate cao bỏ qua phần thấp vừa được xác nhận. Lần tăng chỉ số của vòng `for` đưa quá trình kiểm tra đến đơn vị tiếp theo sau cặp. Nếu không bỏ qua phần thấp, chương trình sẽ nhầm nó thành một surrogate thấp rời ở lượt kế tiếp.

Hàm này chỉ kiểm tra cấu trúc UTF-16. Nó không kiểm tra tên ký tự đã được Unicode gán, quy tắc đặt tên người dùng hay dữ liệu có phù hợp nghiệp vụ không.

## 6. Cẩn thận khi đọc, cắt và xóa chuỗi

Các chỉ số của `String` tính theo đơn vị mã UTF-16. [Tài liệu String](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)

Với `text` chứa một tên lửa theo sau bởi chữ A:

```java
String text = new String(Character.toChars(0x1F680)) + "A";
String broken = text.substring(0, 1);
int end = text.offsetByCodePoints(0, 1);
String complete = text.substring(0, end);
```

Đây là đoạn minh họa bên trong phương thức:

- `broken` chỉ chứa surrogate cao; không còn là UTF-16 hợp lệ.
- `end` bằng 2.
- `complete` chứa cả cặp, tức một điểm mã tên lửa.

Cùng lỗi có thể xuất hiện khi xóa một `char` ở giữa cặp hoặc giới hạn số đơn vị mã mà không xét ranh giới. Nếu mục tiêu là xử lý theo điểm mã, phải tính đúng ranh giới trước khi cắt hoặc xóa.

`codePointAt(index)` cũng không phải hàm xác thực toàn chuỗi. Nó ghép cặp khi vị trí hiện tại là surrogate cao và có surrogate thấp ngay sau; nếu không, nó có thể trả lại giá trị đơn vị mã tại vị trí đó. [Hợp đồng codePointAt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePointAt(int))

Đừng dùng việc “gọi được API điểm mã mà không có ngoại lệ” để kết luận mọi surrogate đã được ghép đúng.

## 7. Những điều dễ hiểu sai

**Hai surrogate không phải hai ký tự văn bản.** Chúng là hai đơn vị biểu diễn một điểm mã bổ sung.

**Không phải cứ hai char là thành một cặp.** Một đơn vị cao phải đứng ngay trước một đơn vị thấp; dữ liệu ở giữa hoặc thứ tự đảo đều làm mất cặp.

**Không cần tự ghép cặp cho mọi ký tự.** Giá trị BMP ngoài vùng surrogate được biểu diễn bằng một đơn vị UTF-16.

**Surrogate rời không được “sửa” bằng cách nối bừa.** Việc ghép hai phần từ những nguồn khác nhau có thể tạo một điểm mã ngoài ý định. Khi nhận đầu vào lỗi, hãy áp dụng chính sách rõ ràng như từ chối hoặc thay thế theo hợp đồng dữ liệu.

**Một cặp hợp lệ chưa chắc là toàn bộ ký tự người dùng nhìn thấy.** Điểm mã bổ sung có thể chỉ là một phần của cụm gồm nhiều điểm mã. Kiểm tra surrogate giải quyết tính hợp lệ của biểu diễn UTF-16, không thay thế việc nhận diện cụm ký tự.

**Kết quả hiển thị không đủ để chẩn đoán.** Khi điều tra dữ liệu hỏng, hãy in từng đơn vị dưới dạng hex như chương trình trên; terminal có thể che lỗi bằng ký hiệu thay thế.

## 8. Bài tập tự kiểm tra

1. `D800 DC00` và `DBFF DFFF` tương ứng với các điểm mã nào?
2. Dãy `0041 D83D 0042 DE80` có hợp lệ không?
3. Vì sao `toCodePoint(high, low)` không nên là bước đầu tiên với dữ liệu chưa biết?
4. Với một chuỗi bắt đầu bằng ký tự bổ sung, muốn lấy điểm mã đầu tiên thì ranh giới cuối theo `char` là 1 hay 2?

Đối chiếu:

1. Lần lượt `U+10000` và `U+10FFFF`.
2. Không; surrogate cao bị ngăn khỏi phần thấp bởi `0042`, và phần thấp sau đó bị rời.
3. Hàm không xác thực cặp; cần kiểm tra đúng miền và thứ tự trước.
4. Là 2; phải lấy cả surrogate cao và thấp.
