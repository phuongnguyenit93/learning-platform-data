# Character.toString(int) và Unicode code point (Java 11)

Trong Java 11, `Character.toString(int codePoint)` tạo một `String` biểu diễn **một Unicode code point**. Phương thức này được bổ sung ở **Java 11** và vẫn hữu ích trong Java hiện nay, đặc biệt với ký tự nằm ngoài Basic Multilingual Plane (BMP), chẳng hạn emoji 🚀 (U+1F680). Điểm quan trọng là **một code point không nhất thiết tương ứng một giá trị `char` của Java**.

Bài học thuộc chủ đề **Chuỗi Unicode**. Các ví dụ dùng API Java 11 vẫn được hỗ trợ và có thể biên dịch trên JDK đang được nhà cung cấp bảo trì (chẳng hạn JDK 25 LTS hoặc JDK 21 LTS nếu toolchain đã được kiểm chứng). Không cần cài một runtime Java 11 đã quá hạn cập nhật chỉ để học API này.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **Unicode code point**, **Unicode scalar value**, **UTF-16 code unit** và `char`.
2. Giải thích vì sao `Character.toString(0x1F680).length() == 2` dù chỉ biểu diễn **một code point**.
3. Sử dụng `Character.toString(int)` đúng cách, phân biệt nó với `Character.toString(char)`.
4. Truy xuất và duyệt chuỗi bằng `String.codePointAt`, `String.codePoints()`, `Character.charCount` và `String.codePointCount` mà không cắt đôi surrogate pair.
5. Kiểm tra giá trị hợp lệ, xử lý giá trị vượt phạm vi và nhận diện **surrogate code point** không phù hợp làm Unicode scalar value.
6. Nhận ra **code point count** và **số ký tự người dùng nhìn thấy** có thể khác nhau.

## 2. Bốn khái niệm cần tách bạch

| Khái niệm | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Unicode code point** | Một giá trị số trong khoảng `U+0000` đến `U+10FFFF`. | `U+0041` là chữ A, `U+1F680` là 🚀. |
| **Unicode scalar value** | Code point **trừ vùng surrogate** `U+D800..U+DFFF`. | `U+1F680` là scalar value; `U+D800` không phải. |
| **UTF-16 code unit** | Một đơn vị **16 bit** để mã hóa chuỗi UTF-16. | 🚀 cần **hai** code unit: `D83D DE80`. |
| **Java `char`** | Kiểu nguyên thủy 16 bit, chứa **một UTF-16 code unit**. | `'A'` nằm trong một `char`; 🚀 không thể nằm trọn trong một `char`. |

Java `String` biểu diễn văn bản theo các **UTF-16 code unit** khi truy cập qua các API như `length()` hoặc `charAt(index)`. Vì vậy:

- `String.length()` đếm **số đơn vị UTF-16**, không nhất thiết là số Unicode code point.
- `String.charAt(i)` lấy **một** đơn vị UTF-16, có thể là **một nửa của surrogate pair**.
- `String.codePointAt(i)` lấy một code point bắt đầu từ chỉ số UTF-16 `i`; nếu có cặp surrogate hợp lệ tại vị trí đó, phương thức kết hợp chúng thành một giá trị `int`.
- `String.codePointCount(begin, end)` đếm code point trong đoạn chỉ định; `begin` và `end` vẫn là **chỉ số UTF-16**.
- `Character.charCount(cp)` trả về **1** cho code point thuộc BMP hoặc **2** cho code point bổ sung (supplementary), giúp di chuyển chỉ số UTF-16 đúng bước.

### Vì sao phải có surrogate pair?

BMP bao gồm các vị trí `U+0000..U+FFFF` (ngoại trừ vùng surrogate không phải scalar value). Các ký tự có code point từ `U+10000` đến `U+10FFFF` được mã hóa trong UTF-16 bằng **hai `char`**: một **high surrogate** thuộc `D800..DBFF` và một **low surrogate** thuộc `DC00..DFFF`.

Ví dụ 🚀 có code point `U+1F680`; biểu diễn UTF-16 là:

```text
Unicode code point : U+1F680
UTF-16 high surrogate: U+D83D
UTF-16 low surrogate : U+DE80
String.length()     : 2
Số code point       : 1
```

Đó là cơ sở để hiểu `Character.toString(int)`.

## 3. API trọng tâm: `Character.toString(int codePoint)`

Chữ ký trong Java 11:

```java
public static String toString(int codePoint)
```

Phương thức nhận **một số nguyên `int` biểu diễn code point** và trả về `String`:

- Với code point trong BMP, chuỗi có `length() == 1` (một UTF-16 code unit).
- Với code point bổ sung, chuỗi có `length() == 2` (một cặp high/low surrogate).
- Nếu giá trị nhỏ hơn `0` hoặc lớn hơn `0x10FFFF`, phương thức ném `IllegalArgumentException`.
- Phương thức **không chuyển số sang các chữ số thập phân**. `Character.toString(65)` tạo `"A"`, trong khi `Integer.toString(65)` tạo `"65"`.
- Đầu vào thuộc vùng surrogate `U+D800..U+DFFF` vẫn nằm trong **khoảng code point được API này chấp nhận**, nhưng tạo chuỗi chứa **unpaired surrogate**, không phải Unicode scalar value hợp lệ để trao đổi văn bản thông thường; xem phần xác thực.

Ví dụ:

```java
String letter = Character.toString(0x0041);   // "A", length = 1
String rocket = Character.toString(0x1F680); // "🚀", length = 2
String digits = Integer.toString(65);        // "65", length = 2
```

Các nhận xét trong ví dụ là giải thích; hãy xem chương trình độc lập tiếp theo để tự chạy và đối chiếu kết quả.

### Phân biệt hai overload

| Lệnh gọi | Overload | Kết quả |
| --- | --- | --- |
| `Character.toString('A')` | `toString(char)` | Chuỗi `"A"`, dài một code unit |
| `Character.toString(0x0041)` | `toString(int)` | Chuỗi `"A"`, dài một code unit |
| `Character.toString(0x1F680)` | `toString(int)` | Chuỗi biểu diễn 🚀, dài hai code unit |
| `Character.toString(rocket.charAt(0))` | `toString(char)` | Chỉ high surrogate của 🚀, **không** phải ký tự 🚀 hoàn chỉnh |

**Quy tắc:** khi xử lý bất kỳ ký tự Unicode nào, kể cả ngoài BMP, hãy dùng **`int` code point**. Ép code point vượt BMP sang `char` sẽ mất thông tin; ép kiểu này không tạo ra surrogate pair đầy đủ.

## 4. Ví dụ chạy được: một code point nhưng hai `char`

Tạo tệp **`CodePointDemo.java`**:

```java
public class CodePointDemo {
    public static void main(String[] args) {
        int letterCodePoint = 0x0041;
        int rocketCodePoint = 0x1F680;

        String letter = Character.toString(letterCodePoint);
        String rocket = Character.toString(rocketCodePoint);

        System.out.println("Letter: " + letter);
        System.out.println("Letter UTF-16 units: " + letter.length());
        System.out.printf("Rocket code point: U+%06X%n",
                rocket.codePointAt(0));
        System.out.println("Rocket UTF-16 units: " + rocket.length());
        System.out.printf("UTF-16 pair: %04X %04X%n",
                (int) rocket.charAt(0), (int) rocket.charAt(1));
        System.out.println("Rocket code point count: " +
                rocket.codePointCount(0, rocket.length()));
        System.out.println("Supplementary: " +
                Character.isSupplementaryCodePoint(rocketCodePoint));
        System.out.println("Equivalent to toChars: " +
                rocket.equals(new String(
                        Character.toChars(rocketCodePoint))));
    }
}
```

Dùng **JDK được hỗ trợ, có `javac` hỗ trợ `--release 11`**:

```sh
javac --release 11 CodePointDemo.java
java CodePointDemo
```

**Stdout chính xác:**

```text
Letter: A
Letter UTF-16 units: 1
Rocket code point: U+01F680
Rocket UTF-16 units: 2
UTF-16 pair: D83D DE80
Rocket code point count: 1
Supplementary: true
Equivalent to toChars: true
```

Ví dụ cố ý in mã thập lục phân thay vì phụ thuộc khả năng hiển thị emoji của terminal. Nếu thử `System.out.println(rocket)`, ký hiệu 🚀 sẽ hiện khi console, font và đường truyền văn bản hỗ trợ nó.

**Giải thích:**

