# StringBuilder: ensureCapacity(), trimToSize() và chi phí cấp phát bộ nhớ trong Java

`StringBuilder` là bộ đệm ký tự **có thể thay đổi** (*mutable*) để xây dựng văn bản bằng các thao tác `append`, `insert`, `delete`, `replace` và `setLength`. Khác với `String` bất biến, `StringBuilder` có thể tận dụng **dung lượng đã cấp phát** cho nhiều thao tác nối mà không phải tạo ra một đối tượng `String` trung gian sau từng lần thay đổi.

Hai API đặc biệt quan trọng khi muốn quản lý bộ nhớ và hiệu năng là:

- **`ensureCapacity(int minimumCapacity)`:** yêu cầu builder chuẩn bị dung lượng tối thiểu dự kiến sẽ cần, nhằm hạn chế số lần mở rộng bộ đệm trong các lần thêm nội dung tiếp theo.
- **`trimToSize()`:** yêu cầu **thử** thu hẹp bộ đệm dư sau khi đã xây dựng xong hoặc thay đổi nội dung; đây là thao tác *best-effort*, không có cam kết tuyệt đối sẽ đưa `capacity()` bằng `length()`.

Hiểu rõ `length`, `capacity` và chi phí của việc **mở rộng/sao chép bộ đệm** sẽ giúp chọn phương pháp phù hợp thay vì gọi hai API này ở mọi nơi một cách máy móc.

## 1. length và capacity: hai đại lượng khác nhau

Một `StringBuilder` có hai khái niệm:

| Khái niệm | API | Ý nghĩa |
|---|---|---|
| **Độ dài đang sử dụng** | `length()` | Số đơn vị mã UTF-16 (**`char`**) hiện có trong nội dung builder |
| **Dung lượng bộ đệm** | `capacity()` | Số đơn vị mã UTF-16 mà builder có thể chứa trước khi cần mở rộng theo mô hình API |

Luôn có bất biến `capacity() >= length()`. Phần `capacity() - length()` là **dung lượng dự phòng chưa chứa nội dung**. Dung lượng không phải số ký tự nhìn thấy và **không** phải số byte trên heap.

Ví dụ:

```java
StringBuilder sb = new StringBuilder(10);
sb.append("Java");

System.out.println(sb.length());   // 4
System.out.println(sb.capacity()); // 10
```

`new StringBuilder(10)` chỉ cấp **dung lượng ban đầu**; nó **không** tạo sẵn mười ký tự, không tự đệm chuỗi bằng dấu cách và không làm `length()` bằng 10. Sau khi thêm `"Java"`, độ dài bằng 4, dung lượng vẫn là 10.

### Đơn vị UTF-16, không phải Unicode code point

`length()` và `capacity()` tính theo **UTF-16 code units**. Với một emoji ngoài BMP:

```java
StringBuilder emoji = new StringBuilder(2);
emoji.appendCodePoint(0x1F600); // U+1F600
System.out.println(emoji.length()); // 2
System.out.println(emoji.codePointCount(0, emoji.length())); // 1
```

Emoji được biểu diễn bằng **hai** code units (high surrogate + low surrogate), nhưng chỉ là **một** code point. Nếu dự toán dung lượng theo số “ký tự người dùng thấy”, hãy cộng dự toán số UTF-16 units thực tế, không tự giả định mỗi emoji chỉ cần một đơn vị mã.

## 2. Dung lượng ban đầu của StringBuilder

Trong Java 17, các constructor phổ biến có ý nghĩa:

| Constructor | Ý nghĩa |
|---|---|
| `new StringBuilder()` | Builder rỗng, capacity ban đầu **16** |
| `new StringBuilder(int capacity)` | Builder rỗng, capacity ban đầu theo số nguyên chỉ định |
| `new StringBuilder(String str)` | Ban đầu chứa toàn bộ `str`, capacity ban đầu bằng `str.length() + 16` |
| `new StringBuilder(CharSequence seq)` | Ban đầu chứa `seq`, có capacity bằng độ dài sequence cộng 16 theo hợp đồng constructor |

Minh họa:

```java
StringBuilder a = new StringBuilder();
StringBuilder b = new StringBuilder(32);
StringBuilder c = new StringBuilder("Java");

System.out.println(a.length());    // 0
System.out.println(a.capacity());  // 16
System.out.println(b.length());    // 0
System.out.println(b.capacity());  // 32
System.out.println(c.length());    // 4
System.out.println(c.capacity());  // 20
```

Lưu ý:

- `new StringBuilder(0)` hợp lệ: ban đầu không có dung lượng dự phòng; lần thêm đầu tiên có thể phải mở rộng.
- `new StringBuilder(-1)` ném `NegativeArraySizeException`, vì constructor không thể tạo dung lượng âm.
- Constructor nhận `String`/`CharSequence` đã chứa sẵn văn bản và có dự phòng; constructor nhận `int` **không** tạo nội dung.
- Dung lượng dự phòng được quản lý nội bộ, không cần tự điền ký tự giả để “giữ chỗ”.

**Không nhầm `capacity()` với số byte RAM.** Các JDK hiện đại có thể sử dụng biểu diễn bộ nhớ khác nhau cho chuỗi/builder (ví dụ tối ưu *compact strings* trong HotSpot). Overhead đối tượng, mảng nội bộ, encoding, alignment và GC khiến dung lượng tính theo code unit **không chuyển thẳng thành một công thức byte chính xác cho mọi JVM**.

## 3. ensureCapacity(minimumCapacity) làm gì?

Cú pháp:

```java
sb.ensureCapacity(minimumCapacity);
```

Với một builder có capacity hiện tại là `oldCapacity`:

1. Nếu `minimumCapacity <= oldCapacity` thì yêu cầu đã được đáp ứng, nên không cần mở rộng vì lời gọi này.
2. Nếu `minimumCapacity > oldCapacity`, builder chuẩn bị dung lượng **ít nhất bằng** `minimumCapacity`.
3. Dung lượng thực tế có thể **lớn hơn** giá trị yêu cầu do chính sách tăng trưởng nội bộ.
4. Nội dung, `length()` và thứ tự ký tự hiện có **không thay đổi** chỉ vì gọi `ensureCapacity`.

Ví dụ:

```java
StringBuilder sb = new StringBuilder(4);
sb.append("ab");

sb.ensureCapacity(20);
System.out.println(sb.length());          // 2
System.out.println(sb.capacity() >= 20);  // true
System.out.println(sb.toString());        // ab
```

Không nên khẳng định `sb.capacity() == 20` cho mọi trường hợp và mọi phiên bản JVM. Hợp đồng ứng dụng nên dựa vào điều kiện **`>= minimumCapacity`**, không dựa vào một con số chính xác sau khi mở rộng.

### Chính sách tăng trưởng thường gặp

Trong các bản triển khai OpenJDK/HotSpot, dung lượng mới thường được tính theo một chiến lược **tăng theo cấp số nhân**, có dạng gần như `oldCapacity * 2 + 2`, rồi đảm bảo không nhỏ hơn dung lượng tối thiểu cần thiết (kèm giới hạn/kiểm tra với mảng quá lớn). Ví dụ với dung lượng 16, một lần mở rộng điển hình có thể tạo khoảng 34 đơn vị mã thay vì đúng 17.

Đây là **chi tiết triển khai**, không phải công thức để viết logic nghiệp vụ. Các JVM/phiên bản khác có thể dùng chiến lược khác; bạn không nên kiểm thử chương trình bằng điều kiện `capacity() == 34` chỉ vì một JDK trả ra giá trị đó. Khi cần hợp đồng ổn định, chỉ sử dụng `capacity >= nhu cầu`.

### minimumCapacity bằng 0 hoặc âm

`ensureCapacity(0)` hoặc yêu cầu âm không tạo thêm dung lượng; không có ý nghĩa “thu hẹp buffer”. Đây là điểm khác `new StringBuilder(-1)` — constructor với dung lượng âm là bất hợp lệ.

```java
StringBuilder sb = new StringBuilder(8);
sb.ensureCapacity(0);
sb.ensureCapacity(-5);
System.out.println(sb.capacity()); // 8
```

Không dùng `ensureCapacity` để giảm bộ nhớ. Nó chỉ phục vụ **dự phòng dung lượng**, không phải API cắt bớt nội dung hoặc loại bỏ phần dự trữ.

