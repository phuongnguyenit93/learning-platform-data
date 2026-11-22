# Chi phí duyệt, tìm kiếm, so sánh và sao chép String theo độ dài trong Java

Hiệu năng của thao tác với `String` thường phụ thuộc vào **độ dài dữ liệu cần đọc** và **lượng dữ liệu phải tạo ra**, chứ không chỉ vào số lần gọi phương thức. Một biểu thức trông ngắn như `text.indexOf(pattern)`, `a.equals(b)` hoặc `text.substring(from, to)` có thể xử lý hàng nghìn hay hàng triệu đơn vị ký tự. Hiểu chi phí giúp chọn thuật toán, tránh sao chép lặp đi lặp lại và đánh giá đúng các điểm nghẽn.

Bài này xét `String` của Java 17+, tập trung vào chi phí **duyệt, tìm kiếm, so sánh và sao chép theo độ dài**. Ký hiệu Big-O mô tả tốc độ tăng chi phí khi kích thước dữ liệu tăng, **không phải số mili giây cố định**. Một số tối ưu phụ thuộc phiên bản JDK, JIT, charset, nội dung chuỗi và cách JVM hiện thực; vì vậy cần phân biệt mô hình thuật toán với cam kết của Java API.

## 1. Xác định đúng kích thước đầu vào

Dùng các ký hiệu sau:

| Ký hiệu | Ý nghĩa |
| --- | --- |
| `n` | `text.length()`: số **UTF-16 code units** của chuỗi nguồn. |
| `m` | `pattern.length()`: số UTF-16 code units của mẫu cần tìm. |
| `k` | Độ dài đoạn được so sánh, duyệt hay sao chép; ví dụ `endIndex - beginIndex`. |
| `r` | Số lần lặp hoặc số phần được tạo thêm. |
| `L` | Tổng độ dài của các phần cần ghép thành kết quả. |

Trong Java, `String.length()` trả số đơn vị mã UTF-16, **không phải** số Unicode code points, số ký tự người dùng nhìn thấy (*grapheme clusters*) hay số byte UTF-8.

```java
String x = "A\uD83D\uDE00"; // A và emoji 😀
int units = x.length();                            // 3
int points = x.codePointCount(0, x.length());     // 2
int bytes = x.getBytes(StandardCharsets.UTF_8).length; // 5
```

Đây là **đoạn minh họa**, cần import `java.nio.charset.StandardCharsets`. Emoji được lưu bằng cặp surrogate, tương ứng **hai** UTF-16 code units và **bốn** byte UTF-8. Khi phân tích độ phức tạp của `charAt`, `indexOf`, `substring` hoặc `compareTo`, các chỉ số Java thường tính theo UTF-16 code units.

Phân biệt:

- **Thời gian:** công việc cần thực hiện khi `n`, `m` hoặc `k` tăng.
- **Bộ nhớ phụ:** vùng nhớ mới do thao tác tạo ra, ngoài các đối tượng đầu vào đã tồn tại.
- **Chi phí tích lũy:** một thao tác `O(n)` nếu lặp `r` lần có thể thành `O(rn)`; nếu độ dài chuỗi tăng dần theo mỗi vòng, tổng còn lớn hơn.

## 2. Bảng tổng quan chi phí cần nhớ

Bảng dưới là **mô hình học thuật và thực tế thường gặp trên Java 17**, không phải bảo đảm độ phức tạp bắt buộc của mọi JVM/phiên bản. Các thao tác có thể dừng sớm hoặc được tối ưu bởi JIT.

