# Chuỗi rỗng khi hai biên bằng nhau: `String.substring(beginIndex, endIndex)`

Khi trích xuất một đoạn của `String` trong Java, hai tham số `beginIndex` và `endIndex` xác định phạm vi ký tự cần lấy. Nếu **hai biên bằng nhau và cùng nằm trong phạm vi hợp lệ**, đoạn được chọn có độ dài bằng 0, nên `substring(beginIndex, endIndex)` trả về **chuỗi rỗng `""`**. Đây là hành vi đúng theo hợp đồng API, không phải lỗi, cũng không phải `null`.

Ví dụ:

```java
String text = "Java";
String empty = text.substring(2, 2);

System.out.println(empty.length());  // 0
System.out.println(empty.isEmpty()); // true
System.out.println(empty.equals("")); // true
```

`substring(2, 2)` không chọn ký tự nào, dù vị trí 2 là một ranh giới nằm giữa chuỗi có nội dung. Cần phân biệt điều này với một phạm vi **không hợp lệ** như `substring(5, 5)` trên `"Java"` dài 4: hai số bằng nhau vẫn không cứu được chỉ số nằm ngoài giới hạn.

## 1. Quy tắc của hai biên: bắt đầu bao gồm, kết thúc không bao gồm

Chữ ký phương thức:

```java
public String substring(int beginIndex, int endIndex)
```

Phương thức lấy các UTF-16 code unit tại các chỉ số thuộc khoảng **`[beginIndex, endIndex)`**:

- `beginIndex` là chỉ số đầu, **được tính vào** kết quả.
- `endIndex` là chỉ số kết thúc, **không được tính vào** kết quả.
- Số UTF-16 code unit trong kết quả là `endIndex - beginIndex`.
- Phải thỏa mãn đồng thời `0 <= beginIndex <= endIndex <= text.length()`.

Với chuỗi `"Java"`, các ký tự có chỉ số 0, 1, 2 và 3, nhưng có **năm vị trí biên** từ 0 đến 4:

```text
Vị trí biên:  0   1   2   3   4
              | J | a | v | a |
Chỉ số char:    0   1   2   3
```

Ví dụ các phạm vi:

| Lời gọi | Phạm vi lấy | Kết quả | Độ dài |
| --- | --- | --- | ---: |
| `text.substring(0, 2)` | `[0, 2)` | `"Ja"` | 2 |
| `text.substring(2, 4)` | `[2, 4)` | `"va"` | 2 |
| `text.substring(1, 3)` | `[1, 3)` | `"av"` | 2 |
| `text.substring(0, 0)` | `[0, 0)` | `""` | 0 |
| `text.substring(2, 2)` | `[2, 2)` | `""` | 0 |
| `text.substring(4, 4)` | `[4, 4)` | `""` | 0 |

Khi `beginIndex == endIndex`, khoảng nửa mở có **không phần tử**, nên không có ký tự nào được đưa vào chuỗi kết quả. Quy tắc này nhất quán với cách Java mô tả các đoạn bằng chỉ số bắt đầu bao gồm và kết thúc loại trừ.

## 2. Ví dụ hoàn chỉnh: mọi vị trí biên hợp lệ đều có thể tạo chuỗi rỗng

Tạo tệp `EmptySubstringDemo.java`:

```java
public class EmptySubstringDemo {
    public static void main(String[] args) {
        String text = "Java";

        String atStart = text.substring(0, 0);
        String inMiddle = text.substring(2, 2);
        String atEnd = text.substring(text.length(), text.length());
        String fromEnd = text.substring(text.length());

        System.out.println("start=[" + atStart + "]");
        System.out.println("middle=[" + inMiddle + "]");
        System.out.println("end=[" + atEnd + "]");
        System.out.println("fromEnd=[" + fromEnd + "]");
        System.out.println("length=" + inMiddle.length());
        System.out.println("isEmpty=" + inMiddle.isEmpty());
        System.out.println("equalsEmpty=" + inMiddle.equals(""));
    }
}
```

Biên dịch/chạy trên JDK 17 trở lên:

```bash
javac -encoding UTF-8 EmptySubstringDemo.java
java EmptySubstringDemo
```

Kết quả chính xác:

```text
start=[]
middle=[]
end=[]
fromEnd=[]
length=0
isEmpty=true
equalsEmpty=true
```

Dấu ngoặc vuông trong kết quả do chương trình **chủ động nối vào** để nhìn thấy ranh giới; chúng không nằm trong chuỗi rỗng. Nếu viết `System.out.println(inMiddle);`, chương trình chỉ in một dòng trống.

