# StringBuilder.setLength(): tăng độ dài bằng ký tự NUL (`\\u0000`)

## 1. Vấn đề cốt lõi

`StringBuilder` là một dãy ký tự **có thể thay đổi** (*mutable*) trong Java. Phương thức `setLength(int newLength)` dùng để đặt **độ dài logic** của dãy đó. Khi `newLength` lớn hơn độ dài hiện tại, các vị trí vừa được bổ sung **không phải dấu cách và không phải chuỗi rỗng**: chúng được điền bằng ký tự **NUL**, tức UTF-16 code unit có giá trị `U+0000`, viết trong Java là `'\0'` hoặc `'\u0000'`.

Đây là hành vi theo hợp đồng API, không chỉ là một chi tiết cài đặt của JVM. Vì NUL thường không hiện ra khi in lên terminal, lập trình viên dễ tưởng `setLength()` chỉ “dự trữ thêm chỗ” hoặc những vị trí mới chưa tồn tại. Thực tế, **chúng đã là thành phần của nội dung StringBuilder** và được tính trong `length()`, `charAt()`, `toString()`, `append()`, tìm kiếm và so sánh.

Ví dụ:

~~~java
StringBuilder sb = new StringBuilder("Hi");
sb.setLength(5);

System.out.println(sb.length());       // 5
System.out.println(sb.charAt(2) == '\0'); // true
System.out.println(sb.charAt(4) == '\u0000'); // true
System.out.println(sb.toString().equals("Hi")); // false
~~~

Sau lệnh `setLength(5)`, dãy code unit là:

| Chỉ số | 0 | 1 | 2 | 3 | 4 |
|---|---|---|---|---|---|
| Giá trị | `'H'` | `'i'` | `U+0000` | `U+0000` | `U+0000` |

Dữ liệu tương đương một chuỗi Java có nội dung `"Hi\u0000\u0000\u0000"` — dài 5 UTF-16 code unit. **Không** tương đương `"Hi"` và cũng **không** tương đương `"Hi   "` (ba dấu cách).

## 2. Độ dài (`length`) khác dung lượng (`capacity`)

Cần phân biệt rõ hai thuộc tính của `StringBuilder`:

- **`length()`**: số UTF-16 code unit đang là nội dung logic. Vị trí hợp lệ cho `charAt(i)` nằm từ 0 đến `length() - 1`. NUL được tính là một phần của độ dài.
- **`capacity()`**: số code unit mà cấu trúc có thể chứa **trước khi cần mở rộng nơi lưu trữ bên trong**. Capacity có thể lớn hơn length, nhưng phần vượt ngoài length **không** được coi là nội dung và không thể đọc bằng `charAt()`.
- **`ensureCapacity(minimumCapacity)`**: yêu cầu dự trữ dung lượng tối thiểu để giảm khả năng phải cấp phát khi thêm dữ liệu về sau. Nó **không** tăng `length()` và **không** tạo ký tự NUL trong nội dung.
- **`setLength(newLength)`**: thay đổi số code unit trong nội dung. Nếu dài ra, các vị trí mới được khởi tạo thành NUL; capacity được mở rộng nếu cần.

Ví dụ đối chiếu:

~~~java
StringBuilder a = new StringBuilder("AB");
a.ensureCapacity(100);
System.out.println(a.length());   // 2
System.out.println(a.toString()); // AB

StringBuilder b = new StringBuilder("AB");
b.setLength(5);
System.out.println(b.length());   // 5
System.out.println(b.charAt(2) == '\0'); // true
~~~

Không nên dùng `setLength(1000)` chỉ để tối ưu số lần cấp phát trước khi `append()`: việc đó tạo **1.000 vị trí nội dung logic** (hoặc nhiều hơn độ dài cũ) với NUL ở phần tăng thêm. Khi chỉ muốn dành chỗ, sử dụng `new StringBuilder(expectedCapacity)` hoặc `ensureCapacity(expectedCapacity)`.