| Thao tác | Chi phí thời gian thường gặp | Bộ nhớ thêm thường gặp | Ghi chú |
| --- | --- | --- | --- |
| `s.length()` | `O(1)` | `O(1)` | Độ dài được lưu trong đối tượng/dữ liệu; không duyệt để đếm ở mỗi lần gọi. |
| `s.isEmpty()` | `O(1)` | `O(1)` | Tương đương kiểm tra độ dài bằng 0. |
| `s.charAt(i)` | `O(1)` | `O(1)` | Truy cập một UTF-16 code unit sau kiểm tra chỉ số. |
| Một vòng duyệt từ `0` đến `n - 1` | `O(n)` | `O(1)` nếu chỉ tích lũy biến | Có thể dừng sớm khi đạt điều kiện. |
| `s.codePointCount(a, b)` | `O(k)` tổng quát | `O(1)` | Cần xác định cặp surrogate trong đoạn dài `k`; chuỗi Latin-1 có đường đi tối ưu. |
| `s.indexOf(ch)` / `lastIndexOf(ch)` | `O(n)` trong trường hợp phải quét hết | `O(1)` thường gặp | Trường hợp tốt có thể tìm thấy ngay. |
| `s.indexOf(pattern)` / `s.contains(pattern)` | Phụ thuộc thuật toán tìm chuỗi và mẫu; mô hình so khớp đơn giản có worst case `O(nm)` | Phụ thuộc triển khai | Không gán bừa `O(n)` hay `O(nm)` như cam kết API cho mọi JDK. |
| `s.startsWith(prefix)` | `O(m)` tối đa cho tiền tố dài `m` | `O(1)` thường gặp | Có thể dừng ở ký tự khác đầu tiên. |
| `s.endsWith(suffix)` | `O(m)` tối đa cho hậu tố dài `m` | `O(1)` thường gặp | Không cần quét toàn bộ phần đầu khi chỉ xét hậu tố. |
| `s.equals(t)` | `O(n)` worst case với hai chuỗi cùng độ dài; có thể dừng sớm | `O(1)` thường gặp | Khác độ dài trả về nhanh; cùng nội dung phải đối chiếu. |
| `s.compareTo(t)` | `O(min(n,m))` cho phần tiền tố so sánh | `O(1)` thường gặp | Dừng ở ký tự khác đầu tiên hoặc cuối chuỗi ngắn hơn. |
| `s.regionMatches(..., len)` | `O(len)` worst case | `O(1)` thường gặp | Chỉ so vùng đã chỉ định. |
| `s.substring(a, b)` | `O(k)` khi tạo bản sao đoạn dài `k` trên OpenJDK hiện đại | `O(k)` khi phải sao chép | Trường hợp rỗng/toàn bộ chuỗi có thể được tối ưu; không lấy chi tiết cấp phát làm hợp đồng API. |
| `s.toCharArray()` | `O(n)` | `O(n)` | Tạo mảng `char[]`, có `n` UTF-16 code units. |
| `s.getBytes(charset)` | Phụ thuộc charset; ít nhất cần tạo/ghi số byte đầu ra, thường tuyến tính theo dữ liệu | `O(b)` với `b` byte đầu ra | Không lấy `n` làm số byte vì UTF-8 biến độ dài. |

**Điểm mấu chốt:** một lệnh ngắn trong source không đồng nghĩa với thao tác `O(1)`. `charAt(i)` chỉ lấy một đơn vị ký tự; `equals`, `indexOf` hay `toCharArray` có thể cần xử lý hầu hết chuỗi.

## 3. Duyệt chuỗi: một lần quét và nhiều lần quét

### 3.1. Vòng lặp `charAt`

```java
int digits = 0;
for (int i = 0; i < text.length(); i++) {
    if (text.charAt(i) >= '0' && text.charAt(i) <= '9') {
        digits++;
    }
}
```

Đây là **đoạn minh họa**, giả sử `text` đã được khai báo. `length()` và mỗi lần `charAt(i)` có chi phí nhỏ, thường `O(1)`; vòng lặp có `n` lần nên tổng là **`O(n)` thời gian và `O(1)` bộ nhớ phụ**. Không phải `O(n²)` chỉ vì gọi `length()` trong điều kiện vòng lặp.

Nếu bài toán chỉ cần tìm **ký tự đầu tiên** thỏa điều kiện, dùng `break` hoặc trả kết quả sớm. Worst case vẫn `O(n)` nhưng dữ liệu thực tế có thể kết thúc sớm.

### 3.2. Code unit khác code point

`charAt` truy cập **UTF-16 code unit**, nên khi chuỗi có emoji hay ký tự ngoài BMP, mỗi lần `charAt` không nhất thiết đại diện trọn một Unicode code point. Nếu logic yêu cầu đọc từng code point:

```java
int count = 0;
for (int offset = 0; offset < text.length();) {
    int cp = text.codePointAt(offset);
    count++;
    offset += Character.charCount(cp);
}
```

Đoạn trên duyệt từng code point. Với mỗi bước, `codePointAt` chỉ xem một hoặc hai code units gần vị trí hiện tại; tổng vẫn **`O(n)`** tính theo số UTF-16 code units. Có thể dùng `text.codePoints()` khi pipeline stream làm mã rõ hơn, nhưng stream có thêm chi phí điều phối/đối tượng và không tự nhiên nhanh hơn vòng lặp trên mọi trường hợp.

### 3.3. Gọi hàm quét toàn chuỗi trong vòng lặp

```java
// Tốn thêm nhiều lần tìm kiếm:
for (int i = 0; i < queries.size(); i++) {
    boolean present = bigText.contains(queries.get(i));
    // ...
}
```