Các trường hợp `atStart`, `inMiddle`, `atEnd` đều trả về giá trị bằng `""`. Đồng thời, overload một tham số `substring(beginIndex)` hiểu rằng lấy từ `beginIndex` đến hết chuỗi; do đó gọi `text.substring(text.length())` cũng trả về chuỗi rỗng.

## 3. Hai biên bằng nhau vẫn phải nằm trong phạm vi hợp lệ

Điều kiện quan trọng là:

```text
0 <= beginIndex <= endIndex <= text.length()
```

Nếu `beginIndex == endIndex == k` thì lời gọi hợp lệ **chỉ khi** `0 <= k <= text.length()`.

| Ví dụ với `text = "Java"`, `length() = 4` | Hợp lệ? | Vì sao |
| --- | --- | --- |
| `substring(0, 0)` | Có | Cả hai biên đều là 0, nằm trong [0, 4] |
| `substring(2, 2)` | Có | Ranh giới số 2 nằm trong [0, 4] |
| `substring(4, 4)` | Có | Biên cuối 4 bằng `length()` và được cho phép |
| `substring(-1, -1)` | Không | Biên âm |
| `substring(5, 5)` | Không | Biên 5 lớn hơn `length()` |
| `substring(3, 2)` | Không | Biên bắt đầu lớn hơn biên kết thúc |

Với tham số không hợp lệ, `String.substring` ném ngoại lệ `StringIndexOutOfBoundsException` (thuộc họ `IndexOutOfBoundsException`). Không nên phụ thuộc vào nội dung thông báo của ngoại lệ vì cách mô tả có thể khác theo phiên bản hoặc triển khai JDK.

Tệp `EmptyRangeValidation.java` minh họa hành vi thành công/thất bại mà không phụ thuộc thông báo ngoại lệ:

```java
public class EmptyRangeValidation {
    public static void main(String[] args) {
        String text = "Java";
        int[][] ranges = {
            {0, 0},
            {2, 2},
            {4, 4},
            {-1, -1},
            {5, 5},
            {3, 2}
        };

        for (int[] range : ranges) {
            int begin = range[0];
            int end = range[1];

            try {
                String part = text.substring(begin, end);
                System.out.printf("[%d,%d) -> length=%d%n",
                        begin, end, part.length());
            } catch (IndexOutOfBoundsException ex) {
                System.out.printf("[%d,%d) -> invalid%n", begin, end);
            }
        }
    }
}
```

Lưu đúng tên tệp rồi chạy:

```bash
javac -encoding UTF-8 EmptyRangeValidation.java
java EmptyRangeValidation
```

Kết quả:

```text
[0,0) -> length=0
[2,2) -> length=0
[4,4) -> length=0
[-1,-1) -> invalid
[5,5) -> invalid
[3,2) -> invalid
```

Trường hợp `[4,4)` hợp lệ dù chuỗi chỉ có các chỉ số **ký tự** từ 0 đến 3, vì `endIndex` biểu diễn **vị trí biên ngay sau ký tự cuối**. Ngược lại, `[5,5)` không phải biên tồn tại trong chuỗi dài 4.

## 4. Chuỗi nguồn rỗng cũng có một phạm vi trích xuất hợp lệ

Với `String emptySource = "";`, `emptySource.length() == 0`. Phạm vi hợp lệ duy nhất của overload hai tham số là `[0, 0)`:

```java
String emptySource = "";

System.out.println(emptySource.substring(0, 0).isEmpty()); // true
System.out.println(emptySource.substring(0).isEmpty());    // true
// emptySource.substring(1, 1); // Ngoại lệ vì vượt length() = 0
```

Các lệnh trên là đoạn minh họa nằm trong một phương thức Java, không phải chương trình độc lập. Trường hợp nguồn rỗng **không có ngoại lệ đặc biệt**: quy tắc biên và điều kiện hợp lệ vẫn giữ nguyên như với chuỗi không rỗng.

## 5. Chuỗi rỗng không phải `null` và không phải chuỗi chứa dấu cách

Cần phân biệt ba giá trị:

- `""`: đối tượng `String` có độ dài `0`, `isEmpty() == true`.
- `" "`: chuỗi chứa một dấu cách thông thường, `length() == 1`, `isEmpty() == false`.
- `null`: tham chiếu **không trỏ đến đối tượng `String` nào**; không thể gọi `length()` hoặc `isEmpty()` trực tiếp trên tham chiếu đó.

`substring(k, k)` với `k` hợp lệ luôn trả về một giá trị kiểu `String` có nội dung rỗng. Phương thức không trả về `null` để diễn tả “không chọn ký tự”.

Ví dụ:

```java
String text = "A B";
String part = text.substring(1, 1);

System.out.println(part == null);   // false
System.out.println(part.length());  // 0
System.out.println(part.isEmpty()); // true

String space = text.substring(1, 2);
System.out.println(space.length());  // 1
System.out.println(space.isEmpty()); // false
```

Đoạn trên là các lệnh minh họa đặt trong một phương thức. Mặc dù `part` và `space` có thể đều trông “không có chữ” khi in trên console, chúng có giá trị và độ dài khác nhau.

Nếu cần so sánh nội dung trích xuất với chuỗi rỗng, dùng `part.isEmpty()` hoặc `part.equals("")`. Không dùng `part == ""` để dựa vào danh tính đối tượng: kể cả khi một triển khai có thể tái sử dụng tham chiếu đến chuỗi rỗng, hợp đồng cần quan tâm là **nội dung bằng nhau**.

## 6. Ứng dụng: trích xuất phần trước/sau dấu phân cách

Chuỗi rỗng thường là kết quả **hợp lệ** khi dấu phân cách nằm ngay đầu hoặc cuối dữ liệu. Ví dụ chuỗi dạng `key=value`:

- `"=value"` có phần khóa rỗng ở trước dấu `=`.
- `"key="` có phần giá trị rỗng ở sau dấu `=`.
- `"="` có cả hai phần rỗng.
- `"name=Lan"` có cả khóa và giá trị không rỗng.

Tệp `DelimiterExtraction.java`:

```java
public class DelimiterExtraction {
    static void showParts(String line) {
        int separator = line.indexOf('=');

        if (separator < 0) {
            System.out.println("No separator: " + line);
            return;
        }

        String key = line.substring(0, separator);
        String value = line.substring(separator + 1, line.length());

        System.out.println("key=[" + key + "], value=[" + value + "]");
    }

    public static void main(String[] args) {
        showParts("name=Lan");
        showParts("=value");
        showParts("key=");
        showParts("=");
        showParts("missing");
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 DelimiterExtraction.java
java DelimiterExtraction
```

Đầu ra:

```text
key=[name], value=[Lan]
key=[], value=[value]
key=[key], value=[]
key=[], value=[]
No separator: missing
```

Giải thích kỹ hai trường hợp quan trọng:

- Khi `line = "=value"`, `separator == 0` nên `line.substring(0, separator)` chính là `substring(0, 0)`: **khóa rỗng**, không phải lỗi.
- Khi `line = "key="`, `separator == line.length() - 1` nên phần giá trị bắt đầu tại `separator + 1 == line.length()`; hai biên bằng nhau tại cuối chuỗi nên giá trị rỗng.

Kiểm tra `separator < 0` là cần thiết: `indexOf('=')` trả về `-1` nếu không tìm thấy; dùng trực tiếp giá trị này làm biên cho `substring` có thể gây lỗi hoặc phân tích dữ liệu sai. Với yêu cầu nghiệp vụ mà khóa/giá trị **không được phép rỗng**, cần xác thực thêm sau khi trích xuất; không nên coi chuỗi rỗng tự động là ngoại lệ API.

## 7. Áp dụng trong thuật toán dùng cửa sổ [begin, end)

Nhiều thuật toán quét văn bản lưu một cặp chỉ số `begin` và `end`, trong đó `begin` là nơi bắt đầu của đoạn hiện tại và `end` là vị trí ngay sau ký tự cuối đã duyệt. Khi hai chỉ số bằng nhau, cửa sổ có độ dài 0.

Ví dụ, một hàm lấy đoạn giữa hai vị trí biên:

```java
static String extractWindow(String text, int begin, int end) {
    return text.substring(begin, end);
}
```

Với `extractWindow("ABCDE", 3, 3)`, kết quả là `""`. Không cần viết điều kiện riêng `if (begin == end) return "";` để tránh ngoại lệ: nếu hai biên **hợp lệ**, `substring` đã xử lý đúng. Tuy nhiên, nếu thuật toán mong đợi **ít nhất một ký tự**, điều kiện `begin == end` có thể báo hiệu rằng cửa sổ chưa có dữ liệu; quy tắc nghiệp vụ phải được kiểm tra riêng.

Những tình huống hay gặp:

1. **Cắt phần tiền tố** bằng `substring(0, boundary)`: nếu `boundary == 0`, tiền tố rỗng.
2. **Cắt phần hậu tố** bằng `substring(boundary, length())`: nếu `boundary == length()`, hậu tố rỗng.
3. **Cắt giữa hai mốc** bằng `substring(left, right)`: nếu hai mốc trùng nhau, không có ký tự giữa chúng.
4. **Bước lặp hoặc quét không tiêu thụ ký tự mới**: cửa sổ `[cursor, cursor)` có thể hợp lệ nhưng cần quyết định thuật toán nên tiếp tục hay dừng để tránh lặp vô hạn.