1. `0x0041` là chữ A, nằm trong BMP, do đó `letter.length() == 1`.
2. `0x1F680` là code point bổ sung; `Character.toString(int)` tự tạo **cặp surrogate đúng**, không yêu cầu lập trình viên tính thủ công.
3. `rocket.length() == 2` vì `length()` đếm code unit; `rocket.codePointCount(0, rocket.length()) == 1` vì hai code unit hợp lại thành một code point.
4. `rocket.charAt(0)` trả về high surrogate `D83D` và `rocket.charAt(1)` trả về low surrogate `DE80`. In riêng một phần surrogate không phải biểu diễn ký tự Unicode hoàn chỉnh.
5. `Character.toChars(int)` là API vẫn hợp lệ: nó trả về `char[]` UTF-16, còn `Character.toString(int)` trả trực tiếp một `String`. Dùng cách nào tùy kiểu dữ liệu đầu ra bạn cần.

**Điểm kiểm tra:** cùng một ký tự có thể có `length() == 2` nhưng `codePointCount(...) == 1`. Không lấy `String.length()` để suy ra số code point nếu chuỗi có ký tự ngoài BMP.

## 5. Duyệt chuỗi đúng theo code point

Xét chuỗi `A🚀B`:

- `A` chiếm 1 code unit.
- 🚀 chiếm 2 code unit.
- `B` chiếm 1 code unit.

Tổng cộng **4 code unit** nhưng chỉ **3 code point**. Duyệt từng `char` sẽ gặp 4 phần tử, vì cặp surrogate của 🚀 bị tách làm hai.

Tạo tệp **`CodePointWalk.java`**:

```java
import java.util.stream.Collectors;

public class CodePointWalk {
    public static void main(String[] args) {
        String sample = "A" + Character.toString(0x1F680) + "B";

        System.out.println("UTF-16 length: " + sample.length());
        System.out.println("Code points: " +
                sample.codePointCount(0, sample.length()));

        int index = 0;
        while (index < sample.length()) {
            int codePoint = sample.codePointAt(index);
            int units = Character.charCount(codePoint);

            System.out.printf("index=%d codePoint=U+%04X units=%d%n",
                    index, codePoint, units);
            index += units;
        }

        String rebuilt = sample.codePoints()
                .mapToObj(Character::toString)
                .collect(Collectors.joining());

        System.out.println("Rebuilt equals original: " +
                sample.equals(rebuilt));
    }
}
```

Chạy:

```sh
javac --release 11 CodePointWalk.java
java CodePointWalk
```

**Stdout chính xác:**

```text
UTF-16 length: 4
Code points: 3
index=0 codePoint=U+0041 units=1
index=1 codePoint=U+1F680 units=2
index=3 codePoint=U+0042 units=1
Rebuilt equals original: true
```

### Vì sao chỉ số nhảy từ 1 sang 3?

`String.codePointAt(index)` nhận **chỉ số của UTF-16 code unit đầu tiên**, không nhận thứ tự code point. Ở `index=1`, giá trị là 🚀 cần **hai** code unit, vì thế phải cộng `Character.charCount(codePoint) == 2` để đi đến `index=3`.

### Khi nào dùng `String.codePoints()`?

`sample.codePoints()` trả về `IntStream` các code point, rất tiện khi bạn muốn **lọc, ánh xạ, thống kê hoặc tái tạo văn bản**. Đoạn `mapToObj(Character::toString)` cho thấy cách chuyển từng `int` code point thành `String` bằng API Java 11.

Với lượng dữ liệu lớn, nếu mục tiêu chỉ là **ghép code point thành chuỗi**, dùng `StringBuilder.appendCodePoint(int)` trực tiếp cũng phù hợp và tránh tạo một `String` riêng cho mỗi phần tử:

```java
StringBuilder builder = new StringBuilder();
sample.codePoints().forEach(cp -> builder.appendCodePoint(cp));
String copied = builder.toString();
System.out.println(copied.equals(sample)); // true
```

Đây là **đoạn mã đặt bên trong phương thức** nơi biến `sample` đã tồn tại, không phải chương trình Java độc lập. `StringBuilder.appendCodePoint` vẫn có giá trị trong Java hiện nay và xử lý đúng surrogate pair khi append một code point bổ sung.

## 6. Giá trị code point hợp lệ và Unicode scalar value

`Character.toString(int)` chỉ ném `IllegalArgumentException` khi giá trị **nằm ngoài** miền code point Java chấp nhận: `0..0x10FFFF`.

Tuy nhiên, miền đó có vùng `U+D800..U+DFFF` dành riêng cho **UTF-16 surrogate**. Đây là chi tiết rất dễ gây lỗi:

- `Character.isValidCodePoint(0xD800)` trả về `true` vì `0xD800` nằm trong phạm vi số nguyên code point.
- `0xD800` **không phải Unicode scalar value**, nên không đại diện một ký tự Unicode bình thường độc lập.
- `Character.toString(0xD800)` không bắt buộc ném lỗi; nó tạo chuỗi chứa **unpaired surrogate**. Chuỗi như vậy có thể gây vấn đề khi encode, trao đổi dữ liệu hoặc hiển thị.
- Nếu dữ liệu dùng làm **văn bản Unicode trao đổi bên ngoài**, hãy yêu cầu **scalar value**: code point hợp lệ **và không nằm trong vùng surrogate**.

### Ví dụ kiểm tra đúng điều kiện

Tạo tệp **`CodePointValidation.java`**:

```java
public class CodePointValidation {
    private static boolean isUnicodeScalarValue(int codePoint) {
        return Character.isValidCodePoint(codePoint)
                && !(codePoint >= Character.MIN_SURROGATE
                && codePoint <= Character.MAX_SURROGATE);
    }

    public static void main(String[] args) {
        System.out.println("U+1F680 valid: " +
                Character.isValidCodePoint(0x1F680));
        System.out.println("U+D800 valid: " +
                Character.isValidCodePoint(0xD800));
        System.out.println("U+D800 scalar: " +
                isUnicodeScalarValue(0xD800));
        System.out.println("U+110000 valid: " +
                Character.isValidCodePoint(0x110000));

        try {
            Character.toString(0x110000);
        } catch (IllegalArgumentException e) {
            System.out.println("Invalid code point rejected");
        }
    }
}
```

Chạy:

```sh
javac --release 11 CodePointValidation.java
java CodePointValidation
```

**Stdout chính xác:**

```text
U+1F680 valid: true
U+D800 valid: true
U+D800 scalar: false
U+110000 valid: false
Invalid code point rejected
```

**Không nhầm giữa ba mức kiểm tra:**

1. **Nằm trong miền số code point:** `Character.isValidCodePoint(cp)`.
2. **Là Unicode scalar value:** điều kiện (1) **và không thuộc surrogate range**.
3. **Là ký tự được định nghĩa trong một phiên bản Unicode cụ thể:** kiểm tra bổ sung như `Character.isDefined(cp)`, chịu ảnh hưởng dữ liệu Unicode của bản JDK. Không phải mọi scalar value đều là ký tự đã được gán; không cần yêu cầu `isDefined` cho mọi ứng dụng.

Nếu chuỗi đầu vào chứa surrogate đơn lẻ, `String.codePoints()` và `String.codePointCount(...)` vẫn có thể ghi nhận giá trị đó như **một phần tử**; chúng **không tự sửa dữ liệu UTF-16 lỗi**. Các ứng dụng nhận văn bản bên ngoài cần quy tắc xử lý đầu vào lỗi hoặc chuẩn hóa rõ ràng theo giao thức.

## 7. Code point không đồng nghĩa ký tự người dùng nhìn thấy

Unicode hỗ trợ **combining marks**, **variation selectors**, **zero-width joiner (ZWJ)** và nhiều cơ chế ghép ký tự. Một **grapheme cluster** (cụm ký tự được người dùng nhận như một ký tự) có thể gồm **nhiều code point**.

Ví dụ chữ “é” có thể biểu diễn theo hai cách:

- Dạng precomposed `U+00E9`: một code point.
- Dạng decomposed `U+0065 U+0301`: chữ `e` và dấu sắc kết hợp, gồm hai code point.

Hai chuỗi có thể hiển thị rất giống nhau nhưng khác mã Unicode và khác kết quả `equals` nếu chưa chuẩn hóa. Tạo **`NormalizationDemo.java`**:

```java
import java.text.Normalizer;

public class NormalizationDemo {
    public static void main(String[] args) {
        String composed = "\u00E9";
        String decomposed = "e\u0301";

        System.out.println("Composed code points: " +
                composed.codePointCount(0, composed.length()));
        System.out.println("Decomposed code points: " +
                decomposed.codePointCount(0, decomposed.length()));
        System.out.println("Raw equals: " +
                composed.equals(decomposed));
        System.out.println("After NFC equals: " +
                composed.equals(
                        Normalizer.normalize(decomposed,
                                Normalizer.Form.NFC)));
    }
}
```

Chạy:

```sh
javac --release 11 NormalizationDemo.java
java NormalizationDemo
```

**Stdout chính xác:**

```text
Composed code points: 1
Decomposed code points: 2
Raw equals: false
After NFC equals: true
```

