# Character.isValidCodePoint, isSupplementaryCodePoint và charCount

Khi nhận một số nguyên biểu diễn điểm mã Unicode, có ba câu hỏi riêng: số đó có nằm trong miền điểm mã không, nó có thuộc vùng bổ sung không, và biểu diễn UTF-16 cần bao nhiêu đơn vị `char`. Ba phương thức trong bài trả lời ba câu hỏi này; chúng không thay thế lẫn nhau.

Đây là các phương thức `static`, gọi trực tiếp qua `Character`, không cần tạo đối tượng bao `Character`.

## 1. Bản đồ trách nhiệm

| Phương thức | Câu hỏi | Kiểu kết quả |
| --- | --- | --- |
| `isValidCodePoint(int cp)` | Giá trị có thuộc khoảng điểm mã Unicode? | `boolean` |
| `isSupplementaryCodePoint(int cp)` | Giá trị có thuộc vùng bổ sung? | `boolean` |
| `charCount(int cp)` | Cần bước qua 1 hay 2 đơn vị mã UTF-16 cho giá trị này? | `int` |

Các ranh giới được dùng là:

```text
0x000000–0x00FFFF : BMP
0x010000–0x10FFFF : vùng bổ sung
```

`charCount` trả về số **đơn vị mã UTF-16**, không phải số byte UTF-8, số điểm mã trong chuỗi hay số ký tự người đọc nhìn thấy.

## 2. isValidCodePoint: xác thực khoảng số

`Character.isValidCodePoint(cp)` trả `true` khi `cp` nằm trong khoảng `0–0x10FFFF`, bao gồm hai đầu. [Hợp đồng isValidCodePoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isValidCodePoint(int))

Có thể hiểu phép kiểm tra qua biểu thức tương đương:

```java
cp >= Character.MIN_CODE_POINT && cp <= Character.MAX_CODE_POINT
```

Đây là biểu thức minh họa, cần đặt trong ngữ cảnh có biến `cp`.

Tên “valid” phải được đọc đúng phạm vi: nó không kiểm tra vị trí đã được gán ký tự, có thể in ra màn hình, hay phù hợp với dữ liệu nghiệp vụ.

Đặc biệt, `0xD800–0xDFFF` là vùng surrogate và vẫn thuộc khoảng điểm mã. Vì vậy:

```java
Character.isValidCodePoint(0xD800)  // true
```

Điều đó không có nghĩa surrogate rời là một ký tự độc lập hợp lệ.