## 4. Khi nào nên gọi ensureCapacity?

Khi bạn biết hoặc ước lượng khá tốt độ dài UTF-16 sẽ xây dựng, dự phòng dung lượng trước thường giảm số lần mở rộng mảng bên trong.

Ví dụ ghép một danh sách từ có dấu phân cách:

```java
import java.util.List;

List<String> words = List.of("Java", "Core", "StringBuilder");

int estimated = 0;
for (String word : words) {
    estimated += word.length();
}
estimated += Math.max(0, words.size() - 1); // Dấu cách giữa các từ

StringBuilder out = new StringBuilder();
out.ensureCapacity(estimated);

for (int i = 0; i < words.size(); i++) {
    if (i > 0) {
        out.append(' ');
    }
    out.append(words.get(i));
}

System.out.println(out.toString()); // Java Core StringBuilder
```

Ví dụ được trình bày như một **đoạn mã dùng trong phương thức** có import `java.util.List`, không phải chương trình độc lập. Nếu danh sách có phần tử `null` hoặc tổng độ dài có thể vượt `Integer.MAX_VALUE`, phải xác định chính sách và kiểm tra overflow trước khi cấp phát.

Với dữ liệu lớn/không đáng tin cậy, nên tính nhu cầu bằng kiểu `long` và giới hạn hợp lý theo yêu cầu ứng dụng; một ước lượng sai do tràn số nguyên có thể dẫn đến capacity âm, thiếu hoặc vượt ngân sách bộ nhớ.

### Có thể dùng constructor để dự phòng ngay

Nếu biết nhu cầu từ trước lúc khởi tạo, có thể viết:

```java
StringBuilder out = new StringBuilder(estimated);
```

thay vì:

```java
StringBuilder out = new StringBuilder();
out.ensureCapacity(estimated);
```

Cả hai đều cho phép chuẩn bị dung lượng. Constructor với kích thước dự kiến thường súc tích hơn nếu ta **chưa tạo builder**, và có thể tránh một lần tạo bộ đệm ban đầu quá nhỏ rồi mở rộng. `ensureCapacity` phù hợp khi builder **đã tồn tại** và nhu cầu tương lai tăng thêm, hoặc khi chỉ có thể ước lượng sau khi đọc thêm thông tin.

**Đừng lạm dụng:** nếu một builder chỉ nhận vài ký tự và bản thân dung lượng mặc định 16 đã đủ, `ensureCapacity` không mang lại lợi ích đo được; nó chỉ làm mã dài hơn.

## 5. Chi phí cấp phát khi StringBuilder lớn dần

Hãy phân biệt hai tình huống:

### Thêm nội dung nhưng vẫn còn chỗ

Khi `length() + appendedUnits <= capacity()`, builder có thể sử dụng phần dự trữ hiện có. Về mặt bộ đệm, không cần tạo một vùng chứa lớn hơn **chỉ vì đã vượt length cũ**.

Ví dụ:

```java
StringBuilder sb = new StringBuilder(8);
sb.append("abc"); // length 3, capacity 8
sb.append("de");  // length 5, capacity 8
```

Thao tác nối vẫn tốn CPU để xử lý dữ liệu, và một số API có thể có cấp phát phụ trợ; nhưng nó không cần **mở rộng bộ đệm chính** khi capacity đủ.

### Thêm nội dung vượt capacity

Khi nội dung mới không còn vừa trong capacity hiện tại, builder phải có vùng lưu trữ nội bộ đủ lớn. Trong một triển khai phổ biến, thao tác này có thể gồm:

1. Xác định dung lượng mới.
2. Cấp phát một vùng chứa ký tự/byte nội bộ lớn hơn.
3. Sao chép nội dung cũ sang vùng mới.
4. Thêm dữ liệu mới vào phần còn trống.
5. Để vùng chứa cũ đủ điều kiện được bộ thu gom rác thu hồi khi không còn tham chiếu tới nó.

Vì vậy, một lần mở rộng có thể tốn **O(n)** theo lượng nội dung phải sao chép lúc đó, kèm chi phí cấp phát/GC. Việc mở rộng theo cấp số nhân tạo ra vùng dự phòng nhằm **giảm tần suất** lặp lại thao tác tốn kém ấy.