Điểm cuối rất quan trọng: một `substring` trả chuỗi rỗng không tự di chuyển chỉ số `cursor`. Nếu thiết kế vòng lặp dựa vào việc mỗi vòng phải tiến ít nhất một ký tự, cần đảm bảo phần cập nhật chỉ số phù hợp.

## 8. Chỉ số của `substring` tính theo UTF-16 code unit

Một phạm vi rỗng `[k, k)` không lấy bất kỳ code unit nào, **kể cả khi `k` nằm giữa hai nửa surrogate pair**. Chẳng hạn, với `"A😀B"`, `substring(2, 2)` vẫn trả `""`, trong khi `substring(1, 2)` chỉ lấy nửa đầu emoji và không biểu diễn một code point hoàn chỉnh.

Việc hai biên bằng nhau giải quyết câu hỏi “có dữ liệu nào trong đoạn?”; khi đoạn **không rỗng** và chứa Unicode bổ sung, phải chọn biên code point hoặc grapheme thích hợp cho nghiệp vụ.

## 9. `substring` với `subSequence` và đoạn rỗng

`String` triển khai `CharSequence`, nên `text.subSequence(k, k)` cũng cho dãy có độ dài `0` với `k` hợp lệ. Ví dụ:

```java
String text = "Java";
CharSequence empty = text.subSequence(3, 3);
System.out.println(empty.isEmpty()); // true
```

`substring` khai báo trả về `String`, còn `subSequence` khai báo trả về `CharSequence`. Đây là khác biệt về kiểu API; với nguồn `String`, cả hai cùng diễn đạt đoạn rỗng theo quy tắc nửa mở.

## 10. Lỗi thường gặp

- **`substring(k, k)` luôn hợp lệ?** Không: `k` vẫn phải nằm trong `[0, length()]`. `substring(5, 5)` trên `"Java"` dài bốn code unit vẫn ném ngoại lệ.
- **Đoạn rỗng đồng nghĩa `null`?** Không: `""` có `length() == 0`, gọi được `isEmpty()`; `null` không phải đối tượng `String`.
- **Một dấu cách có rỗng không?** Không: `" "` có độ dài một và `isEmpty() == false`. `isBlank()` hỏi một câu khác về nội dung khoảng trắng.
- **Có nên so sánh với `== ""`?** Không: `==` so identity, dùng `isEmpty()` hoặc `equals("")` cho nội dung.
- **Vòng lặp không tiến do kết quả rỗng?** `substring` không di chuyển con trỏ; thuật toán phải bảo đảm tiến độ hoặc quy tắc dừng riêng.

## 11. Câu hỏi tự kiểm tra

**Câu 1.** Với `String s = "abc";`, kết quả của `s.substring(1, 1)` và `s.substring(3, 3)` là gì?

**Đáp án:** Cả hai là `""`, vì hai biên trùng nhau và `1` lẫn `3` đều nằm trong phạm vi biên hợp lệ `[0, 3]`.

**Câu 2.** `s.substring(4, 4)` với `s = "abc"` có trả chuỗi rỗng không?

**Đáp án:** Không. Phương thức ném ngoại lệ vì `4 > s.length() == 3`. Hai biên bằng nhau không đủ để một khoảng trở nên hợp lệ.

**Câu 3.** `"abc".substring("abc".length())` trả về gì?

**Đáp án:** `""`. Overload một tham số lấy từ chỉ số bắt đầu đến hết chuỗi; bắt đầu ngay tại biên cuối nên không còn ký tự nào.

**Câu 4.** Chuỗi `"x="` có phần sau dấu bằng dài bao nhiêu khi trích bằng `substring(separator + 1, length())`?

**Đáp án:** `0`. Dấu `=` ở cuối nên `separator + 1 == length()`; hai biên hợp lệ bằng nhau, kết quả là chuỗi rỗng.

**Câu 5.** `substring(k, k)` tại vị trí giữa high surrogate và low surrogate có gây ra một surrogate đứng lẻ không?

**Đáp án:** Không, vì không lấy code unit nào. Nhưng nếu trích đoạn khác rỗng và cắt một nửa surrogate pair thì mới có nguy cơ tạo một chuỗi UTF-16 chứa surrogate đứng lẻ.

**Ghi nhớ:** Với `String.substring(beginIndex, endIndex)`, nếu `0 <= beginIndex == endIndex <= length()`, kết quả luôn là **`""`** và có **độ dài 0**. Chỉ số phải hợp lệ; chuỗi rỗng là kết quả bình thường của một khoảng `[k, k)`, không phải `null` và không phải ngoại lệ.