`Normalizer` (API có trong Java 11 và còn được sử dụng) giải quyết **chuẩn hóa biểu diễn Unicode**, không phải mọi vấn đề so sánh ngôn ngữ, font hoặc xác định grapheme cluster. Ví dụ này chứng minh **số code point cũng không phải số ký tự hiển thị**. Nếu sản phẩm cần đặt con trỏ, cắt chuỗi theo ký tự người dùng nhìn thấy, đếm emoji ghép hoặc xử lý ngôn ngữ chuyên sâu, cần một giải pháp **phân đoạn grapheme theo chuẩn Unicode hiện hành** được kiểm chứng cho yêu cầu đó; không chỉ dùng `codePointCount`.

## 8. Chọn API cho đúng bài toán

| Mục đích | API phù hợp | Lưu ý |
| --- | --- | --- |
| Tạo `String` từ một code point | `Character.toString(int)` | Bổ sung ở Java 11, trả 1 hoặc 2 UTF-16 code unit. |
| Tạo `String` từ một `char` | `Character.toString(char)` | Chỉ chuyển một code unit; không ghép surrogate pair. |
| Tạo mảng UTF-16 từ code point | `Character.toChars(int)` | Trả `char[]` có 1 hoặc 2 phần tử. |
| Ghép code point vào chuỗi đang xây dựng | `StringBuilder.appendCodePoint(int)` | Hữu ích khi xử lý nhiều code point liên tiếp. |
| Lấy code point tại chỉ số UTF-16 | `String.codePointAt(index)` | Cẩn thận ranh giới surrogate pair và index. |
| Duyệt code point | `String.codePoints()` | Trả `IntStream`, không bảo đảm dữ liệu đầu vào đã hợp lệ. |
| Đếm code point trong đoạn | `String.codePointCount(begin, end)` | Đối số begin/end vẫn là chỉ số UTF-16. |
| Bước qua một code point | `Character.charCount(cp)` hoặc `String.offsetByCodePoints(...)` | Tránh dùng `index++` khi duyệt chuỗi có supplementary character. |
| Kiểm tra miền code point Java | `Character.isValidCodePoint(cp)` | Không loại bỏ vùng surrogate. |
| Kiểm tra Unicode scalar value | `isValidCodePoint(cp)` **và** ngoài `D800..DFFF` | Cần khi chỉ chấp nhận văn bản Unicode scalar. |
| Chuẩn hóa dạng biểu diễn Unicode | `Normalizer.normalize(text, Normalizer.Form.NFC)` | Dùng theo hợp đồng dữ liệu; không tương đương xử lý grapheme. |

### Hiểu đúng hiệu năng và an toàn

- Nếu đã có `int codePoint` và cần `String` nhỏ biểu diễn duy nhất ký tự đó, `Character.toString(int)` là lời gọi trực tiếp, dễ đọc.
- Nếu đang lặp qua hàng nghìn code point để tạo văn bản, `StringBuilder.appendCodePoint` tránh tạo nhiều `String` trung gian.
- Tránh `char` hoặc `String.substring(i, i + 1)` để tách ký tự nếu `i` có thể trỏ vào surrogate pair; có nguy cơ tạo chuỗi với unpaired surrogate.
- Với đầu vào không tin cậy, xác thực phạm vi, surrogate, độ dài và quy tắc giao thức riêng; `Character.toString(int)` tự nó không kiểm chứng toàn bộ tính hợp lệ/ngữ nghĩa của văn bản.

## 9. Sai lầm thường gặp

**Sai lầm 1: “Một ký tự Java luôn có `length() == 1`.”** Không đúng với supplementary character trong UTF-16. Ví dụ 🚀 có `length() == 2` nhưng một code point.

**Sai lầm 2: “`char` lưu được mọi Unicode code point.”** `char` chỉ chứa một code unit 16 bit. Để biểu diễn mọi code point, dùng `int`; khi đưa vào `String` có thể cần hai code unit.

**Sai lầm 3: “`Character.toString(int)` giống `Integer.toString(int)`.”** Không. `Character.toString(65)` là `"A"`, còn `Integer.toString(65)` là `"65"`.

**Sai lầm 4: “`isValidCodePoint` bảo đảm văn bản Unicode scalar hợp lệ.”** Không. Vùng surrogate được xem là hợp lệ về miền số, nhưng không phải scalar value.

**Sai lầm 5: “`codePointCount` chính là số grapheme.”** Không. Combining marks và emoji ghép có thể khiến một grapheme gồm nhiều code point.

**Sai lầm 6: “Duyệt `String` bằng `charAt(i)` luôn trả một ký tự hoàn chỉnh.”** Không. `charAt` có thể trả một nửa surrogate pair. Dùng `codePointAt` với `charCount`, hoặc `codePoints()` khi cần code point.