### Vì sao append thường có chi phí khấu hao tốt?

Nếu dung lượng tăng theo hệ số lớn hơn 1, các lần mở rộng hiếm dần khi dữ liệu lớn lên. Tổng số đơn vị mã đã phải sao chép trong nhiều lần tăng trưởng sẽ cùng bậc với tổng kích thước cuối trong mô hình tăng trưởng hình học. Vì vậy, khi nối một số lượng lớn nội dung với builder, tổng chi phí quản lý vùng nhớ có thể **khấu hao O(n)** theo kích thước đầu ra (không tính các phép xử lý nội dung đặc biệt), thay vì sao chép toàn bộ tiền tố ở **mọi lần** thêm.

Tuy nhiên:

- **Một lần append đơn lẻ không được bảo đảm O(1)**, vì có thể phải mở rộng và sao chép hoặc thêm một chuỗi có độ dài lớn.
- **O(n)** là phân tích chi phí khấu hao trong mô hình nhất định, không phải thời gian thực thi chính xác trên mọi JVM.
- Dự phòng bằng `ensureCapacity` có thể giảm các lần mở rộng, nhưng **không biến việc ghi n ký tự thành O(1)**; dữ liệu vẫn phải được sao chép vào kết quả ở mức nào đó.
- Việc tăng capacity quá lớn gây lãng phí bộ nhớ, tăng áp lực cấp phát và có thể làm `OutOfMemoryError` xuất hiện sớm hơn.

### So với nối String bằng + trong vòng lặp

`String` bất biến. Mã tạo chuỗi mới bằng phép nối lặp nhiều lần **có thể** tạo và sao chép các tiền tố trung gian, khiến tổng công việc tốn kém, trong khi `StringBuilder` có thể tái sử dụng bộ đệm. Vì thế, với vòng lặp có nhiều thao tác thêm từng phần, `StringBuilder` thường là lựa chọn rõ ràng.

Dẫu vậy, đừng mặc định mọi biểu thức `"a" + x + y` đều phải tạo nhiều đối tượng `String`: compiler/JVM hiện đại có thể tối ưu phép nối bằng `invokedynamic` hoặc cách khác. Chọn theo cấu trúc công việc, sau đó đo bằng công cụ benchmark (ví dụ JMH) nếu hiệu năng thực sự quan trọng.

## 6. trimToSize(): chỉ **thử** thu hẹp vùng dự trữ

Cú pháp:

```java
sb.trimToSize();
```

Theo tài liệu `AbstractStringBuilder`/`StringBuilder`, `trimToSize()` **attempts to reduce storage used**: nếu vùng chứa nội bộ đang rộng hơn lượng ký tự thực tế, triển khai **có thể** thu nhỏ dung lượng. Nhưng API **không cam kết** sau khi gọi luôn có `capacity() == length()`.

Một số điểm cần nhớ:

- `trimToSize()` **không xóa hay đổi nội dung**. `length()` được giữ nguyên.
- Thao tác này **không nối thêm** ký tự.
- Nếu còn nhiều chỗ trống, triển khai có thể cấp phát vùng chứa nhỏ hơn và sao chép dữ liệu sang đó.
- Nếu JVM không thay đổi dung lượng, điều đó vẫn có thể tuân thủ hợp đồng *best-effort*.
- Không có cam kết việc gọi `trimToSize` làm bộ nhớ heap trả lại OS ngay. Vòng đời của mảng cũ, GC và cấp phát bộ nhớ thực tế phụ thuộc JVM.
- Sau khi thu hẹp, **lần append tiếp theo có thể phải mở rộng lại**, dẫn đến thêm cấp phát và sao chép.

Ví dụ:

```java
StringBuilder sb = new StringBuilder(128);
sb.append("done");

int before = sb.capacity(); // 128
sb.trimToSize();

System.out.println(sb.toString());        // done
System.out.println(sb.length());          // 4
System.out.println(sb.capacity() >= 4);   // true
```

Không nên bắt đầu một bài kiểm thử có tính tương thích JVM bằng việc đòi `sb.capacity() == 4` sau `trimToSize`. Mục tiêu chính của API là **đề nghị giảm bộ nhớ dự phòng**, không cam kết một con số cố định.