Giả sử có `r` truy vấn. Mỗi lần `contains` có thể tìm trên văn bản dài `n` và mẫu dài `m_i`; **không** được tính cả vòng lặp chỉ `O(r)`. Tổng là tổng chi phí của từng phép tìm kiếm, phụ thuộc dữ liệu. Nếu cùng truy vấn được lặp lại nhiều lần, cân nhắc lưu kết quả; nếu cần tra cứu rất nhiều từ/mẫu, cấu trúc chỉ mục hoặc thuật toán đa mẫu có thể hữu ích, nhưng phải đo trước khi đầu tư.

## 4. Tìm kiếm: một ký tự và chuỗi con

### 4.1. `indexOf(int)`, `lastIndexOf(int)`

```java
String s = "ababaX";

int firstA = s.indexOf('a');         // 0
int lastA = s.lastIndexOf('a');      // 4
int absent = s.indexOf('z');        // -1
```

Các phương thức có thể dừng khi thấy kết quả cần tìm; nếu ký tự không tồn tại, thường phải kiểm tra đến hết vùng tìm kiếm. Vì vậy dùng mô hình **`O(n)` worst case**, `O(1)` bộ nhớ phụ. `indexOf(int)` cũng hỗ trợ Unicode code point ngoài BMP (đối chiếu cặp surrogate); kết quả vị trí vẫn là chỉ số UTF-16.

### 4.2. `indexOf(String)`, `contains(String)`

Giả sử nguồn dài `n`, mẫu dài `m`:

```java
String s = "ababaX";
int a = s.indexOf("aba");     // 0
int b = s.indexOf("aba", 1);  // 2
boolean found = s.contains("baba"); // true
```

Không nên khẳng định một Big-O duy nhất cho mọi triển khai và mọi mẫu. Một phương pháp tìm chuỗi con đơn giản thử tối đa `n - m + 1` vị trí và có thể so sánh tới `m` đơn vị tại mỗi vị trí, nên **worst case `O(nm)`**. Các thư viện/JVM có thể tối ưu hóa cho từng dạng chuỗi, mẫu ngắn hoặc nội dung cụ thể. `contains` kiểm tra sự xuất hiện của chuỗi con, không phải tìm bằng regex. Trên Java, `s.contains(x)` dùng cơ chế tìm kiếm chuỗi con (tương đương kiểm tra `indexOf(x) >= 0`).

**Ví dụ trường hợp so khớp lặp lại:** nguồn gồm nhiều chữ `a`, mẫu bắt đầu bởi nhiều `a` rồi mới là `b` có thể buộc thuật toán so khớp ngây thơ so sánh lại nhiều vị trí. Đây là mô hình phân tích thuật toán, không khẳng định một thời gian chạy cố định trên HotSpot 17.

### 4.3. Khi chỉ cần kiểm tra đầu hoặc cuối

Nếu yêu cầu chỉ là kiểm tra một **tiền tố**, dùng `startsWith(prefix)`; nếu chỉ kiểm tra một **hậu tố**, dùng `endsWith(suffix)`. Chúng chỉ cần so sánh vùng tương ứng, tối đa `O(m)` với `m` là độ dài tiền/hậu tố sau kiểm tra độ dài, thay vì tìm trên toàn bộ chuỗi. Ví dụ:

```java
String path = "/api/orders/123";
boolean apiPath = path.startsWith("/api/");
boolean endsWithId = path.endsWith("/123");
```

Không dùng `indexOf(prefix) == 0` nếu `startsWith(prefix)` nói rõ ý định hơn; lợi ích hiệu năng cụ thể còn phụ thuộc môi trường.

### 4.4. Regex khác tìm kiếm chuỗi thuần

`String.matches(regex)`, `split(regex)`, `replaceAll(regex, replacement)` dùng **regex** và có chi phí phân tích mẫu, tìm khớp. Độ phức tạp của regex phụ thuộc biểu thức, nhất là với backtracking và các nhánh lồng nhau; có mẫu gây tăng trưởng rất lớn khi dữ liệu không khớp. Vì vậy không thể suy ra từ `indexOf` rằng mọi tìm kiếm bằng regex đều tuyến tính.

Nếu chỉ cần tìm một chuỗi ký tự **nguyên văn**, ưu tiên `indexOf`/`contains`; nếu cần regex lặp lại, cân nhắc biên dịch `Pattern` một lần và sử dụng `Matcher` mới cho từng đầu vào. Việc đo trên dữ liệu đại diện quan trọng hơn mẹo tối ưu chung chung.

## 5. So sánh: khác ngay đầu thì rẻ, trùng dài thì đắt

### 5.1. `equals`

```java
boolean x = "prefix-a".equals("prefix-b"); // false
boolean y = "same".equals(new String("same")); // true
```

