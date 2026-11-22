# Quan hệ giữa equals, hashCode và việc hai chuỗi băm trùng trong Java

Khi so sánh `String` trong Java, `equals()` trả lời câu hỏi **“hai chuỗi có cùng nội dung không?”**; `hashCode()` tính một **giá trị băm `int`** từ nội dung để hỗ trợ các cấu trúc dữ liệu như `HashMap` và `HashSet`. Hai chức năng liên quan chặt chẽ theo một hợp đồng quan trọng:

> Nếu hai `String` bằng nhau theo `equals()`, chúng **bắt buộc** có cùng `hashCode()`. Chiều ngược lại **không đúng**: hai chuỗi **khác nhau** hoàn toàn có thể có giá trị băm trùng (*hash collision*).

Hiểu hợp đồng này giúp tránh nhầm lẫn giữa **định danh**, **so sánh nội dung** và **băm để tìm kiếm**; cũng giải thích vì sao các bộ sưu tập dạng hash vẫn phân biệt được hai chuỗi khác nhau có cùng giá trị băm.

## 1. equals() so sánh điều gì?

`String.equals(Object other)` trả về `true` khi `other` là một đối tượng `String` có cùng **dãy đơn vị mã UTF-16** (cùng chiều dài và cùng giá trị `char` tại từng vị trí). So sánh phân biệt chữ hoa/thường. Ví dụ:

~~~java
String a = "Java";
String b = new String("Java");
String c = "java";

System.out.println(a.equals(b));  // true
System.out.println(a.equals(c));  // false
System.out.println(a == b);       // false
~~~

Đây là **đoạn mã minh họa** đặt trong phương thức Java. `a.equals(b)` bằng `true` vì nội dung giống nhau; `a == b` bằng `false` vì `new String("Java")` tạo một đối tượng riêng. Toán tử `==` với hai tham chiếu đối tượng hỏi chúng có trỏ đến **cùng đối tượng** không; đó không phải phép kiểm tra bằng nhau về nội dung chuỗi.

Lưu ý:

- `equals()` trả về `false` khi đối số `null` hoặc không phải `String` phù hợp.
- Gọi `nullReference.equals(...)` sẽ gây `NullPointerException`. Nếu có thể chứa `null`, dùng `java.util.Objects.equals(a, b)` để so sánh null-safe.
- `String` bất biến: nội dung đã tạo không đổi; vì vậy kết quả `equals()` và `hashCode()` của một đối tượng `String` ổn định suốt vòng đời đối tượng.
- `equalsIgnoreCase()` là **một cách so sánh khác**: nó không biến hai chuỗi khác hoa/thường thành bằng nhau theo `equals()`.

### “Cùng nội dung” trong Java chưa chắc là “trông giống nhau”

`equals()` so sánh dãy UTF-16, không tự chuẩn hóa Unicode. Ví dụ chữ `é` ghép sẵn (`U+00E9`) và chữ `e` cộng dấu sắc kết hợp (`U+0065 U+0301`) có thể trông giống nhau nhưng có dãy code unit khác nhau. Tương tự, `equals()` không tự bỏ khoảng trắng hay không tự chuyển chữ hoa thành chữ thường. Nếu nghiệp vụ muốn coi những cách biểu diễn đó là tương đương, cần **quy định chuẩn hóa/so sánh riêng** trước khi dùng làm khóa.

## 2. hashCode() của String được tính như thế nào?

Theo hợp đồng API Java, `String.hashCode()` được tính từ các giá trị `char` theo công thức đa thức cơ số **31**:

\[
h = s[0]\cdot 31^{n-1} + s[1]\cdot 31^{n-2} + \ldots + s[n-1]
\]

Trong đó `n = s.length()` và `s[i]` là **UTF-16 code unit** ở vị trí `i`, không nhất thiết là một Unicode code point hoàn chỉnh. Phép tính thực hiện với số nguyên `int` 32 bit, nên các phép nhân/cộng có thể **tràn số theo quy tắc Java**, tương ứng kết quả modulo \(2^{32}\); số băm có thể âm. Chuỗi rỗng có `hashCode() == 0`.