### Khi nào trimToSize có ích?

Một tình huống phù hợp: bạn đã xây dựng xong một `StringBuilder` có khả năng giữ lại **rất lâu** trong một đối tượng ứng dụng; nội dung thực tế nhỏ hơn nhiều so với capacity từng dự phòng; bạn muốn **thử** giảm footprint trước khi giữ đối tượng lâu dài.

Ví dụ:

```java
StringBuilder cacheValue = new StringBuilder(10_000);
cacheValue.append("small result");
cacheValue.trimToSize(); // Yêu cầu thử giảm phần dự phòng
```

Nếu bạn chỉ cần **chuỗi bất biến cuối cùng**, việc gọi `toString()` rồi bỏ tham chiếu đến `StringBuilder` thường hợp lý hơn là giữ builder lại chỉ để gọi `trimToSize`. `toString()` cho một `String` đại diện nội dung tại thời điểm gọi; bộ đệm builder và chuỗi kết quả là các khái niệm khác nhau.

### Vì sao không nên gọi trimToSize sau mỗi append?

Giả sử một builder liên tục:

```text
append -> trimToSize -> append -> trimToSize -> append -> ...
```

Nếu mỗi `trimToSize` thực sự thu nhỏ vùng chứa về gần độ dài hiện tại, phần dự trữ biến mất sau mỗi bước. Mỗi lần append sau có thể phải cấp phát/sao chép lại, gây hiệu năng kém và tăng GC. **Tránh một chu kỳ thu hẹp–mở rộng liên tục** nếu bạn còn định thêm dữ liệu.

Nguyên tắc: **dự phòng trước giai đoạn tăng trưởng**, chỉ cân nhắc thu hẹp **sau giai đoạn tăng trưởng và khi thật sự có lợi về bộ nhớ**.

## 7. trimToSize khác setLength, delete, clear ra sao?

| API | Thay đổi length? | Thay đổi nội dung? | Tác dụng chính tới capacity |
|---|---|---|---|
| `ensureCapacity(n)` | Không | Không | Đảm bảo tối thiểu n khi cần |
| `trimToSize()` | Không | Không | Thử giảm dung lượng thừa; không cam kết giảm |
| `setLength(n)` | Có | Có thể cắt bớt hoặc bổ sung `\u0000` khi tăng | Không phải API “trả lại bộ nhớ”; có thể mở rộng nếu n lớn |
| `delete(start, end)` | Có | Xóa nội dung theo đoạn | Không bắt buộc giảm capacity |
| `setLength(0)` | Có, còn 0 | Xóa nội dung logic | Thường **giữ capacity** để tái sử dụng |

Ví dụ:

```java
StringBuilder sb = new StringBuilder(64);
sb.append("abcdef");

sb.setLength(3);
System.out.println(sb.toString()); // abc
System.out.println(sb.capacity()); // 64

sb.setLength(0);
System.out.println(sb.length());   // 0
System.out.println(sb.capacity()); // 64
```

`setLength(0)` hữu ích để **tái sử dụng builder** trong nhiều lần xây dựng chuỗi. Nếu sau đó tiếp tục append với kích thước tương tự, giữ capacity có thể là ưu điểm. Đừng gọi `trimToSize` để “clear nội dung”: đó **không** phải ý nghĩa của phương thức này.

Nếu `setLength(n)` tăng độ dài, các vị trí mới được điền ký tự `\u0000` (NUL) chứ không phải dấu cách thông thường. Không dùng cách tăng length để “reserve” dung lượng thay cho `ensureCapacity`, vì khi đó đã thực sự thay đổi văn bản logic.

## 8. Chương trình Java 17+ hoàn chỉnh: quan sát bất biến

Ví dụ cố tình chỉ in **những giá trị được bảo đảm bởi hợp đồng API**, tránh giả định dung lượng cụ thể sau khi mở rộng hay thu hẹp. Lưu vào **`StringBuilderCapacityDemo.java`**:

```java
public class StringBuilderCapacityDemo {
    public static void main(String[] args) {
        StringBuilder sb = new StringBuilder(4);

        System.out.println("initial capacity: " + sb.capacity());

        sb.append("ab");
        System.out.println("after 2 chars: "
                + sb.length() + ", capacity=" + sb.capacity());

        sb.ensureCapacity(20);
        System.out.println("ensured >= 20: " + (sb.capacity() >= 20));

        sb.append("cd");
        System.out.println("after append: " + sb);

        sb.trimToSize();
        System.out.println("trim kept data: " + sb.toString().equals("abcd"));
        System.out.println("after trim >= length: "
                + (sb.capacity() >= sb.length()));

        sb.setLength(2);
        System.out.println("shortened: " + sb);

        StringBuilder emoji = new StringBuilder(2);
        emoji.appendCodePoint(0x1F600);
        System.out.println("emoji units: " + emoji.length());
        System.out.println("emoji codePoints: "
                + emoji.codePointCount(0, emoji.length()));
    }
}
```

Biên dịch/chạy:

```bash
javac -encoding UTF-8 StringBuilderCapacityDemo.java
java StringBuilderCapacityDemo
```

**Stdout:**

```text
initial capacity: 4
after 2 chars: 2, capacity=4
ensured >= 20: true
after append: abcd
trim kept data: true
after trim >= length: true
shortened: ab
emoji units: 2
emoji codePoints: 1
```

**Giải thích kết quả:**

1. Constructor `(4)` tạo builder rỗng có capacity bằng 4.
2. `append("ab")` dùng hai ô mã UTF-16 trong capacity 4, nên capacity vẫn 4.
3. `ensureCapacity(20)` bảo đảm dung lượng **ít nhất 20**; phép kiểm tra boolean luôn `true` theo hợp đồng.
4. `append("cd")` đưa nội dung thành `"abcd"`, không cần biết capacity chính xác.
5. `trimToSize()` có thể giảm dung lượng nhưng **không được phá hỏng nội dung**. `capacity() >= length()` luôn đúng.
6. `setLength(2)` thay đổi **nội dung logic** thành `"ab"`.
7. `appendCodePoint(0x1F600)` thêm một code point được biểu diễn bằng hai đơn vị UTF-16, nên `length() == 2` và `codePointCount(...) == 1`.

Ví dụ nhấn mạnh cách viết test bền vững: kiểm tra **invariant do API bảo đảm**, thay vì đóng đinh chi tiết tối ưu của một phiên bản JVM.

## 9. Đo và ước lượng chi phí bộ nhớ đúng cách

Giả sử bạn định nối n chuỗi `parts[i]` với tổng số UTF-16 units:

\[
L = \sum_{i=0}^{n-1} \mathrm{parts}[i].\mathrm{length}()
\]

Nếu thêm `n - 1` dấu phân cách đơn vị mã đơn, dung lượng dự kiến:

\[
C = L + \max(0, n-1)
\]

Đây là dự toán **số UTF-16 units**, không phải số byte trên heap. Với dấu phân cách là chuỗi dài hơn, phải cộng `delimiter.length() * (n-1)`. Nếu có bất kỳ bước biến đổi nào làm tăng/giảm độ dài, dự toán phải điều chỉnh.

Trong code xử lý input lớn, tránh tràn `int` khi cộng và đặt giới hạn để từ chối input vượt ngân sách:

```java
long needed = 0;
for (String part : parts) {
    needed += part.length();
}
if (needed > 1_000_000L) {
    throw new IllegalArgumentException("Text too large");
}

StringBuilder sb = new StringBuilder((int) needed);
```

Đây là **đoạn minh họa**; giả sử `parts` là tập các chuỗi không null và chưa tính delimiters. Trong ứng dụng thật, cần bổ sung chi phí dấu phân cách và giới hạn dựa trên quy tắc nghiệp vụ. Với các biến `long`, phải tránh overflow nếu dữ liệu có thể cực lớn, dù giới hạn ứng dụng thường loại trừ trường hợp đó sớm hơn.

### Các yếu tố thực tế cần đo