`equals` kiểm tra nội dung có bằng nhau hay không. Nếu hai đối tượng `String` chính là cùng tham chiếu, hoặc độ dài khác nhau, có thể trả về nhanh. Nếu cùng độ dài và nhiều ký tự đầu giống nhau, phải so sánh sâu hơn; hai chuỗi dài thực sự bằng nhau cần đối chiếu đủ nội dung để xác nhận, nên mô hình worst case là **`O(n)`**.

Chú ý `==` kiểm tra **tham chiếu đối tượng**, không phải tính bằng nhau của nội dung. Thay `equals` bằng `==` để “tối ưu” là thay đổi ý nghĩa, dễ gây lỗi.

### 5.2. `compareTo`

`s.compareTo(t)` so sánh thứ tự từ điển theo giá trị UTF-16 của từng đơn vị ký tự. Nó trả về số âm, 0 hoặc số dương; không nên giả định luôn chỉ trả -1, 0, 1.

- Nếu ký tự đầu tiên khác nhau, có thể kết thúc sớm.
- Nếu `s` và `t` có một tiền tố dài giống nhau, phải so sâu hơn.
- Nếu một chuỗi là tiền tố của chuỗi kia, sau khi so hết chuỗi ngắn hơn sẽ xét chênh lệch độ dài.

Với độ dài lần lượt `n` và `m`, số phần tử cần đối chiếu nhiều nhất tỷ lệ với **`min(n,m)`**, nên mô hình là `O(min(n,m))` cho thời gian so sánh và `O(1)` bộ nhớ phụ thường gặp. Chi phí có thể tăng đáng kể khi sắp xếp một danh sách gồm nhiều chuỗi rất dài có tiền tố giống nhau.

### 5.3. `regionMatches`, `equalsIgnoreCase`

`regionMatches` so một đoạn có độ dài `k` thay vì phải tạo `substring` trước:

```java
String s = "prefixVALUEsuffix";
boolean same = s.regionMatches(6, "VALUE", 0, 5); // true
```

Khi chỉ cần kiểm tra đoạn, cách này giúp **tránh tạo một đối tượng/chuỗi con trung gian**. Chi phí so sánh vùng khoảng `O(k)` worst case; dừng sớm khi không khớp.

`equalsIgnoreCase` so sánh không phân biệt hoa/thường theo quy tắc Unicode của API, không phải cách so sánh ngôn ngữ theo locale; vẫn có thể cần đọc nhiều đơn vị ký tự. Nếu cần thứ tự/ngữ nghĩa văn bản theo ngôn ngữ tự nhiên, dùng `Collator` với locale phù hợp.

## 6. Sao chép: thời gian và bộ nhớ tăng theo lượng dữ liệu tạo ra

### 6.1. `substring(begin, end)`

```java
String s = "hello-world";
String piece = s.substring(6, 11); // "world"
```

Với `k = end - begin`, OpenJDK 17 thông thường tạo dữ liệu ký tự của phần kết quả dài `k` nên **chi phí khoảng `O(k)` về thời gian/bộ nhớ** khi cần bản sao. Đây là tính chất **triển khai**, không phải hợp đồng nói mọi lời gọi `substring` đều cấp phát; ví dụ lấy toàn bộ chuỗi hay chuỗi rỗng có thể được tối ưu.

Không mang giả định từ một số JDK rất cũ rằng mọi substring là “view” chia sẻ mảng nền với chuỗi gốc. Với JVM hiện đại, việc giữ một substring nhỏ thường không buộc giữ cả vùng ký tự dài cũ; nhưng chi phí cắt ra nhiều substring vẫn cần tính đến.

Nếu chỉ cần **kiểm tra** một đoạn, `regionMatches` thường tránh được bước tạo substring. Nếu cần thật sự lưu và sử dụng đoạn văn bản lâu dài, `substring` có thể là lựa chọn đúng và dễ đọc; không nên né sao chép bằng cấu trúc phức tạp khi chưa có vấn đề thực tế.

### 6.2. `toCharArray`, `getBytes`, `getChars`

- `toCharArray()` tạo một `char[]` mới có `n` code units: **`O(n)` thời gian, `O(n)` bộ nhớ phụ** cho mảng.
- `getBytes(StandardCharsets.UTF_8)` mã hóa thành `byte[]` mới: thường có chi phí tỷ lệ với số đơn vị đầu vào và byte đầu ra. Với `b` byte đầu ra, bộ nhớ cho dữ liệu kết quả là **`O(b)`**.
- `getChars(srcBegin, srcEnd, dst, dstBegin)` sao chép `k` code units vào **mảng do người gọi cấp**: thời gian `O(k)`; không cần tự tạo `char[]` trả về cho mỗi lần gọi, nhưng phải bảo đảm vùng đích đủ chỗ.