| Mục tiêu | Lựa chọn phù hợp |
|---|---|
| Dành chỗ cho 1.000 ký tự sẽ được `append()` sau | `new StringBuilder(1000)` hoặc `ensureCapacity(1000)` |
| Thay đổi chiều dài logic thành 1.000 code unit | `setLength(1000)` |
| Thêm nội dung ngay sau văn bản hiện có | `append(...)` |
| Rút ngắn nội dung từ vị trí `n` trở đi | `setLength(n)` với `n` nhỏ hơn độ dài hiện tại |
| Điền dấu cách cho đến độ dài cần thiết | `append(" ".repeat(...))` hoặc thao tác ghi ký tự có chủ đích, **không** dựa vào mặc định của `setLength()` |

## 3. Ba trường hợp của `setLength(newLength)`

### 3.1. `newLength` bằng độ dài hiện tại

Về mặt nội dung không có thay đổi:

~~~java
StringBuilder sb = new StringBuilder("ABC");
sb.setLength(3);
System.out.println(sb.toString().equals("ABC")); // true
~~~

### 3.2. `newLength` nhỏ hơn độ dài hiện tại: cắt phần đuôi

Khi giảm độ dài, những code unit từ chỉ số `newLength` trở đi không còn thuộc nội dung logic:

~~~java
StringBuilder sb = new StringBuilder("ABCDE");
sb.setLength(3);
System.out.println(sb.toString()); // ABC
System.out.println(sb.length());   // 3
~~~

Capacity thường không tự giảm xuống bằng length; đó là một thuộc tính khác. Nếu muốn xem xét giảm bộ nhớ sau khi nội dung ổn định, có `trimToSize()`, nhưng không cần gọi theo thói quen vì hiệu quả và chi phí phụ thuộc tình huống.

### 3.3. `newLength` lớn hơn độ dài hiện tại: bổ sung NUL

~~~java
StringBuilder sb = new StringBuilder("ABC");
sb.setLength(6);

System.out.println(sb.length()); // 6
System.out.println(sb.charAt(3) == '\0'); // true
System.out.println(sb.charAt(4) == '\0'); // true
System.out.println(sb.charAt(5) == '\0'); // true
~~~

Nội dung logic mới gồm `A`, `B`, `C`, rồi ba code unit `U+0000`. Các vị trí mới không phải “ô trống” để `append()` tự điền.

**Giới hạn:** `setLength(-1)` ném `StringIndexOutOfBoundsException`. Một giá trị tăng rất lớn có thể đòi cấp phát bộ nhớ lớn và gây lỗi tài nguyên, ví dụ `OutOfMemoryError`; cần kiểm tra kích thước dữ liệu được phép trước khi gọi, nhất là khi newLength đến từ bên ngoài.

## 4. NUL là ký tự thật, không phải điểm kết thúc chuỗi Java

**NUL** ở đây là Unicode code point `U+0000`, được mã hóa trong `StringBuilder` bằng code unit có giá trị 0. Có thể viết:

~~~java
char nul1 = '\0';
char nul2 = '\u0000';
System.out.println(nul1 == nul2); // true
System.out.println((int) nul1);    // 0
~~~

Điều cần phân biệt:

- `'\0'` không đồng nghĩa với `null` (giá trị tham chiếu không trỏ tới đối tượng). `null` không phải ký tự.
- `'\0'` không đồng nghĩa với `'0'` (chữ số 0, code point U+0030).
- `'\0'` không đồng nghĩa với `' '` (dấu cách, U+0020).
- `StringBuilder` và `String` Java **không sử dụng NUL để đánh dấu kết thúc văn bản** như quy ước *null-terminated string* thường thấy trong C. NUL ở giữa hoặc cuối chuỗi vẫn được tính vào độ dài.
- Khi gửi dữ liệu sang một thư viện native, giao thức mạng, cơ sở dữ liệu hay định dạng có quy tắc riêng, **không được giả định** NUL luôn được hiển thị, bảo toàn hoặc cho phép như văn bản bình thường. Hành vi tùy hệ thống nhận; cần kiểm tra ranh giới chuyển đổi.

Ví dụ:

~~~java
StringBuilder sb = new StringBuilder("AB");
sb.setLength(4);              // 'A','B','\0','\0'
sb.append('C');               // 'A','B','\0','\0','C'
System.out.println(sb.length()); // 5
System.out.println(sb.charAt(4)); // C
~~~