- **Số lần mở rộng**: nhiều lần tăng capacity gây thêm allocations và copy.
- **Dung lượng dự phòng so với dữ liệu thực**: quá nhiều vùng trống kéo dài có thể lãng phí heap nếu builder sống lâu.
- **Chu kỳ sống của builder**: tạo và bỏ nhanh khác với lưu builder trong cache hoặc object lâu dài.
- **Số lần gọi `toString()`**: tạo bản `String` để sử dụng độc lập có chi phí; lặp gọi nhiều lần không thay đổi nội dung có thể làm tăng allocations tùy tối ưu JVM.
- **Kiểu dữ liệu ký tự**: text Latin-1 so với Unicode có thể có cách lưu byte khác nhau trên JVM có compact strings.
- **Bộ thu gom rác và cấu hình heap**: ảnh hưởng latency, throughput và footprint quan sát được.

Nếu tối ưu hiệu năng là yêu cầu thực tế, hãy đo bằng profiler và microbenchmark phù hợp (thường dùng JMH). Không kết luận hiệu quả dựa vào vài lần `System.nanoTime()` khi JVM chưa warm-up.

## 10. Những lựa chọn theo tình huống

| Bối cảnh | Cách thường phù hợp | Lý do |
|---|---|---|
| Chuỗi ngắn chỉ nối vài giá trị | Phép `+` rõ ràng | Compiler/JVM có thể tối ưu tốt; mã dễ đọc |
| Vòng lặp nối nhiều phần | `StringBuilder` | Tái sử dụng buffer thay vì nối tạo nhiều chuỗi trung gian |
| Biết trước tổng độ dài tương đối chính xác | `new StringBuilder(estimated)` | Dự phòng ngay từ đầu |
| Đã có builder và sắp thêm nhiều dữ liệu | `ensureCapacity(neededTotal)` | Giảm nguy cơ phải mở rộng nhiều lần |
| Builder đã hoàn tất nhưng phải giữ lâu, capacity dư quá nhiều | Cân nhắc `trimToSize()` | Thử giảm footprint |
| Builder chỉ là công cụ tạm để ra `String` kết quả | `toString()` rồi bỏ builder | Không cần duy trì buffer dự phòng |
| Tái dùng builder cho từng lượt độc lập | `setLength(0)` | Xóa nội dung logic, thường giữ capacity để tái sử dụng |
| Đa luồng cần cùng một bộ đệm | Thiết kế đồng bộ/ownership rõ ràng; cân nhắc `StringBuffer` nếu phù hợp | `StringBuilder` **không** đồng bộ các thao tác |

Không nên coi bảng là quy tắc tuyệt đối. Nếu đầu vào có độ dài rất biến động, preallocation theo giá trị cực đại của một trường hợp hiếm có thể làm nhiều builder dư thừa bộ nhớ. Ước lượng tốt theo phân bố dữ liệu thực thường hiệu quả hơn đặt capacity cực lớn “cho chắc”.

## 11. Các lỗi thường gặp

| Hiểu nhầm/lỗi | Hậu quả | Cách làm đúng |
|---|---|---|
| “`new StringBuilder(100)` có length 100” | Nhầm dung lượng với nội dung | Builder mới rỗng, `length() == 0` |
| “`ensureCapacity(100)` làm length thành 100” | Không có ký tự mới nào được thêm | Dùng `append` để bổ sung nội dung |
| “`ensureCapacity` luôn đặt capacity đúng số yêu cầu” | Chính sách tăng trưởng có thể cấp nhiều hơn | Chỉ dựa vào `capacity() >= minimumCapacity` |
| “`ensureCapacity` làm giảm capacity khi truyền số nhỏ” | Không đạt mục đích giảm bộ nhớ | `ensureCapacity` chỉ dự phòng; cân nhắc `trimToSize` |
| “`trimToSize` luôn khiến capacity == length” | Phụ thuộc triển khai | API là *best-effort* |
| “`trimToSize` xóa phần nội dung cuối” | Thực tế không thay đổi ký tự hay length | Dùng `setLength`/`delete` để xóa nội dung |
| “`setLength(0)` chắc chắn trả lại RAM” | Thường vẫn giữ buffer đã cấp | Chỉ có length trở về 0 |
| Gọi `trimToSize` sau **mỗi** lần append | Có thể tạo chu kỳ co–giãn, tăng cấp phát/copy | Chỉ cân nhắc sau khi đã xây xong và builder sống lâu |
| Dự toán bằng số emoji thay vì UTF-16 units | Dung lượng thiếu so với nhu cầu thực | Dùng `String.length()` hoặc `Character.charCount(cp)` |
| “Capacity 100 nghĩa là 200 byte RAM” | Bỏ qua compact strings, overhead, alignment, JVM | Đo thực tế, không áp công thức byte cứng |
| Dự toán `int` bị overflow | Capacity sai hoặc lỗi khi cấp phát | Tính với `long`, giới hạn đầu vào rồi mới ép kiểu |
| Cho rằng mọi thao tác `append` luôn O(1) | Có thể sao chép buffer hoặc append dữ liệu lớn | Hiểu chi phí khấu hao và độ dài phần được thêm |