Hai chuỗi có cùng `length()` không nhất thiết cho cùng số byte UTF-8: ASCII dùng một byte mỗi code point, nhiều chữ tiếng Việt/emoji cần nhiều hơn. Vì vậy kích thước payload và chi phí truyền dữ liệu phải xét `getBytes(...).length`, không dựa hoàn toàn vào `String.length()`.

### 6.3. Chuỗi là immutable, kết quả biến đổi có thể tạo dữ liệu mới

`String` bất biến; các thao tác tạo giá trị văn bản đã biến đổi, chẳng hạn `toUpperCase`, `replace` hoặc `repeat`, không sửa nội dung gốc. Nếu kết quả khác đầu vào và được vật hóa, phải có nơi lưu dữ liệu kết quả; chi phí tối thiểu liên quan tới **số ký tự/byte đầu ra**. Nhưng không nên tự gán một Big-O chính xác cho mọi overload `replace` và mọi biểu thức regex: thuật toán dò tìm, thay thế, chuẩn hóa có thể khác nhau.

Ví dụ `"ab".repeat(4)` tạo `"abababab"`, dài tám code units. Nếu số lần lặp là `r` và chuỗi gốc dài `n`, cần tạo sản phẩm kích thước `n × r` (trừ các trường hợp đặc biệt như `r = 0` hoặc `1`).

## 7. Nối chuỗi lặp: chi phí cộng dồn

Độ phức tạp của **một phép nối** khác với tổng chi phí khi phải nối lại cùng một tiền tố nhiều lần. Xét một vòng lặp với danh sách `parts` đã có:

```java
String result = "";
for (String part : parts) {
    result += part;
}
```

Vì `String` bất biến, mỗi lượt có thể tạo kết quả mới chứa toàn bộ tiền tố đã tích lũy. Với `r` phần, mỗi phần dài `c` đơn vị UTF-16, tổng độ dài các kết quả trung gian theo mô hình sao chép tuần tự là `c × (1 + 2 + … + r) = c × r(r + 1)/2`, tức **`Θ(c·r²)`**. Trong khi đó chuỗi cuối chỉ dài `L = c·r`. Đây là mô hình công việc, không phải số byte cấp phát chính xác của mọi JVM.

```java
StringBuilder builder = new StringBuilder();
for (String part : parts) {
    builder.append(part);
}
String result = builder.toString();
```

Với bộ đệm mở rộng theo tỷ lệ, xây dựng bằng `StringBuilder` thường có tổng chi phí append **gần `O(L)` theo lượng dữ liệu được thêm**, cộng chi phí tạo kết quả cuối. Nếu biết kích thước hợp lý, có thể dự trù capacity để hạn chế mở rộng. Phân biệt điều này với một biểu thức đơn như `a + b + c`: compiler/JVM hiện đại có thể tối ưu hiệu quả, nên không cần thay mọi dấu `+` bằng builder.

Phần tính tổng dữ liệu sao chép cho các đoạn không đều, ví dụ chạy được và sự khác nhau giữa số ký tự lý thuyết với allocation thực nằm ở bài chuyên sâu về nối lặp `+=`. Tại đây, điểm cần giữ là **chi phí tích lũy phụ thuộc việc dữ liệu cũ phải được xử lý lại bao nhiêu lần**.

## 8. Ví dụ Java 17+ chạy độc lập

Tạo tệp `StringCostDemo.java` bằng mã sau:

```java
import java.nio.charset.StandardCharsets;
import java.util.List;

public class StringCostDemo {
    public static void main(String[] args) {
        String text = "ababaX";
        String pattern = "aba";

        System.out.println("length: " + text.length());
        System.out.println("charAt(3): " + text.charAt(3));
        System.out.println("first pattern: " + text.indexOf(pattern));
        System.out.println("pattern after 0: " + text.indexOf(pattern, 1));
        System.out.println("last pattern: " + text.lastIndexOf(pattern));
        System.out.println("missing char: " + text.indexOf('z'));
        System.out.println("startsWith: " + text.startsWith("aba"));
        System.out.println("endsWith: " + text.endsWith("X"));
        System.out.println("equals: " + text.equals(new String("ababaX")));
        System.out.println("compareTo: " + text.compareTo("ababaY"));
        System.out.println("regionMatches: "
                + text.regionMatches(2, pattern, 0, 3));

        String piece = text.substring(2, 5);
        char[] copy = text.toCharArray();
        System.out.println("substring: " + piece);
        System.out.println("copied chars: " + copy.length);

        int sum = 0;
        for (int i = 0; i < text.length(); i++) {
            sum += text.charAt(i);
        }
        System.out.println("code-unit sum: " + sum);

        String unicode = "A\uD83D\uDE00"; // A và emoji
        System.out.println("UTF-16 units: " + unicode.length());
        System.out.println("code points: "
                + unicode.codePointCount(0, unicode.length()));
        System.out.println("UTF-8 bytes: "
                + unicode.getBytes(StandardCharsets.UTF_8).length);

        List<String> parts = List.of("[0]", "[1]", "[2]", "[3]");
        StringBuilder builder = new StringBuilder(12);
        for (String part : parts) {
            builder.append(part);
        }
        System.out.println("built: " + builder);
        System.out.println("built length: " + builder.length());
    }
}
```