Có thể hình dung thuật toán tương đương sau (minh họa logic, không phải mã nguồn nội bộ bắt buộc của JVM):

~~~java
static int manualStringHash(String s) {
    int hash = 0;
    for (int i = 0; i < s.length(); i++) {
        hash = 31 * hash + s.charAt(i);
    }
    return hash;
}
~~~

Đây là **phương thức minh họa** cần đặt trong một lớp Java. Khi tính toán `int`, overflow xảy ra theo quy tắc Java, không tạo ngoại lệ. Đối với `String` thông thường, hàm trên cho cùng kết quả với `s.hashCode()`.

**Ý nghĩa:** cùng một dãy code unit luôn cho cùng một giá trị băm, bất kể hai chuỗi được tạo bằng literal, `new String(...)`, thao tác nối hay đọc từ tệp. Nhưng không có thông tin nào trong giá trị `int` cho phép suy ra duy nhất chuỗi gốc.

## 3. Hợp đồng giữa equals() và hashCode()

| Quan hệ giữa hai chuỗi `a`, `b` | Hệ quả bắt buộc | Điều không thể kết luận |
| --- | --- | --- |
| `a.equals(b) == true` | `a.hashCode() == b.hashCode()` | Không có nghĩa `a == b` |
| `a.hashCode() != b.hashCode()` | `a.equals(b) == false` | Không nói gì về thứ tự từ điển giữa `a` và `b` |
| `a.hashCode() == b.hashCode()` | Chỉ biết hai băm trùng nhau | **Không kết luận** `a.equals(b) == true` |
| `a.equals(b) == false` | Nội dung khác nhau | Hai hash **có thể trùng hoặc khác** |

Một cách ghi nhớ:

~~~text
a.equals(b) == true
        |
        v
a.hashCode() == b.hashCode()

a.hashCode() == b.hashCode()
        |
        +---- có thể a.equals(b) == true
        |
        +---- cũng có thể a.equals(b) == false
              (hash collision)
~~~

Hợp đồng này áp dụng cho các đối tượng có cách triển khai `equals()` và `hashCode()` đúng quy định của `Object`. `String` đã triển khai phù hợp. Khi tự xây dựng lớp làm khóa `HashMap`, nếu ghi đè `equals()` thì thông thường **phải ghi đè `hashCode()` tương thích** để các đối tượng bằng nhau có cùng giá trị băm.

Việc có cùng hash cũng không làm `equals()` trả về `true`, vì `equals()` không định nghĩa sự bằng nhau thông qua mỗi giá trị hash. Giá trị hash chỉ là **bước hỗ trợ tìm kiếm/phân nhóm**.

## 4. Ví dụ va chạm nổi tiếng: "Aa" và "BB"

Hai chuỗi **khác nội dung** sau đây có cùng giá trị hash:

~~~java
String first = "Aa";
String second = "BB";

System.out.println(first.hashCode());      // 2112
System.out.println(second.hashCode());     // 2112
System.out.println(first.equals(second));  // false
~~~

Ta tự tính theo công thức của `String`, với giá trị UTF-16 của các ký tự ASCII:

- `"Aa"`: `'A' = 65`, `'a' = 97` nên `65 * 31 + 97 = 2112`.
- `"BB"`: `'B' = 66` nên `66 * 31 + 66 = 2112`.

Hash bằng nhau vì hai phép tính cho cùng số nguyên; các chữ trong chuỗi vẫn khác nhau. **Đây là va chạm băm**, không phải lỗi của Java.

Va chạm là điều **không thể loại bỏ hoàn toàn** bằng một hàm băm trả về `int`: có vô số chuỗi `String` có thể tạo ra, nhưng giá trị trả về của `hashCode()` chỉ có \(2^{32}\) khả năng. Theo nguyên lý ngăn kéo, nhiều chuỗi khác nhau phải chia sẻ một giá trị hash.

Đặc biệt, ngay cả khi không có overflow, hai chuỗi ngắn như `"Aa"` và `"BB"` đã có thể băm trùng. Vì vậy **không được dùng hash làm bằng chứng duy nhất cho tính bằng nhau**.