`append('C')` thêm **sau length hiện có** chứ không dò vị trí NUL để ghi đè. Kết quả không phải `"ABC"` mà là một dãy gồm `"AB"`, hai NUL và `"C"`.

## 5. Cách kiểm tra các vị trí NUL mà không bị terminal đánh lừa

Câu lệnh `System.out.println(sb)` có thể không cho thấy các code unit NUL trong vùng văn bản hiển thị. Không dựa vào hình ảnh output để kết luận length.

Có thể kiểm tra trực tiếp:

~~~java
StringBuilder sb = new StringBuilder("Hi");
sb.setLength(5);
System.out.println("length=" + sb.length());       // length=5
System.out.println("nul-count=" + sb.chars()
        .filter(value -> value == 0)
        .count());                                  // nul-count=3
~~~

`StringBuilder.chars()` là luồng giá trị `int` tương ứng với từng UTF-16 code unit; các NUL có giá trị 0 nên dễ đếm. Nếu dữ liệu có ký tự Unicode ngoài BMP, `chars()` và `codePoints()` có thể cho cách đếm khác nhau; ở trường hợp NUL đơn lẻ, hai cách vẫn nhận diện được `U+0000`.

Một cách khác là in ký hiệu đại diện hoặc hex thay vì in trực tiếp NUL:

~~~java
for (int i = 0; i < sb.length(); i++) {
    System.out.printf("index=%d, unit=U+%04X%n",
            i, (int) sb.charAt(i));
}
~~~

Kết quả cho `"Hi"` sau `setLength(5)`:

~~~text
index=0, unit=U+0048
index=1, unit=U+0069
index=2, unit=U+0000
index=3, unit=U+0000
index=4, unit=U+0000
~~~

Với dữ liệu được đưa vào log hoặc JSON, một công cụ có thể escape NUL thành `\u0000`, biểu diễn bằng ký hiệu đặc biệt hoặc từ chối ký tự điều khiển. **Cách hiển thị không làm NUL biến thành dữ liệu rỗng**; hãy kiểm tra byte/code unit, độ dài và quy tắc encoding thực tế.

## 6. Rút ngắn rồi tăng lại: không khôi phục ký tự cũ

Giả sử builder chứa `"ABCDE"`, sau đó cắt về length 2 rồi kéo dài lên 4:

~~~java
StringBuilder sb = new StringBuilder("ABCDE");
sb.setLength(2);
System.out.println(sb.toString()); // AB

sb.setLength(4);
System.out.println(sb.length());         // 4
System.out.println(sb.charAt(2) == '\0'); // true
System.out.println(sb.charAt(3) == '\0'); // true
~~~

Giá trị ở chỉ số 2 và 3 **không phải** `'C'` và `'D'`. Việc tăng lại độ dài không làm hồi sinh phần văn bản bị cắt. Những vị trí mới phải được điền bằng NUL, kể cả khi cấu trúc nội bộ còn dung lượng sau lần cắt trước đó.

Nếu muốn tạm thay đổi độ dài rồi phục hồi nội dung cũ, hãy lưu **một bản sao dữ liệu gốc** trước khi cắt, không chỉ lưu số length:

~~~java
StringBuilder sb = new StringBuilder("ABCDE");
String original = sb.toString();
sb.setLength(2);
// ... công việc cần chuỗi rút gọn ...
sb.setLength(0);
sb.append(original);
System.out.println(sb); // ABCDE
~~~

## 7. Khi nào nên dùng `setLength()` để tăng độ dài?

Tăng độ dài chủ động có thể hữu ích trong thuật toán ghi dữ liệu **theo chỉ số**, nếu chương trình hiểu rõ các vị trí NUL tạm thời và bảo đảm điền chúng trước khi đưa văn bản ra ngoài.

~~~java
StringBuilder sb = new StringBuilder("AB");
sb.setLength(5);       // Có thể setCharAt tại chỉ số 2, 3, 4.
sb.setCharAt(2, '-');
sb.setCharAt(3, '-');
sb.setCharAt(4, 'Z');
System.out.println(sb); // AB--Z
~~~