## 12. Bài tập tự kiểm tra

### Bài 1 — Length và capacity

```java
StringBuilder b = new StringBuilder(8);
b.append("abc");
b.ensureCapacity(20);
```

Hỏi: `b.length()` và điều kiện chắc chắn về `b.capacity()` là gì?

**Đáp án:** `length() == 3`; `capacity() >= 20`. Không được kết luận capacity bằng đúng 20 trong mọi triển khai.

### Bài 2 — Trimming

```java
StringBuilder b = new StringBuilder(100);
b.append("xyz");
b.trimToSize();
```

Hỏi: điều gì chắc chắn không đổi và điều gì có thể thay đổi?

**Đáp án:** nội dung `"xyz"` và `length() == 3` không đổi. `capacity` có thể giảm nếu triển khai thực hiện thu hẹp, nhưng API không bắt buộc nó phải bằng 3.

### Bài 3 — Tái sử dụng buffer

```java
StringBuilder b = new StringBuilder(32);
b.append("First");
b.setLength(0);
b.append("Next");
```

**Đáp án:** nội dung cuối là `"Next"`, độ dài bằng 4; `setLength(0)` không xóa capacity dự trữ. Tái sử dụng thường có lợi nếu chuỗi được xây lại nhiều lần.

### Bài 4 — Unicode

Một chuỗi có 10 emoji ngoài BMP, mỗi emoji biểu diễn bằng một surrogate pair. Hỏi riêng phần emoji cần bao nhiêu UTF-16 code units?

**Đáp án:** 20 code units (mỗi emoji có 2). Tổng capacity còn phải tính các ký tự và dấu phân cách khác.

### Bài 5 — Chi phí

Bạn đang tạo nhiều chuỗi, mỗi chuỗi có vài chục ngàn ký tự. Sau **mọi** lần `append`, code gọi `trimToSize`. Vì sao có thể chậm dù bạn muốn tiết kiệm bộ nhớ?

**Đáp án:** sau khi giảm buffer dự phòng, lần append sau có thể buộc cấp phát vùng lớn hơn và sao chép lại dữ liệu. Nếu liên tục co–giãn, tổng chi phí cấp phát/GC và copy tăng cao. Hợp lý hơn là dự phòng theo nhu cầu, build xong mới cân nhắc thu hẹp **nếu giữ builder lâu**.

## 13. Tài liệu chính thức

- [Java SE 17 — StringBuilder](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html): các constructor, `capacity`, `length`, `ensureCapacity`, `trimToSize`, `setLength` và `appendCodePoint`.
- [Java SE 17 — StringBuilder.ensureCapacity(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#ensureCapacity(int)): điều kiện đảm bảo dung lượng tối thiểu và cơ chế tăng trưởng.
- [Java SE 17 — StringBuilder.trimToSize()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html#trimToSize()): hợp đồng *attempts to reduce storage*.
- [Java SE 17 — Character.charCount(int)](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#charCount(int)): số UTF-16 units dùng cho một Unicode code point.

**Ghi nhớ:** `length()` là số UTF-16 code units **đang có**, còn `capacity()` là dung lượng có thể chứa **trước khi mở rộng**. `ensureCapacity(n)` chuẩn bị tối thiểu `n` đơn vị mã và không đổi nội dung; `trimToSize()` chỉ **thử** bỏ vùng dự phòng sau khi xây dựng. Dự phòng hợp lý giúp giảm reallocations, nhưng dự phòng quá mức hoặc liên tục co–giãn gây tốn bộ nhớ và CPU.