**Sai lầm 7: “Nếu `toString(int)` không ném lỗi thì ký tự chắc chắn in được.”** Không. Code point có thể là điều khiển, chưa được gán, không được font hỗ trợ hoặc thuộc surrogate range. Khả năng hiển thị còn phụ thuộc font, console, encoding và phiên bản Unicode.

## 10. Bài tập thực hành

### Bài 1 — Phân biệt code point và code unit

Dự đoán:

```java
String a = Character.toString(0x0041);
String b = Character.toString(0x1F680);

System.out.println(a.length());
System.out.println(b.length());
System.out.println(b.codePointCount(0, b.length()));
```

Đây là **đoạn lệnh đặt bên trong `main`**, không phải một lớp độc lập. Kết quả theo thứ tự là:

```text
1
2
1
```

Giải thích bằng thuật ngữ **BMP**, **supplementary code point** và **UTF-16 surrogate pair**.

### Bài 2 — Duyệt không làm hỏng Unicode

Với chuỗi `"X" + Character.toString(0x1F680) + "Y"`, in từng code point dưới dạng `U+XXXX`, mỗi dòng một giá trị. Kết quả mong đợi: `U+0058`, `U+1F680`, `U+0059`. So sánh hai cách: vòng lặp `codePointAt/charCount` và `String.codePoints()`.

### Bài 3 — Xác thực Unicode scalar

Viết hàm `isUnicodeScalarValue(int cp)` rồi thử các giá trị:

| Đầu vào | `isValidCodePoint` | Unicode scalar? |
| --- | --- | --- |
| `0x0041` | `true` | `true` |
| `0x1F680` | `true` | `true` |
| `0xD800` | `true` | `false` |
| `0x10FFFF` | `true` | `true` |
| `0x110000` | `false` | `false` |
| `-1` | `false` | `false` |

Giải thích vì sao muốn **Unicode scalar value** không thể chỉ kiểm tra `Character.isValidCodePoint`.

### Bài 4 — Code point count khác grapheme

Chạy `NormalizationDemo.java`, lý giải sự khác nhau giữa hai chuỗi Unicode “é”, rồi thử bổ sung một chuỗi gồm chữ và combining mark khác. Nêu lý do tại sao `Normalizer` và phân đoạn grapheme giải quyết **hai vấn đề khác nhau**.

### Checklist hoàn thành

- [ ] Đã chạy các chương trình độc lập trên JDK còn nhận bản vá, compiler dùng `--release 11`.
- [ ] Hiểu `Character.toString(int)` được bổ sung ở Java 11 và trả `String` có 1 hoặc 2 UTF-16 code unit.
- [ ] Đọc đúng mã `U+1F680`, cặp `D83D DE80`, `length() == 2` và `codePointCount(...) == 1`.
- [ ] Không cắt chuỗi ở giữa surrogate pair; dùng `codePoints()`/`codePointAt` hợp lý.
- [ ] Phân biệt code point hợp lệ theo miền số, Unicode scalar và grapheme cluster.
- [ ] Biết khi nào dùng `Character.toString(int)`, `Character.toChars(int)` hoặc `StringBuilder.appendCodePoint(int)`.

## 11. Tài liệu tham khảo

1. [Java SE 11 — `Character` API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/Character.html): `toString(int)` (Since 11), `toString(char)`, `isValidCodePoint`, `charCount`, `toChars` và surrogate pair.
2. [Java SE 11 — `String` API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html): `length`, `charAt`, `codePointAt`, `codePointCount`, `codePoints` và `offsetByCodePoints`.
3. [Java SE 11 — `StringBuilder` API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/StringBuilder.html): `appendCodePoint(int)`.
4. [Java SE 11 — `Normalizer` API](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/text/Normalizer.html): các biểu diễn normalization NFC/NFD.
5. [Unicode Consortium — Glossary](https://www.unicode.org/glossary/): phân biệt code point, scalar value, code unit, grapheme cluster.

**Kết luận áp dụng:** `Character.toString(int)` chuyển **một code point** thành `String` đúng với UTF-16, kể cả code point cần **hai `char`**. Khi thao tác chuỗi Unicode, chọn API theo **code point** nếu cần xử lý giá trị Unicode hoàn chỉnh, kiểm tra thêm **scalar value** khi nhận dữ liệu từ bên ngoài, và nhớ rằng **grapheme cluster** có thể chứa nhiều code point.