Vì `setCharAt(i, ch)` chỉ hợp lệ khi `0 <= i < length()`, nên tăng length trước có thể cho phép ghi vào các chỉ số mới. Nhưng nếu quy trình bị gián đoạn trước khi điền xong, dữ liệu có thể chứa NUL. Đây là lý do cần viết các đoạn cập nhật rõ phạm vi, có kiểm tra và không công bố kết quả khi còn vị trí chưa được khởi tạo bằng dữ liệu nghiệp vụ.

Trong phần lớn trường hợp xây dựng chuỗi tuần tự, `append()` là API rõ và an toàn hơn:

~~~java
StringBuilder sb = new StringBuilder("AB");
sb.append("---");
System.out.println(sb); // AB---
~~~

Khi cần **đệm dấu cách** tới độ dài `targetLength`, có thể viết:

~~~java
StringBuilder sb = new StringBuilder("AB");
int targetLength = 5;
if (targetLength > sb.length()) {
    sb.append(" ".repeat(targetLength - sb.length()));
}
System.out.println(sb.equals("AB   ")); // false: equals của StringBuilder không so nội dung
System.out.println(sb.toString().equals("AB   ")); // true
~~~

Điểm đáng chú ý của hai câu `println` cuối: `StringBuilder` không override `equals()` để so nội dung, nên phải so `String` hoặc dùng phép so nội dung phù hợp. `"AB   ".contentEquals(sb)` cũng có thể trả `true`. Khi mục tiêu là dấu cách, **phải thêm dấu cách thật**, không mong `setLength()` làm việc đó.

## 8. Tác động tới các thao tác String và validation

Khi gọi `toString()` trên builder chứa NUL, `String` kết quả vẫn giữ NUL. Nhiều API kiểm tra nội dung sẽ cho kết quả không giống như khi xử lý văn bản chỉ có dấu cách.

Ví dụ:

~~~java
StringBuilder sb = new StringBuilder("Hi");
sb.setLength(5);
String text = sb.toString();

System.out.println(text.length());            // 5
System.out.println(text.equals("Hi"));        // false
System.out.println(text.indexOf('\0'));       // 2
System.out.println(text.isEmpty());           // false
System.out.println(text.isBlank());           // false
System.out.println(text.strip().length());    // 5
System.out.println(text.trim().length());     // 2
~~~

Giải thích:

- `isEmpty()` kiểm tra độ dài bằng 0; `"Hi\0\0\0"` dài 5, nên false.
- `isBlank()` (Java 11+) hỏi toàn bộ ký tự có thuộc tập whitespace theo `Character.isWhitespace` hay không. NUL **không** phải whitespace. Ngay cả chuỗi chỉ gồm NUL cũng **không blank**.
- `strip()` bỏ whitespace ở hai đầu theo `Character.isWhitespace`; NUL không thuộc tập đó nên không bị bỏ.
- `trim()` là API cũ bỏ code unit có giá trị không lớn hơn U+0020 ở hai đầu; do đó nó có thể bỏ NUL ở cuối chuỗi ví dụ, nhưng **đây không phải cách xử lý NUL đáng tin trong mọi vị trí**. Một NUL ở giữa chuỗi không bị loại bỏ bởi `trim()`.

Nếu dữ liệu từ `StringBuilder` dùng làm mã định danh, tên tệp, khóa map hoặc giá trị giao thức, những ký tự NUL vô hình có thể gây bug khó phát hiện. Tùy nghiệp vụ, cần **không tạo NUL không cần thiết**, hoặc kiểm tra từ chối các ký tự điều khiển trước khi sử dụng.

### Cảnh báo về cắt giữa surrogate pair

`length()` đếm **UTF-16 code unit**, không đếm ký tự hiển thị hay Unicode code point. Ví dụ emoji 🚀 gồm hai code unit trong Java:

~~~java
StringBuilder sb = new StringBuilder("🚀");
System.out.println(sb.length()); // 2
sb.setLength(1);
System.out.println(Character.isHighSurrogate(sb.charAt(0))); // true
~~~

Lệnh `setLength(1)` có thể cắt đôi một surrogate pair và để lại **high surrogate không ghép cặp**. `StringBuilder` cho phép các dãy UTF-16 code unit như vậy tồn tại; khi chuyển sang encoding khác hoặc gửi qua một giao thức, dữ liệu có thể bị thay thế hoặc từ chối. Không cắt tùy ý theo code unit khi muốn giữ nguyên code point; cần xác định ranh giới hợp lệ, có thể sử dụng `offsetByCodePoints()` với `String` và làm việc cẩn thận với Unicode.

