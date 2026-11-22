# Vùng BMP và các code point bổ sung

Khi xử lý Unicode trong Java, bạn cần phân biệt **địa chỉ của một điểm mã** với **số đơn vị dùng để biểu diễn nó**. Một ký tự có thể nằm trong vùng BMP hoặc ngoài BMP; lựa chọn đó ảnh hưởng trực tiếp đến cách đọc chuỗi, tính độ dài và chọn API.

Bài này dùng “điểm mã” cho thuật ngữ **code point**. Ký hiệu `U+1F600` nghĩa là điểm mã có giá trị thập lục phân `1F600`, không phải số byte hay vị trí trong chuỗi.

## 1. Không gian mã Unicode được chia thành các mặt phẳng

Unicode có các điểm mã từ `U+0000` đến `U+10FFFF`. Không gian này gồm 17 mặt phẳng (plane), mỗi mặt phẳng chứa `0x10000`, tức 65.536 vị trí.

| Vùng | Mặt phẳng | Khoảng điểm mã |
| --- | --- | --- |
| BMP — Basic Multilingual Plane | 0 | `U+0000–U+FFFF` |
| Các mặt phẳng bổ sung | 1–16 | `U+10000–U+10FFFF` |

BMP là mặt phẳng đa ngôn ngữ cơ bản; điểm mã lớn hơn `U+FFFF` được gọi là điểm mã bổ sung (supplementary code point). [Thuật ngữ Unicode: BMP và supplementary code point](https://www.unicode.org/glossary/)

Có thể kiểm tra nhanh mặt phẳng bằng cách chia giá trị điểm mã cho `0x10000`. Ví dụ `0x1F600 / 0x10000 = 1` theo phép chia nguyên, nên `U+1F600` nằm ở mặt phẳng 1.

Ranh giới cần nhớ:

```text
U+FFFF   : vị trí cuối BMP
U+10000  : vị trí đầu vùng bổ sung
U+10FFFF : vị trí cuối không gian mã Unicode
U+110000 : nằm ngoài không gian mã Unicode
```

Một vị trí trong khoảng mã không đồng nghĩa với việc vị trí ấy đã được gán cho ký tự dùng để hiển thị. Đừng hiểu “Unicode hỗ trợ hơn một triệu vị trí” thành “có hơn một triệu ký tự đã được gán”.

## 2. BMP không có nghĩa là chỉ chứa tiếng Anh

Một số ví dụ:

| Điểm mã | Ký tự hoặc ý nghĩa | Vùng |
| --- | --- | --- |
| `U+0041` | A | BMP |
| `U+00E9` | é | BMP |
| `U+1EA1` | ạ | BMP |
| `U+4E2D` | 中 | BMP |
| `U+1F600` | 😀 | Bổ sung |
| `U+1D11E` | Ký hiệu khóa Sol trong âm nhạc | Bổ sung |

Vùng bổ sung không phải “vùng riêng của emoji”. Nó còn chứa các hệ chữ, ký hiệu âm nhạc, ký hiệu toán học và những nhóm ký tự khác. Ngược lại, chỉ nhìn hình dạng giống emoji cũng không đủ để kết luận điểm mã nằm ngoài BMP.

Vì vậy, lọc bỏ tất cả điểm mã lớn hơn `U+FFFF` chỉ để tránh lỗi xử lý chuỗi sẽ làm mất dữ liệu hợp lệ. Cách sửa phù hợp thường là thay cách duyệt hoặc cắt chuỗi.

## 3. Mối liên hệ với char và UTF-16 trong Java

`char` là một giá trị 16 bit. API `String` đánh chỉ số theo đơn vị mã UTF-16; một ký tự bổ sung chiếm hai vị trí. [Tài liệu String: biểu diễn UTF-16](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html)

Đối với các giá trị vô hướng Unicode:

| Vùng | Số đơn vị mã UTF-16 | Biểu diễn bằng char |
| --- | --- | --- |
| BMP, ngoài vùng surrogate | 1 | Một `char` |
| Vùng bổ sung | 2 | Một cặp surrogate |

Ví dụ:

```text
U+00E9  → 00E9           một đơn vị mã
U+1F600 → D83D DE00      hai đơn vị mã
```

Hai giá trị `D83D` và `DE00` cùng nhau biểu diễn `U+1F600`. Không giá trị nào trong hai giá trị đó là “điểm mã emoji” khi đứng riêng.

Để giữ một điểm mã bất kỳ, dùng `int` thay vì ép nó về `char`:

```java
int emoji = 0x1F600;
String text = new String(Character.toChars(emoji));
```

Đoạn này minh họa cách tạo chuỗi bên trong một phương thức. Ép `(char) emoji` chỉ giữ 16 bit thấp, không tạo cặp surrogate và không giữ nguyên giá trị ban đầu.

## 4. Ngoại lệ quan trọng trong BMP: vùng surrogate

BMP bao gồm vùng `U+D800–U+DFFF` dành cho surrogate. Những điểm mã này không được dùng như ký tự độc lập. Giá trị vô hướng Unicode (Unicode scalar value) là điểm mã ngoài vùng surrogate. [Unicode Glossary: Unicode scalar value](https://www.unicode.org/glossary/)

Có ba câu hỏi khác nhau:

1. Giá trị có nằm trong khoảng điểm mã Unicode không?
2. Giá trị có thuộc BMP hay vùng bổ sung không?
3. Giá trị có phải giá trị vô hướng dùng để biểu diễn độc lập không?

`U+D800` nằm trong khoảng Unicode và thuộc BMP, nhưng không phải giá trị vô hướng. Đây là lý do không nên viết quy tắc “mọi điểm mã BMP là một ký tự hoàn chỉnh”.

Trong Java, `Character.isValidCodePoint(int)` chỉ kiểm tra khoảng `0–0x10FFFF`. Nó có thể trả `true` cho giá trị surrogate. `isBmpCodePoint` và `isSupplementaryCodePoint` cũng là các phép kiểm tra khoảng tương ứng. [Hợp đồng các hàm kiểm tra Character](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isValidCodePoint(int))

Các phép kiểm tra này không chứng minh điểm mã đã được gán, có phông chữ để hiển thị, hoặc được phép xuất hiện trong một trường dữ liệu cụ thể.

## 5. Chương trình quan sát BMP và vùng bổ sung

Lưu thành **UnicodePlanesDemo.java**. Chương trình không cần in emoji trực tiếp; nó in giá trị số để kết quả không phụ thuộc phông chữ của terminal.

```java
public class UnicodePlanesDemo {
    private static boolean isScalar(int cp) {
        return Character.isValidCodePoint(cp)
                && !(cp >= 0xD800 && cp <= 0xDFFF);
    }

    private static void inspect(int cp) {
        System.out.printf(
                "U+%04X valid=%s scalar=%s BMP=%s supplementary=%s%n",
                cp,
                Character.isValidCodePoint(cp),
                isScalar(cp),
                Character.isBmpCodePoint(cp),
                Character.isSupplementaryCodePoint(cp));
    }

    public static void main(String[] args) {
        inspect(0x0041);
        inspect(0x1F600);
        inspect(0x1D11E);
        inspect(0xD800);
        inspect(0x110000);

        String text = new StringBuilder()
                .append('A')
                .appendCodePoint(0x1F600)
                .append('\u00E9')
                .toString();

        System.out.println("UTF-16 units=" + text.length());
        System.out.println("code points="
                + text.codePointCount(0, text.length()));

        for (int i = 0; i < text.length(); i++) {
            System.out.printf("unit[%d]=%04X%n", i, (int) text.charAt(i));
        }

        for (int i = 0; i < text.length();) {
            int cp = text.codePointAt(i);
            System.out.printf("codePoint at %d=U+%04X%n", i, cp);
            i += Character.charCount(cp);
        }
    }
}
```

Chạy với JDK 17 trở lên:

```shell
javac -encoding UTF-8 UnicodePlanesDemo.java
java UnicodePlanesDemo
```

Stdout:

```text
U+0041 valid=true scalar=true BMP=true supplementary=false
U+1F600 valid=true scalar=true BMP=false supplementary=true
U+1D11E valid=true scalar=true BMP=false supplementary=true
U+D800 valid=true scalar=false BMP=true supplementary=false
U+110000 valid=false scalar=false BMP=false supplementary=false
UTF-16 units=4
code points=3
unit[0]=0041
unit[1]=D83D
unit[2]=DE00
unit[3]=00E9
codePoint at 0=U+0041
codePoint at 1=U+1F600
codePoint at 3=U+00E9
```

Cách đọc kết quả:

- Hai điểm mã bổ sung có số lớn hơn `FFFF`; không thể chứa trọn trong một `char`.
- Dòng `U+D800` cho thấy kiểm tra khoảng khác với kiểm tra giá trị vô hướng.
- Chuỗi `A😀é` có 4 đơn vị mã nhưng 3 điểm mã.
- Vòng lặp `charAt` đi qua các chỉ số 0, 1, 2, 3.
- Vòng lặp điểm mã đi qua chỉ số 0, 1, 3 vì bước qua emoji cần hai đơn vị mã.

Vòng lặp cuối dùng chuỗi UTF-16 hợp lệ đã được chương trình tạo. Nếu đầu vào có surrogate rời, việc duyệt bằng API điểm mã không tự biến đầu vào thành chuỗi hợp lệ; xác thực dữ liệu là yêu cầu riêng.

## 6. Chọn API theo đơn vị cần xử lý

| Mục tiêu | API hoặc cách làm |
| --- | --- |
| Đọc một đơn vị mã UTF-16 | `charAt(index)` |
| Đọc điểm mã tại một ranh giới đúng | `codePointAt(index)` |
| Tính số điểm mã trong chuỗi | `codePointCount(0, length())` |
| Chuyển vị trí theo số điểm mã | `offsetByCodePoints(index, count)` |
| Chuyển điểm mã sang biểu diễn UTF-16 | `Character.toChars(cp)` |
| Ghép một điểm mã vào builder | `appendCodePoint(cp)` |
| Kiểm tra BMP hoặc bổ sung | `Character.isBmpCodePoint(cp)`, `isSupplementaryCodePoint(cp)` |

Chỉ số của `codePointAt` vẫn là chỉ số UTF-16. Nếu truyền vị trí trỏ vào low surrogate ở giữa cặp, bạn không nhận lại điểm mã bổ sung như khi bắt đầu ở high surrogate. Từ “code point” trong tên phương thức không đổi hệ chỉ số của chuỗi. [Tài liệu codePointAt](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#codePointAt(int))

Khi cần lấy điểm mã đầu tiên từ một chuỗi không rỗng:

```java
int end = text.offsetByCodePoints(0, 1);
String first = text.substring(0, end);
```

Đây là đoạn minh họa bên trong phương thức. Điều kiện `text` không rỗng phải được kiểm tra trước. Nếu lấy `substring(0, 1)`, bạn có thể chỉ lấy một nửa của ký tự bổ sung đứng đầu chuỗi.

## 7. Những nhầm lẫn cần tránh

**Unicode không phải luôn là hai byte cho mỗi ký tự.** BMP và vùng bổ sung là phân vùng điểm mã. UTF-8, UTF-16 và UTF-32 là cách biểu diễn. Số byte còn phụ thuộc cách mã hóa; `String.length()` không phải kích thước UTF-8.

**Số điểm mã chưa phải số ký tự người dùng nhìn thấy.** Một chữ có thể gồm chữ nền và dấu kết hợp; một emoji có thể gồm nhiều điểm mã. Biết BMP và vùng bổ sung giúp xử lý biểu diễn, chưa thay thế việc phân đoạn cụm ký tự.

**Điểm mã lớn không có nghĩa là dữ liệu sai.** Hãy kiểm tra yêu cầu nghiệp vụ thay vì giới hạn toàn bộ đầu vào vào BMP.

**Không dùng một char để đại diện mọi ký tự Unicode.** Nếu API cần nhận một điểm mã bất kỳ, kiểu `int` và các phương thức hỗ trợ điểm mã thường phù hợp hơn.

**Không đồng nhất lỗi hiển thị với lỗi dữ liệu.** Ký tự hiện thành ô vuông có thể do thiếu phông chữ. In giá trị `U+...` và các đơn vị mã giúp phân biệt dữ liệu thực tế với cách terminal trình bày.

Các ranh giới BMP/bổ sung không phụ thuộc việc một JDK đã nhận diện tên hoặc thuộc tính của mọi ký tự mới hay chưa. Dữ liệu thuộc tính Unicode mà JDK hỗ trợ có phiên bản riêng; đừng suy ra rằng “JDK chưa biết tên” nghĩa là điểm mã nằm ngoài phạm vi.

## 8. Tự kiểm tra

1. `U+10000` thuộc BMP hay vùng bổ sung? Cần bao nhiêu `char` trong UTF-16?
2. Vì sao `Character.isValidCodePoint(0xD800)` trả `true` nhưng giá trị ấy không đại diện ký tự độc lập?
3. Chuỗi gồm một ký tự BMP thông thường và hai điểm mã bổ sung có bao nhiêu đơn vị mã UTF-16?
4. Vì sao vòng lặp `i++` kết hợp `charAt(i)` không tương đương duyệt từng điểm mã?

Đáp án:

1. Vùng bổ sung; hai `char`.
2. Phương thức chỉ kiểm tra khoảng giá trị; vùng surrogate nằm trong khoảng đó nhưng bị loại khỏi tập giá trị vô hướng.
3. Năm đơn vị mã, giả sử chuỗi được biểu diễn hợp lệ.
4. Nó đi qua từng đơn vị mã, nên đi vào cả hai nửa của mỗi cặp surrogate.