## 5. Chương trình Java 17+ kiểm chứng cả equals, HashSet, HashMap

Lưu chương trình sau vào tệp **StringHashCollisionDemo.java**:

~~~java
import java.util.HashMap;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

public class StringHashCollisionDemo {
    public static void main(String[] args) {
        String first = "Aa";
        String second = "BB";
        String sameContent = new String("Aa");

        System.out.println("first hash = " + first.hashCode());
        System.out.println("second hash = " + second.hashCode());
        System.out.println("hash collision = "
                + (first.hashCode() == second.hashCode()));
        System.out.println("first equals second = " + first.equals(second));
        System.out.println("first equals sameContent = "
                + first.equals(sameContent));
        System.out.println("first == sameContent = "
                + (first == sameContent));

        Set<String> set = new HashSet<>();
        set.add(first);
        set.add(second);
        set.add(sameContent);
        System.out.println("set size = " + set.size());

        Map<String, Integer> map = new HashMap<>();
        map.put(first, 1);
        map.put(second, 2);
        map.put(sameContent, 3);

        System.out.println("map size = " + map.size());
        System.out.println("map Aa = " + map.get(new String("Aa")));
        System.out.println("map BB = " + map.get("BB"));
    }
}
~~~

Chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 StringHashCollisionDemo.java
java StringHashCollisionDemo
~~~

**Stdout chính xác:**

~~~text
first hash = 2112
second hash = 2112
hash collision = true
first equals second = false
first equals sameContent = true
first == sameContent = false
set size = 2
map size = 2
map Aa = 3
map BB = 2
~~~

Giải thích:

1. `first` và `second` có cùng hash `2112` nhưng khác nội dung, nên `equals()` trả về `false`.
2. `sameContent` là một đối tượng `String` khác với `first`, nhưng có nội dung `"Aa"` nên `first.equals(sameContent)` trả về `true` và chúng có cùng hash.
3. `HashSet` lưu **hai** phần tử: `"Aa"` và `"BB"`. Giá trị băm trùng **không khiến một chuỗi bị loại**; phần tử thứ ba `sameContent` không được thêm vì **bằng theo `equals()`** với `"Aa"` đã có.
4. `HashMap` giữ **hai** khóa `"Aa"` và `"BB"`. Lệnh `put(sameContent, 3)` cập nhật giá trị gắn với khóa bằng nội dung `"Aa"` từ `1` thành `3`, không tạo khóa thứ ba.
5. Lời gọi `map.get(new String("Aa"))` tìm đúng giá trị `3` dù tham chiếu khóa truyền vào là một đối tượng mới.

Không dựa vào **thứ tự duyệt** `HashMap`/`HashSet` để kiểm thử: các collection này không bảo đảm thứ tự như danh sách. Ví dụ trên chỉ in kích thước và kết quả truy xuất theo khóa, nên không phụ thuộc thứ tự lặp.

## 6. Vì sao HashMap và HashSet vẫn hoạt động khi hash trùng?

Ý tưởng tổng quát của cấu trúc hash trong Java là kết hợp **mã băm để khoanh vùng tìm kiếm** và **so sánh bằng nhau để xác nhận đúng khóa**:

~~~text
key (String)
     |
     v
hashCode() --> chọn vị trí/vùng tìm kiếm trong bảng
                    |
                    v
                các mục ứng viên
                    |
                    v
             kiểm tra bằng nhau
             (equals/định danh)
                    |
            +-------+--------+
            |                |
         bằng nhau        không bằng
            |                |
      cùng khóa logic     khóa khác, dù
      (cập nhật/tra)      hash có thể trùng
~~~

Sơ đồ là **mô hình khái niệm**. Triển khai thực tế của `HashMap` có bước trộn bit hash, lựa chọn bucket, tổ chức bucket và tối ưu khác theo phiên bản JDK. Điều cốt lõi của ngữ nghĩa công khai là các khóa `String` được phân biệt theo `equals()`, không dựa độc quyền vào `hashCode()`.