## 9. Chương trình Java 17 chạy độc lập

Ví dụ tổng hợp dưới đây chủ động **không in trực tiếp NUL** trong stdout. Thay vào đó, hàm `inspect()` biểu diễn mỗi `char` bằng ký hiệu dễ đọc. Chương trình kiểm tra: mở rộng bằng NUL, việc `append()` không thay NUL, điền `setCharAt()`, rút ngắn/tăng lại, `ensureCapacity()`, Unicode và trường hợp length âm.

Lưu tệp UTF-8 tên **`SetLengthNulDemo.java`**:

~~~java
public class SetLengthNulDemo {
    private static String inspect(StringBuilder sb) {
        StringBuilder view = new StringBuilder("[");
        for (int i = 0; i < sb.length(); i++) {
            if (i > 0) {
                view.append(", ");
            }
            char ch = sb.charAt(i);
            if (ch == '\0') {
                view.append("U+0000");
            } else {
                view.append('\'').append(ch).append('\'');
            }
        }
        return view.append(']').toString();
    }

    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder("Hi");
        sb.setLength(5);

        System.out.println("expanded.length=" + sb.length());
        System.out.println("expanded.units=" + inspect(sb));
        System.out.println("nulAt2=" + (sb.charAt(2) == '\0'));
        System.out.println("stringLength=" + sb.toString().length());
        System.out.println("equalsHi=" + sb.toString().equals("Hi"));
        System.out.println("indexOfNul=" + sb.indexOf("\0"));
        System.out.println("isBlank=" + sb.toString().isBlank());
        System.out.println("trimLength=" + sb.toString().trim().length());
        System.out.println("stripLength=" + sb.toString().strip().length());

        sb.setCharAt(2, '!');
        sb.setCharAt(3, '?');
        sb.setCharAt(4, '.');
        System.out.println("filled=" + sb);

        sb.setLength(2);
        System.out.println("shortened=" + sb);
        sb.setLength(4);
        System.out.println("regrown.units=" + inspect(sb));
        sb.append('Z');
        System.out.println("afterAppend.units=" + inspect(sb));

        StringBuilder reserved = new StringBuilder("OK");
        reserved.ensureCapacity(100);
        System.out.println("reserved.length=" + reserved.length());
        System.out.println("reserved.content=" + reserved);

        try {
            sb.setLength(-1);
        } catch (StringIndexOutOfBoundsException expected) {
            System.out.println("negativeLength=REJECTED");
        }

        StringBuilder rocket = new StringBuilder("🚀");
        System.out.println("rocket.length=" + rocket.length());
        rocket.setLength(1);
        System.out.println("halfSurrogate=" +
                Character.isHighSurrogate(rocket.charAt(0)));
    }
}
~~~

Biên dịch và chạy với JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 SetLengthNulDemo.java
java SetLengthNulDemo
~~~

Stdout dự kiến:

~~~text
expanded.length=5
expanded.units=['H', 'i', U+0000, U+0000, U+0000]
nulAt2=true
stringLength=5
equalsHi=false
indexOfNul=2
isBlank=false
trimLength=2
stripLength=5
filled=Hi!?.
shortened=Hi
regrown.units=['H', 'i', U+0000, U+0000]
afterAppend.units=['H', 'i', U+0000, U+0000, 'Z']
reserved.length=2
reserved.content=OK
negativeLength=REJECTED
rocket.length=2
halfSurrogate=true
~~~

Phân tích kết quả:

1. `expanded.units` chứng minh ba vị trí tăng thêm là `U+0000`, không phải dấu cách.
2. `stringLength=5` và `equalsHi=false` chứng minh `toString()` giữ đủ nội dung, kể cả NUL cuối.
3. `trimLength=2` và `stripLength=5` minh họa hai tiêu chí xử lý đầu/cuối khác nhau; không nên dùng `trim()` như cách che lỗi NUL.
4. Sau khi dùng `setCharAt()`, dữ liệu `Hi!?.` không còn NUL ở phần được tăng.
5. Sau khi cắt về `Hi` rồi tăng lại, hai vị trí mới **lại** là NUL. `append('Z')` chỉ thêm `Z` vào sau đó.
6. `ensureCapacity(100)` có thể tăng dung lượng dự trữ nhưng không tăng length và không sửa chữ `OK`.
7. `setLength(-1)` bị từ chối; việc cắt emoji xuống một code unit để lại surrogate không ghép cặp.

## 10. Những lỗi thường gặp

| Nhầm lẫn | Thực tế | Cách xử lý |
|---|---|---|
| Tăng `setLength()` nghĩa là dự trữ chỗ | Nó **tăng chiều dài logic** và điền NUL vào đoạn mới | Dùng `ensureCapacity()` nếu chỉ muốn dự trữ |
| Vị trí NUL là ô trống sẽ được `append()` điền vào | `append()` luôn thêm sau length hiện tại | Dùng `setCharAt()` để ghi đè trong phạm vi, hoặc `append()` ngay từ đầu |
| NUL giống dấu cách | NUL là U+0000, dấu cách U+0020 | Điền dấu cách thật nếu nghiệp vụ cần |
| NUL làm Java String kết thúc sớm | Java dùng độ dài logic, không dùng NUL terminator | Kiểm tra `length()`, `charAt()` thay vì nhìn output |
| `setLength()` giảm rồi tăng là khôi phục dữ liệu cũ | Đoạn mới tăng lên được điền NUL | Lưu dữ liệu cũ nếu cần khôi phục |
| `toString()` bỏ NUL | `String` kết quả giữ NUL | Dùng biểu diễn hex/escape khi debug |
| `strip()` loại NUL | NUL không phải whitespace theo `Character.isWhitespace()` | Không dựa vào `strip()` để xử lý ký tự điều khiển |
| `trim()` luôn xóa được NUL | Nó chỉ xử lý code unit <= U+0020 **ở hai đầu**, không phải mọi vị trí | Xây dựng dữ liệu đúng ngay từ đầu hoặc validation riêng |
| `StringBuilder.equals()` so nội dung | Mặc định so danh tính đối tượng | Dùng `toString().equals(...)` hoặc `String.contentEquals(builder)` |
| `length()` bằng số ký tự hiển thị | Length đếm UTF-16 code unit | Cân nhắc surrogate pair/code point |
| `setLength()` âm sẽ thành rỗng | Giá trị âm không hợp lệ | Ràng buộc `newLength >= 0` |
| Tăng tới chiều dài cực lớn luôn an toàn | Có thể tốn bộ nhớ và thời gian, gây lỗi tài nguyên | Xác thực kích thước và giới hạn input |

## 11. Checklist sử dụng `setLength()` đúng cách

- [ ] Phân biệt rõ **length** với **capacity**.
- [ ] Chỉ tăng length khi thực sự muốn các vị trí mới tồn tại; biết chúng được điền **NUL**.
- [ ] Nếu muốn nối thêm tuần tự, ưu tiên `append()`; nếu chỉ muốn dự trữ, ưu tiên `ensureCapacity()`.
- [ ] Nếu phải tăng length để ghi theo chỉ số, bảo đảm ghi đè toàn bộ những vị trí NUL tạm trước khi xuất dữ liệu.
- [ ] Không dựa vào terminal để quan sát NUL; dùng `charAt()`, mã hex hoặc kiểm tra length.
- [ ] Chú ý `toString()` giữ NUL, và `trim()`/`strip()` có tiêu chí khác nhau.
- [ ] Đặt giới hạn cho kích thước mới và xử lý `newLength < 0`.
- [ ] Khi cắt Unicode, tránh chia đôi surrogate pair nếu nghiệp vụ làm việc theo code point.

**Ghi nhớ:** `setLength(newLength)` thay đổi **nội dung logic** của `StringBuilder`: giảm thì cắt đuôi, tăng thì **thêm các ký tự `U+0000` vào cuối**. Nó **khác hoàn toàn** với việc chỉ tăng capacity. NUL là ký tự thật trong chuỗi Java, mặc dù thường vô hình khi hiển thị.