Biên dịch và chạy từ thư mục chứa tệp:

```bash
javac -encoding UTF-8 StringCostDemo.java
java StringCostDemo
```

Đầu ra:

```text
length: 6
charAt(3): b
first pattern: 0
pattern after 0: 2
last pattern: 2
missing char: -1
startsWith: true
endsWith: true
equals: true
compareTo: -1
regionMatches: true
substring: aba
copied chars: 6
code-unit sum: 575
UTF-16 units: 3
code points: 2
UTF-8 bytes: 5
built: [0][1][2][3]
built length: 12
```

Giải thích theo chi phí:

1. `charAt(3)` chỉ lấy một code unit; vòng cộng mã ký tự phải duyệt sáu code units nên là một phép quét `O(n)`.
2. `indexOf("aba")` và `lastIndexOf("aba")` cho vị trí khác nhau; thời gian tìm phụ thuộc nội dung nguồn/mẫu, không chỉ độ dài kết quả trả về.
3. `regionMatches(2, pattern, 0, 3)` so đúng ba code units mà không yêu cầu tạo substring.
4. `substring(2, 5)` tạo nội dung `"aba"`; `toCharArray()` tạo bản sao sáu code units.
5. `unicode.length()` bằng 3 nhưng có 2 code points và 5 byte UTF-8.
6. `StringBuilder` ghép bốn phần thành 12 ký tự mà không yêu cầu tự dựng lại chuỗi tiền tố sau từng `append`.

Đây là **ví dụ giải thích hành vi**. Đầu ra chứng minh giá trị đúng, **không trực tiếp chứng minh thời gian chạy hay Big-O**; muốn đánh giá hiệu năng thực tế cần phép đo có phương pháp.

## 9. Sắp xếp nhiều chuỗi: chi phí so sánh cộng dồn

Khi sắp xếp `q` chuỗi bằng comparator dựa trên `String.compareTo`, một thuật toán so sánh sắp xếp thường cần khoảng `O(q log q)` lần so sánh. Nhưng **một lần so sánh chuỗi** có thể đọc tới `O(min(n_i, n_j))` code units. Nếu mọi chuỗi có độ dài tối đa `M`, ước lượng cấp cao thường là **`O(q log q × M)`**, không chỉ `O(q log q)`. Đây là giới hạn theo mô hình comparator-based phổ biến, không phải khẳng định mọi trường hợp dữ liệu luôn đạt tới đó.

Ví dụ danh sách gồm các mã có tiền tố chung rất dài sẽ tốn nhiều phép đọc ký tự hơn danh sách có ký tự đầu rất khác nhau, dù số phần tử và số lần gọi comparator tương tự.

Nếu so sánh theo ngữ nghĩa địa phương/tiếng Việt, `String.compareTo` không tương đương sắp xếp theo quy tắc ngôn ngữ; cân nhắc `Collator`. Việc tạo khóa so sánh hoặc bộ nhớ đệm có thể cải thiện một số workload, nhưng phải tính thêm bộ nhớ và chi phí tạo khóa.

## 10. Trường hợp đặc biệt làm thay đổi chi phí thực tế

### Chuỗi rỗng và đối tượng có cùng tham chiếu

Một số phương thức có đường đi nhanh: `isEmpty()`, so sánh độ dài trước khi `equals`, hay kết quả cho `substring` rỗng. Vì vậy một thao tác có worst case `O(n)` không có nghĩa mọi lời gọi đều quét `n` ký tự.

### Compact Strings và cách JVM lưu dữ liệu