- **Hash trùng + `equals()` trả về `true`:** cùng một khóa logic, thường ghi đè/cập nhật giá trị trong `HashMap`; `HashSet.add()` không tăng kích thước.
- **Hash trùng + `equals()` trả về `false`:** hai khóa logic khác nhau, đều có thể tồn tại trong `HashMap` và `HashSet`.
- **Hash khác:** hai `String` không thể bằng nhau theo `equals()` vì vi phạm chiều thuận của hợp đồng nếu chúng bằng nhau.

Việc nhiều khóa băm trùng có thể làm tăng số lần so sánh và ảnh hưởng **hiệu năng**, nhưng không được phép phá vỡ kết quả đúng của tra cứu. Các tối ưu ở cấp triển khai không biến hash thành định danh duy nhất.

### Phân biệt ba thứ dễ nhầm

| Thao tác | Câu hỏi được trả lời | Có thể dùng để thay thế thao tác kia không? |
| --- | --- | --- |
| `a == b` | Có cùng tham chiếu đối tượng không? | Không thay `equals()` khi cần nội dung |
| `a.equals(b)` | Có bằng nhau theo giá trị `String` không? | Đúng cho so sánh nội dung nguyên văn |
| `a.hashCode() == b.hashCode()` | Có cùng mã băm 32 bit không? | **Không** thay `equals()` vì có collision |

Nếu mục tiêu thật sự là **khóa nội dung chuỗi**, hãy truyền chính `String` làm khóa `Map<String, ...>` hoặc phần tử của `Set<String>`. Không biến chuỗi thành một `int` qua `hashCode()` rồi dùng `int` đó làm “mã duy nhất” để lưu trữ hoặc ghi đè dữ liệu.

## 7. Tự triển khai hàm băm tương đương để kiểm chứng

Để hiểu vì sao giá trị băm phụ thuộc **nội dung UTF-16**, có thể tự hiện thực phép tính:

~~~java
public class ManualStringHashDemo {
    static int compute(String s) {
        int result = 0;
        for (int index = 0; index < s.length(); index++) {
            result = 31 * result + s.charAt(index);
        }
        return result;
    }