Giá trị vô hướng Unicode (Unicode scalar value) loại trừ vùng surrogate khỏi tập điểm mã. Nếu đầu vào phải biểu diễn một giá trị độc lập, cần kiểm tra thêm điều kiện loại trừ ấy. [Unicode Glossary: giá trị vô hướng](https://www.unicode.org/glossary/)

## 3. isSupplementaryCodePoint: nhận diện vùng bổ sung

`Character.isSupplementaryCodePoint(cp)` trả `true` khi `cp` thuộc khoảng `0x10000–0x10FFFF`. [Hợp đồng isSupplementaryCodePoint](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#isSupplementaryCodePoint(int))

Ví dụ:

| Giá trị | Kết quả | Ý nghĩa |
| --- | --- | --- |
| `0xFFFF` | `false` | Còn ở BMP |
| `0x10000` | `true` | Điểm đầu vùng bổ sung |
| `0x1F600` | `true` | Một điểm mã bổ sung |
| `0x10FFFF` | `true` | Điểm cuối vùng bổ sung |
| `0x110000` | `false` | Đã ra ngoài miền Unicode |

`false` không đủ để kết luận “đây là BMP”. Nó có thể là giá trị âm hoặc lớn hơn `0x10FFFF`. Muốn phân nhánh BMP/bổ sung cho dữ liệu chưa biết, hãy xác thực miền trước.

Ngược lại, nếu phương thức trả `true` thì giá trị chắc chắn đã thuộc miền điểm mã và nằm ngoài vùng surrogate.

## 4. charCount: tính độ rộng UTF-16, không xác thực

Với điểm mã bổ sung hợp lệ, `Character.charCount(cp)` trả 2; với giá trị BMP trả 1. Phương thức không tự kiểm tra tính hợp lệ. [Hợp đồng charCount](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/Character.html#charCount(int))

Quy tắc tính là:

```java
cp >= 0x10000 ? 2 : 1
```

Vì không có bước kiểm tra miền:

- `charCount(-1)` trả 1.
- `charCount(0x110000)` trả 2.
- `charCount(0xD800)` trả 1.

Những kết quả này không làm các giá trị trở thành ký tự độc lập hợp lệ. Không dùng điều kiện “kết quả bằng 1 hoặc 2” làm phép xác thực, bởi cả đầu vào sai cũng cho các kết quả ấy.

## 5. Chương trình kiểm tra ranh giới và cách dùng an toàn

Chương trình dưới đây cố ý gọi ba API với cả dữ liệu đúng và sai để quan sát khác biệt. Sau đó, nó dùng một hàm có tiền điều kiện rõ ràng: chỉ chấp nhận giá trị vô hướng Unicode.

Lưu thành **CodePointChecksDemo.java**:

```java
public class CodePointChecksDemo {
    private static int unitsForScalar(int cp) {
        if (!Character.isValidCodePoint(cp)) {
            throw new IllegalArgumentException("Outside Unicode range");
        }
        if (cp >= 0xD800 && cp <= 0xDFFF) {
            throw new IllegalArgumentException("Surrogate is not a scalar");
        }
        return Character.charCount(cp);
    }

    public static void main(String[] args) {
        int[] samples = {
            -1, 0x0041, 0xD800, 0xFFFF,
            0x10000, 0x1F600, 0x10FFFF, 0x110000
        };

        for (int cp : samples) {
            System.out.printf(
                    "0x%08X valid=%s supplementary=%s units=%d%n",
                    cp,
                    Character.isValidCodePoint(cp),
                    Character.isSupplementaryCodePoint(cp),
                    Character.charCount(cp));
        }

        int[] rejected = {-1, 0xD800, 0x110000};
        for (int cp : rejected) {
            try {
                unitsForScalar(cp);
                System.out.println("accepted unexpectedly");
            } catch (IllegalArgumentException ex) {
                System.out.printf("rejected=0x%08X%n", cp);
            }
        }

        int[] points = {0x0041, 0x1F600, 0x20AC};
        int predicted = 0;
        for (int cp : points) {
            predicted += unitsForScalar(cp);
        }

        String text = new String(points, 0, points.length);
        System.out.println("predicted units=" + predicted);
        System.out.println("actual units=" + text.length());
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```shell
javac -encoding UTF-8 CodePointChecksDemo.java
java CodePointChecksDemo
```

Stdout:

```text
0xFFFFFFFF valid=false supplementary=false units=1
0x00000041 valid=true supplementary=false units=1
0x0000D800 valid=true supplementary=false units=1
0x0000FFFF valid=true supplementary=false units=1
0x00010000 valid=true supplementary=true units=2
0x0001F600 valid=true supplementary=true units=2
0x0010FFFF valid=true supplementary=true units=2
0x00110000 valid=false supplementary=false units=2
rejected=0xFFFFFFFF
rejected=0x0000D800
rejected=0x00110000
predicted units=4
actual units=4
```

`0xFFFFFFFF` là cách `%08X` trình bày mẫu bit của số `int` -1, không phải một điểm mã Unicode.

Ba phần của kết quả minh họa ba ý:

1. `isValidCodePoint` và `isSupplementaryCodePoint` kiểm tra miền, còn `charCount` chỉ tính theo ngưỡng.
2. `unitsForScalar` từ chối surrogate và giá trị ngoài miền trước khi dùng kết quả đếm.
3. Ba giá trị A, emoji và dấu euro cần tổng cộng `1 + 2 + 1 = 4` đơn vị mã UTF-16.

`U+FFFF` trong bảng là một noncharacter của Unicode. Nó vẫn nằm trong miền điểm mã và là giá trị vô hướng; việc chấp nhận nó trong dữ liệu cụ thể cần chính sách riêng. Kết quả `true` không phải cam kết rằng có một hình chữ thông thường để hiển thị.

## 6. Ứng dụng trong vòng lặp duyệt điểm mã

Sau khi lấy một điểm mã từ chuỗi UTF-16 hợp lệ ở đúng ranh giới, `charCount` cho biết cần tăng chỉ số `char` bao nhiêu bước:

```java
for (int index = 0; index < text.length();) {
    int cp = text.codePointAt(index);
    System.out.printf("U+%X%n", cp);
    index += Character.charCount(cp);
}
```

Đây là đoạn vòng lặp minh họa, đặt trong phương thức với biến `text` đã có.

Nếu `cp` là điểm mã BMP thì tăng 1; nếu là điểm mã bổ sung thì tăng 2 để không đi vào giữa cặp surrogate.

Vòng lặp này không tự xác thực toàn bộ chuỗi. Một `String` có thể chứa surrogate rời; `codePointAt` có thể trả giá trị surrogate đó và `charCount` vẫn trả 1. Nếu hợp đồng đầu vào yêu cầu UTF-16 hợp lệ, phải xác thực cấu trúc surrogate hoặc từ chối các giá trị rời trong quá trình xử lý.

Cũng không cần đếm nhiều lần bằng `charCount` nếu mục tiêu chỉ là biết số đơn vị mã của một `String` đã có: `text.length()` trả trực tiếp số ấy.

## 7. Những phép suy luận sai cần tránh

| Suy luận sai | Vì sao sai? |
| --- | --- |
| `isValidCodePoint(cp)` là `true` nên có thể in độc lập | Vẫn có thể là surrogate hoặc giá trị không có hình hiển thị |
| `isSupplementaryCodePoint(cp)` là `false` nên thuộc BMP | Có thể là số ngoài miền Unicode |
| `charCount(cp) == 2` nên điểm mã hợp lệ | Giá trị `0x110000` cũng cho 2 |
| `charCount(cp)` cho số byte | Nó đếm đơn vị mã UTF-16 |
| Gọi `charCount` sẽ ném lỗi với điểm mã sai | Phương thức không làm bước xác thực đó |
| Ép `cp` sang `char` rồi mới kiểm tra | Phép ép có thể làm mất các bit cao, thay đổi giá trị cần kiểm tra |

Nên giữ đầu vào ở kiểu `int` cho đến khi đã phân loại hoặc chuyển đổi qua API phù hợp. Chẳng hạn, ép `0x1F600` sang `char` không tạo emoji; nó chỉ giữ 16 bit thấp.

Ba phép kiểm tra trong bài cũng không giải quyết việc đếm cụm ký tự. Một cụm hiển thị có thể gồm nhiều điểm mã; số đơn vị mã của từng điểm không thể tự cho biết ranh giới cụm.

## 8. Chọn thứ tự kiểm tra theo yêu cầu

Nếu chỉ cần biết một số có thuộc miền điểm mã Unicode, dùng `isValidCodePoint`.

Nếu đầu vào phải là một giá trị vô hướng để biểu diễn độc lập, dùng kiểm tra miền rồi loại `0xD800–0xDFFF`, như `unitsForScalar`.

Nếu chỉ xử lý ký tự bổ sung, `isSupplementaryCodePoint` là điều kiện trực tiếp.

Nếu cần tính chỗ chứa UTF-16 cho dữ liệu đã được chấp nhận, dùng `charCount` sau bước xác thực tương ứng. Không dùng một con số độ rộng để quyết định thay cho chính sách dữ liệu.

## 9. Tự kiểm tra

1. Với `cp = 0x110000`, tại sao `isSupplementaryCodePoint` là `false` nhưng `charCount` lại bằng 2?
2. Với `cp = 0xD800`, kiểm tra nào cần bổ sung nếu yêu cầu là giá trị vô hướng?
3. Có thể dùng `!isSupplementaryCodePoint(cp)` làm điều kiện duy nhất để ép về `char` không?
4. Ba điểm mã bổ sung hợp lệ cần tổng cộng bao nhiêu đơn vị mã UTF-16?

Đối chiếu:

1. Hai hàm có trách nhiệm khác nhau: một hàm kiểm tra cả hai biên của vùng bổ sung, hàm kia chỉ so với ngưỡng `0x10000`.
2. Loại bỏ vùng surrogate `0xD800–0xDFFF` sau khi kiểm tra miền.
3. Không; phải xác thực miền và xác định đúng yêu cầu trước.
4. Sáu đơn vị mã; kết quả này không cho biết số byte UTF-8 hay số cụm ký tự.