OpenJDK/HotSpot hiện đại có cơ chế **Compact Strings** (JEP 254): nếu nội dung có thể biểu diễn bằng Latin-1, bộ nhớ nền có thể dùng một byte mỗi code unit; nếu không, dùng biểu diễn UTF-16. Điều này ảnh hưởng mức tiêu thụ bộ nhớ, băng thông bộ nhớ và các nhánh tối ưu bên trong. Đây là **chi tiết triển khai**, không làm thay đổi ý nghĩa `String.length()` hay hợp đồng Unicode của `String`, và không nên dùng để suy rằng tất cả chuỗi Java luôn tốn đúng một hoặc hai byte trên mỗi ký tự (vì còn header, alignment và các vùng nhớ khác).

### Bộ nhớ tạm và áp lực garbage collector

Một thuật toán tạo ra nhiều substring, mảng `char[]`, byte array hoặc chuỗi trung gian có thể gây nhiều allocation và GC, dù độ phức tạp tiệm cận giống cách khác. Chẳng hạn `s.substring(a, b).equals(target)` có thể vừa tạo đoạn mới vừa so sánh; `s.regionMatches(a, target, 0, target.length())` giúp tránh bước tạo đoạn trung gian khi mục tiêu chỉ là kiểm tra.

JIT đôi khi loại bỏ allocation bằng escape analysis khi chứng minh được đối tượng không thoát, nhưng đó là tối ưu phụ thuộc JVM và workload; không xem như điều chắc chắn trong thiết kế thuật toán.

### Cache, Unicode và tính chất dữ liệu

Một chuỗi có nhiều ASCII có thể chạy khác chuỗi có nhiều surrogate, dù cùng số code units. Dữ liệu có mẫu tìm kiếm xuất hiện ở đầu thường khác dữ liệu không có mẫu; so sánh các chuỗi khác ngay ký tự đầu khác chuỗi có tiền tố chung dài. Những thay đổi này ảnh hưởng chi phí thực tế mà không mâu thuẫn với Big-O worst case.

## 11. Đo hiệu năng cho đúng

Không nên lấy vài dòng `System.nanoTime()` chạy đúng một lần rồi kết luận phương thức A luôn nhanh hơn B. Với JVM, cần tính tới JIT warmup, cấp phát/GC, biến động CPU, nội dung dữ liệu và khả năng JVM tối ưu bỏ kết quả không dùng.

Để đo đáng tin cậy:

1. **Xác định workload:** độ dài `n`, kích thước mẫu `m`, bảng ký tự, tỷ lệ tìm thấy/không thấy và số lần lặp.
2. **Giữ ngữ nghĩa tương đương:** so sánh hai cách làm tạo cùng kết quả; tránh trường hợp một cách có bước chuẩn hóa/tạo dữ liệu khác.
3. **Khởi động JVM và warmup đủ:** hạn chế đo phần class loading/JIT thay vì chính thao tác.
4. **Dùng JMH** (Java Microbenchmark Harness) cho microbenchmark, tiêu thụ kết quả với cách JMH hỗ trợ để tránh dead-code elimination.
5. **Đo cả throughput, latency, allocation/GC khi thích hợp**; lặp trên nhiều kích thước đầu vào để nhìn độ tăng.
6. **Đánh giá tính dễ đọc và mức độ ảnh hưởng thực tế:** nếu tối ưu chỉ tiết kiệm vài nanosecond ở đường chạy hiếm gặp, chưa chắc đáng tăng độ phức tạp mã nguồn.

Ví dụ phép thử có ý nghĩa là so sánh việc ghép 10, 100, 10.000 phần bằng vòng `String +=` và `StringBuilder`, giữ nguyên tổng nội dung; hoặc so `substring(...).equals(...)` với `regionMatches(...)` khi cùng điều kiện đúng/sai. Tránh benchmark bằng các hằng số được compiler/JIT gộp trước khi đo.

## 12. Các lỗi phân tích thường gặp

| Suy luận sai | Phân tích đúng |
| --- | --- |
| “`length()` có `n` ký tự nên chắc chắn `O(n)`.” | Độ dài đã có sẵn; `length()` thường `O(1)`. |
| “`charAt` là `O(1)` nên duyệt `n` lần vẫn là `O(1)`.” | Cộng `n` lần gọi cho ra `O(n)`. |
| “`equals` luôn kiểm tra đủ chuỗi.” | Có thể kiểm tra tham chiếu/độ dài hoặc dừng ở ký tự khác sớm; worst case dài mới tuyến tính. |
| “`compareTo` tốn thời gian theo chuỗi dài hơn.” | Chỉ cần so tối đa tiền tố chung đến hết chuỗi ngắn hơn: `O(min(n,m))`. |
| “`indexOf(String)` luôn `O(n)` như tìm một ký tự.” | Mẫu dài có chi phí so khớp bổ sung; thuật toán triển khai quyết định worst case. |
| “`substring` luôn `O(1)` và không tạo bản sao.” | Trên OpenJDK hiện đại, đoạn kết quả khác biệt thường cần sao chép theo độ dài `k`. |
| “Nối `+=` trong vòng lặp dài là rẻ như một lần append.” | Sao chép tiền tố tích lũy có thể dẫn tới chi phí bậc hai theo số phần. |
| “`String.length()` là số ký tự Unicode hay byte UTF-8.” | Đó là số UTF-16 code units. |
| “Giảm Big-O là đủ để chứng minh nhanh hơn.” | Hằng số, allocation, GC, JIT, dữ liệu và kích thước nhỏ có thể làm kết quả khác; cần benchmark đúng. |
| “Có một giá trị Big-O cố định cho mọi regex.” | Độ phức tạp phụ thuộc biểu thức, công cụ regex và đầu vào. |