    public static void main(String[] args) {
        String[] examples = {"", "Aa", "BB", "Java", "😀"};
        for (String text : examples) {
            System.out.println(compute(text) == text.hashCode());
        }
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac -encoding UTF-8 ManualStringHashDemo.java
java ManualStringHashDemo
~~~

Kết quả:

~~~text
true
true
true
true
true
~~~

Chương trình trên cho thấy `hashCode()` của `String` được xác định theo công thức công khai, kể cả với chuỗi chứa emoji gồm một cặp surrogate. **Kích thước bộ nhớ nội bộ** hoặc cách JVM tối ưu đối tượng không làm thay đổi giá trị hash mà API cam kết.

Cũng vì hash dùng đơn vị UTF-16 theo công thức, nó **không phải** mã hóa UTF-8, checksum của byte tệp hay hàm đếm Unicode code point. Hash không cho biết chuỗi dài bao nhiêu ký tự hiển thị và không thể dùng để khôi phục nội dung ban đầu.

## 8. So sánh khác quy tắc thì phải thiết kế quy tắc khóa nhất quán

### Chữ hoa/chữ thường

`equalsIgnoreCase()` không tham gia hợp đồng `String.hashCode()`. Ví dụ:

~~~java
System.out.println("A".equalsIgnoreCase("a")); // true
System.out.println("A".equals("a"));           // false
System.out.println("A".hashCode());            // 65
System.out.println("a".hashCode());            // 97
~~~

Đây là **đoạn mã minh họa** đặt trong phương thức. Hai chuỗi có thể bằng nhau dưới **quy tắc bỏ qua hoa/thường**, nhưng hash vẫn khác vì `String.hashCode()` tính theo **nội dung gốc**. Điều này hoàn toàn phù hợp với hợp đồng `equals()` của `String` vì `"A".equals("a")` là `false`.

Muốn một bảng tra cứu không phân biệt hoa/thường, cần chủ động xác định quy tắc nghiệp vụ: chẳng hạn chuẩn hóa các khóa trước khi lưu và tra bằng cùng một quy tắc, hoặc dùng cấu trúc/comparator phù hợp như `TreeMap<>(String.CASE_INSENSITIVE_ORDER)` nếu hành vi so sánh của comparator đáp ứng yêu cầu. Với Unicode đa ngôn ngữ, quy tắc chuyển hoa/thường, locale và so sánh không nhạy hoa/thường cần được xem xét cẩn thận; chuyển `toLowerCase()` tùy tiện không tự bảo đảm mọi hình thức case folding hay chuẩn hóa mong muốn.

### Unicode normalization

Chữ `é` có thể được biểu diễn bằng code point ghép sẵn `U+00E9` hoặc `e` + dấu sắc `U+0301`:

~~~java
import java.text.Normalizer;

// Đoạn mã minh họa bên trong phương thức Java:
String composed = "\u00E9";
String decomposed = "e\u0301";

System.out.println(composed.equals(decomposed)); // false
System.out.println(composed.hashCode());         // 233
System.out.println(decomposed.hashCode());       // 3900

String normalized = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
System.out.println(composed.equals(normalized)); // true
~~~

Vì dãy code unit khác nhau, `equals()` và `hashCode()` trên chuỗi **chưa chuẩn hóa** cũng có thể khác. Trong trường hợp này, NFC chuyển chuỗi decomposed thành nội dung ghép sẵn, nên `equals()` trả về `true` và theo hợp đồng hash cũng trùng.

Nếu muốn coi những chuỗi tương đương theo chuẩn Unicode là cùng khóa, phải **chuẩn hóa nhất quán cả lúc thêm và lúc tra cứu**, và quy tắc nào được coi là “tương đương” phải được ghi rõ trong ứng dụng. Không thể dùng một mình `hashCode()` để thực hiện việc chuẩn hóa hay so sánh ngữ nghĩa.

## 9. Những sai lầm thường gặp

| Sai lầm | Vì sao sai | Cách làm đúng |
| --- | --- | --- |
| `a.hashCode() == b.hashCode()` thì chắc chắn `a.equals(b)` | Hash collision tồn tại; `"Aa"` và `"BB"` là phản ví dụ | Khi cần biết cùng nội dung, dùng `equals()` |
| Hai chuỗi có cùng hash nên `HashSet` sẽ chỉ lưu một | `HashSet` phân biệt phần tử bằng logic bằng nhau | `"Aa"` và `"BB"` cùng tồn tại |
| `==` thay cho `equals()` | `==` với tham chiếu kiểm tra danh tính đối tượng | Dùng `equals()` với chuỗi |
| Dùng `hashCode()` làm ID duy nhất của chuỗi | Chỉ là số nguyên 32 bit, có collision | Giữ khóa là chuỗi gốc hoặc dùng ID riêng được quản lý |
| Dùng hash để phát hiện chuỗi bị thay đổi hay dữ liệu bị giả mạo | `String.hashCode()` không phải hash mật mã, dễ cố ý tạo collision | Chọn công cụ cryptographic phù hợp với bài toán an ninh |
| Dùng `equalsIgnoreCase()` nhưng nghĩ hash cũng bỏ qua hoa/thường | `hashCode()` vẫn theo nội dung `String` chính xác | Thiết kế chuẩn hóa/so sánh khóa thống nhất |
| Các ký tự hiển thị giống nhau phải có cùng hash | Dãy Unicode code unit có thể khác | Xác định quy tắc Unicode normalization trước |
| `String.hashCode()` phụ thuộc địa chỉ đối tượng | Hash của `String` tính từ nội dung | Hai đối tượng `String` nội dung bằng nhau luôn hash bằng nhau |
| Chỉ so sánh hash để tiết kiệm thời gian | Có thể báo bằng nhau sai; chi phí hash cũng không miễn phí | Dùng collection và API so sánh chuẩn, để cấu trúc xử lý collision |

**Lưu ý về bảo mật:** `String.hashCode()` là mã băm **không dùng cho mục đích mật mã**; dễ dự đoán và dễ tìm collision. Không dùng nó cho chữ ký, xác thực mật khẩu, kiểm tra tính toàn vẹn chống sửa đổi hoặc chứng minh duy nhất. Bài toán an ninh cần thuật toán và thiết kế phù hợp riêng.

## 10. Checklist khi dùng String làm khóa

1. Xác định **“hai khóa được coi là bằng nhau”** theo quy tắc nào: nguyên văn, bỏ qua hoa/thường, Unicode normalization hay quy tắc nghiệp vụ khác?
2. Nếu là **nguyên văn**, dùng `String` trực tiếp làm khóa `HashMap<String, V>` / `HashSet<String>`; `equals()` và `hashCode()` của `String` đã phù hợp với nhau.
3. Nếu cần **chuẩn hóa**, thực hiện cùng một phép biến đổi cho mọi khóa lúc lưu và truy xuất; lưu ý locale và dữ liệu Unicode.
4. Không so sánh duy nhất bằng hash và không biến `hashCode()` thành mã định danh duy nhất.
5. Kiểm thử cả cặp **khác nội dung nhưng hash trùng** như `"Aa"` và `"BB"`, và cặp **bằng nội dung nhưng khác đối tượng** như literal `"Aa"` và `new String("Aa")`.
6. Khi nhận giá trị có thể `null`, dùng cơ chế kiểm tra null phù hợp; không gọi `s.equals()` hoặc `s.hashCode()` trực tiếp trên tham chiếu `null`.
7. Đánh giá hiệu năng nếu có nhiều khóa do nguồn không tin cậy cố ý chọn gây collision; kết quả đúng và đặc tính hiệu năng là hai mối quan tâm riêng.

## 11. Tự kiểm tra

**Câu 1.** Nếu `a.equals(b)` là `true`, có trường hợp `a.hashCode() != b.hashCode()` với hai `String` Java hợp lệ không?

**Đáp án:** không. Đây là chiều bắt buộc của hợp đồng `equals()` / `hashCode()`.

**Câu 2.** Nếu hai `String` có cùng `hashCode()`, có đủ dữ kiện khẳng định chúng bằng nhau không?

**Đáp án:** không. `"Aa"` và `"BB"` cùng hash `2112` nhưng `equals()` trả về `false`.

**Câu 3.** Đưa `"Aa"` và `"BB"` vào `HashSet<String>` có bao nhiêu phần tử?

**Đáp án:** hai. Chúng có hash trùng nhưng khác nhau theo `equals()`.

**Câu 4.** Với `Map<String, Integer> m`, sau `m.put("Aa", 1); m.put(new String("Aa"), 2);`, kích thước tăng thành hai không?

**Đáp án:** không. Hai khóa bằng nhau theo `equals()`, nên khóa logic `"Aa"` được cập nhật giá trị thành `2`; kích thước vẫn là một.

**Câu 5.** Vì sao `"A".equalsIgnoreCase("a")` bằng `true`, nhưng hash `65` và `97` khác nhau vẫn không vi phạm hợp đồng?

**Đáp án:** hợp đồng dựa trên `equals()`, mà `"A".equals("a")` bằng `false`. `equalsIgnoreCase()` là quy tắc so sánh khác.

**Câu 6.** Vì sao không nên lưu `String.hashCode()` làm ID độc nhất của tên đăng nhập?

**Đáp án:** nhiều chuỗi khác nhau có thể cùng hash; nếu dùng hash làm ID duy nhất, người dùng khác nhau có thể bị đồng nhất nhầm. Cần lưu và so sánh theo khóa đúng hoặc hệ thống ID riêng có kiểm soát.

## Tài liệu tham khảo

- [Java SE 17 — String](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): hợp đồng của `equals()`, `hashCode()`, `equalsIgnoreCase()` và công thức băm chuỗi.
- [Java SE 17 — Object](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Object.html): hợp đồng tổng quát giữa `equals()` và `hashCode()`.
- [Java SE 17 — HashMap](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashMap.html): hành vi bảng băm với khóa và giá trị.
- [Java SE 17 — HashSet](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/HashSet.html): tập hợp không lưu các phần tử trùng theo quan hệ bằng nhau.
- [Java SE 17 — Normalizer](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): chuẩn hóa biểu diễn Unicode khi yêu cầu nghiệp vụ cần.