## 13. Bài tập tự kiểm tra

**Bài 1.** Có `n` code units, mỗi vòng gọi `s.charAt(i)` đúng một lần và chỉ tăng biến đếm. Thời gian và bộ nhớ phụ?

**Đáp án:** `O(n)` thời gian, `O(1)` bộ nhớ phụ nếu không tạo cấu trúc tăng theo `n`.

**Bài 2.** Hai chuỗi cùng độ dài 100.000, chỉ khác ký tự đầu tiên. `equals` và `compareTo` có nhất thiết so đến ký tự cuối không?

**Đáp án:** Không. Có thể dừng ngay tại vị trí đầu tiên khác nhau (sau các kiểm tra cần thiết). Worst case tuyến tính áp dụng khi chúng giống nhau hoặc khác rất muộn.

**Bài 3.** Tạo 5.000 phần dài 10 ký tự bằng vòng `result += part`. Đầu ra cuối dài bao nhiêu và vì sao mô hình bậc hai đáng quan tâm?

**Đáp án:** Đầu ra dài 50.000 code units. Nếu mỗi lần nối tạo kết quả mới và chép lại toàn bộ tiền tố, tổng lượng dữ liệu được chép tỷ lệ `10(1 + ... + 5000)`, tăng bậc hai theo số phần.

**Bài 4.** Chỉ cần kiểm tra vùng dài 20 ký tự tại offset 100 của một chuỗi lớn có bằng `target` dài 20 hay không. Phương thức nào tránh tạo substring?

**Đáp án:** `s.regionMatches(100, target, 0, 20)`. Nó so vùng hiện hữu trực tiếp, tối đa theo độ dài vùng so sánh.

**Bài 5.** Tìm kiếm ký tự `'x'` trong chuỗi dài `n` không có `'x'`. Đây là trường hợp nào về thời gian?

**Đáp án:** Thường phải quét hết vùng tìm kiếm, nên là trường hợp `O(n)` của `indexOf('x')`.

## 14. Cách chọn thao tác theo nhu cầu

- **Đọc đúng một vị trí:** `charAt(i)`, chi phí gần hằng số; dùng `codePointAt` nếu muốn lấy một Unicode code point.
- **Kiểm tra một tính chất trên toàn chuỗi:** duyệt một lần, dừng ngay khi đủ điều kiện; tránh quét toàn chuỗi lặp không cần thiết.
- **Tìm một ký tự:** `indexOf(int)` hoặc `lastIndexOf(int)`.
- **Tìm chuỗi con:** `indexOf(String)` / `contains`; cân nhắc độ dài mẫu và số lượng truy vấn.
- **Kiểm tra tiền tố/hậu tố/đoạn:** `startsWith`, `endsWith`, `regionMatches` thay vì tạo substring chỉ để so.
- **So nội dung:** `equals` hoặc `compareTo` đúng ngữ nghĩa; xét trường hợp có tiền tố chung dài.
- **Cần bản sao dữ liệu:** `substring`, `toCharArray`, `getBytes` với chi phí theo kích thước kết quả.
- **Ghép nhiều phần:** `StringBuilder`, `String.join` hoặc `Collectors.joining`; tránh `+=` nối tăng dần ở vòng lặp lớn.

Ghi nhớ: **số phần tử phải đọc, số lần đọc lại và lượng dữ liệu phải tạo ra** thường quyết định chi phí lớn nhất. Hãy đặt đúng kích thước `n, m, k, L`, phân biệt worst case với đường chạy sớm, rồi đo trên dữ liệu thật trước khi tối ưu sâu.

### Tài liệu tham khảo

- [Java SE 17 — `String` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html).
- [Java SE 17 — `StringBuilder` API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html).
- [JEP 254 — Compact Strings](https://openjdk.org/jeps/254).

