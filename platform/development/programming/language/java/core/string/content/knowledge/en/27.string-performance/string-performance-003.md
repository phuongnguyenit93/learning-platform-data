# Ước lượng `capacity` của `StringBuilder` trong Java

## Mục tiêu

Khi ghép nhiều chuỗi trong vòng lặp, việc tạo `StringBuilder` với dung lượng ban đầu phù hợp có thể giảm số lần mở rộng vùng chứa trung gian. Tuy nhiên, chọn quá lớn sẽ giữ tài nguyên không cần thiết. Bài học này giải thích `capacity` là gì, cách ước lượng từ dữ liệu đầu vào, khi nào dùng `new StringBuilder(capacity)` hoặc `ensureCapacity()` và cách kiểm chứng giả định bằng Java 17+.

## 1. Phân biệt `length` và `capacity`

`StringBuilder` là đối tượng lưu một chuỗi ký tự có thể thay đổi (mutable). Hai thuộc tính dễ nhầm là:

- `length()`: số **đơn vị mã UTF-16 đang có nội dung** trong builder.
- `capacity()`: số **đơn vị mã UTF-16 có thể chứa trước khi cần mở rộng**. Dung lượng có thể lớn hơn `length()`.

Luôn có `0 <= length() <= capacity()`. Khi `append()` thêm nội dung, `length()` tăng theo lượng văn bản thực sự thêm; nếu cần nhiều chỗ hơn, builder tự tăng `capacity()`. Khi gọi `toString()`, chuỗi được trả về có nội dung theo `length()`, không kèm phần dung lượng chưa sử dụng.

Ví dụ nếu một builder đang có `length() == 5` và `capacity() == 20`, bạn có thể thêm tối đa 15 đơn vị UTF-16 trước khi cần mở rộng vùng chứa. **Capacity không phải số byte**, không nhất thiết là số Unicode code point, và cũng không phải độ dài tối đa vĩnh viễn của `StringBuilder`.

### Giá trị khởi tạo thường gặp

| Lời gọi | `length()` ban đầu | `capacity()` ban đầu |
| --- | ---: | ---: |
| `new StringBuilder()` | 0 | 16 |
| `new StringBuilder(100)` | 0 | 100 |
| `new StringBuilder("")` | 0 | 16 |
| `new StringBuilder("abc")` | 3 | 19 |
| `new StringBuilder(existingSeq)` | `existingSeq.length()` | `existingSeq.length() + 16` |

Bộ dựng từ `String` hoặc `CharSequence` vừa **chép nội dung** vừa dành thêm dung lượng. Ngược lại, bộ dựng với số nguyên chỉ tạo vùng chứa với capacity được yêu cầu, chưa thêm văn bản. `new StringBuilder(-1)` ném `NegativeArraySizeException`. Khi dữ liệu đầu vào là một chuỗi đã biết, `new StringBuilder(existingString)` hợp lý hơn việc tự ghép chuỗi đó thêm lần nữa.

## 2. Tại sao cần ước lượng dung lượng?

Giả sử bạn tạo một chuỗi kết quả dài hàng chục nghìn đơn vị UTF-16 từ hàng nghìn đoạn nhỏ. Nếu bắt đầu với capacity rất thấp, builder có thể phải cấp phát vùng chứa lớn hơn và sao chép nội dung đã có khi vượt giới hạn. Việc cấp phát trước gần với kích thước cuối cùng thường giúp giảm các lần mở rộng, đặc biệt khi xử lý khối lượng lớn lặp lại thường xuyên.

Dẫu vậy, `StringBuilder` **tự mở rộng khi cần**; việc không đoán trước dung lượng không làm chuỗi sai. Mục tiêu là giảm cấp phát và sao chép nếu đây thực sự là phần việc tốn thời gian.

Hai kiểu sử dụng phổ biến:

```java
// Đơn giản, thường đủ tốt với chuỗi nhỏ hoặc chưa biết độ dài.
StringBuilder message = new StringBuilder();
message.append("Hello, ").append("Java");

// Khi đã biết gần đúng kích thước kết quả.
int expectedLength = 1024;
StringBuilder buffer = new StringBuilder(expectedLength);
```

Đây là các đoạn minh họa trong ngữ cảnh của một phương thức. Capacity **không** giới hạn nội dung ở 1024: append thêm vẫn có thể khiến bộ đệm lớn lên.

### Cách tăng capacity khi bị đầy

Với triển khai OpenJDK được dùng trong Java 17, tăng dung lượng tự động thường chọn ít nhất:

```text
newCapacity ≈ max(minimumCapacity, oldCapacity * 2 + 2)
```

Trong đó `minimumCapacity` là số đơn vị UTF-16 cần chứa sau thao tác. Công thức có các nhánh xử lý tràn số và giới hạn mảng; vì vậy đây là **mô tả quy tắc tăng thông thường của triển khai**, không phải cam kết rằng mọi JDK hoặc mọi trường hợp đều trả về đúng công thức. Theo API, điều quan trọng là builder đảm bảo có chỗ cho nội dung nếu có thể cấp phát.

Ví dụ: từ capacity 4, `append` làm length vượt 4 sẽ mở rộng. Không nên dựa vào capacity cụ thể sau khi tăng để tính đúng/sai của chương trình.

## 3. Công thức ước lượng từ các phần sẽ nối

Nếu các đoạn văn bản và ký tự phân cách đã biết, ta có thể tính **chính xác số đơn vị UTF-16 của kết quả** trước khi tạo builder:

```text
estimatedCapacity = tổng length() của các phần dữ liệu
                  + tổng độ dài của các dấu phân cách
                  + độ dài prefix/suffix/nhãn cố định
                  + độ dài các ký tự được thêm có điều kiện
```

Ví dụ nối `n` chuỗi với một dấu phẩy giữa hai phần, **không có dấu phẩy cuối**:

```text
estimatedCapacity = sum(part.length()) + max(0, n - 1)
```

Với dấu phân cách là một `String separator` bất kỳ:

```text
estimatedCapacity = sum(part.length())
                  + max(0, n - 1) * separator.length()
```

Trong công thức trên, `length()` đo **đơn vị UTF-16**; đây chính là đơn vị cần dùng cho capacity. Nếu nối thêm `\n` một lần sau mỗi dòng, cần tính thêm một đơn vị cho mỗi `\n`. Với dấu xuống dòng `\r\n`, cần thêm hai đơn vị mỗi lần. Với `System.lineSeparator()`, lấy `separator.length()` thay vì giả định có đúng một ký tự.

### Ví dụ đầy đủ: nối dữ liệu với dấu phân cách

Lưu thành `CapacityEstimateDemo.java`:

```java
import java.util.List;

public class CapacityEstimateDemo {
    public static void main(String[] args) {
        List<String> parts = List.of("Java", "17", "StringBuilder");
        String separator = ",";

        int estimate = 0;
        for (String part : parts) {
            estimate = Math.addExact(estimate, part.length());
        }
        int separatorCount = Math.max(0, parts.size() - 1);
        int separatorsLength = Math.multiplyExact(
                separatorCount, separator.length());
        estimate = Math.addExact(estimate, separatorsLength);

        StringBuilder result = new StringBuilder(estimate);
        for (int i = 0; i < parts.size(); i++) {
            if (i > 0) {
                result.append(separator);
            }
            result.append(parts.get(i));
        }

        System.out.println("estimated=" + estimate);
        System.out.println("length=" + result.length());
        System.out.println("capacity=" + result.capacity());
        System.out.println("text=" + result);
    }
}
```

Chạy trên Java 17+:

```bash
javac CapacityEstimateDemo.java
java CapacityEstimateDemo
```

Kết quả:

```text
estimated=21
length=21
capacity=21
text=Java,17,StringBuilder
```

`"Java"` dài 4, `"17"` dài 2 và `"StringBuilder"` dài 13; thêm 2 dấu phẩy = 21. Vì builder được tạo đúng capacity cần thiết, chương trình không cần mở rộng khi nối dữ liệu này. Khi `parts` rỗng, công thức cho 0 và builder có capacity 0; khi chỉ có một phần, không có separator.

Hai phương thức `Math.addExact` và `Math.multiplyExact` giúp phát hiện tràn `int` khi tổng hợp kích thước, thay vì âm thầm tạo một số âm hoặc quá nhỏ. Chúng ném `ArithmeticException` khi tràn. Tuy nhiên, một số capacity cực lớn dù còn nằm trong phạm vi `int` vẫn có thể không cấp phát được vì giới hạn của máy ảo hoặc bộ nhớ.

**Điểm đánh đổi:** tính chính xác toàn bộ độ dài đầu vào tốn thêm một lượt duyệt. Nếu dữ liệu đã được duyệt để xác thực hoặc thống kê thì gần như có sẵn; nếu tất cả đoạn cực ngắn, chi phí đo trước có thể lớn hơn lợi ích tránh vài lần mở rộng. Hãy đo trong tình huống thực tế.

## 4. Khi không biết chính xác kích thước kết quả

Một số đoạn văn bản được tạo ra từ số hoặc phép chuyển đổi định dạng. Cần phân biệt **giá trị** với **số ký tự sau chuyển đổi**:

- `builder.append(12345)` thêm 5 đơn vị UTF-16, không phải 12.345 đơn vị.
- `builder.append(-12)` thêm 3 đơn vị: dấu `-` và hai chữ số.
- `builder.append(true)` thêm 4 đơn vị, `false` thêm 5.
- `builder.append((String) null)` thêm chuỗi `"null"` dài 4.
- `builder.append('\n')` thêm 1 đơn vị; `builder.append("\r\n")` thêm 2.
- `builder.append("😀")` thêm 2 đơn vị UTF-16 dù người dùng nhìn thấy một emoji.

Nếu đối số đến từ `String.valueOf(x)`, `toString()`, `String.format()`, JSON serializer hoặc formatter theo locale, dung lượng phụ thuộc **đầu ra thực tế** (ví dụ dấu nhóm hàng nghìn, số chữ số, escape, khoảng trắng, trường tùy chọn). Không dùng số byte UTF-8 hay số trường dữ liệu làm capacity trực tiếp.

Khi chưa biết chính xác, có thể dùng ước lượng theo số bản ghi:

```java
int rowCount = 500;
int estimatedUnitsPerRow = 48;
int estimate = Math.multiplyExact(rowCount, estimatedUnitsPerRow);
StringBuilder report = new StringBuilder(estimate);
```

Đây là đoạn minh họa, giả định ước lượng trung bình 48 đơn vị UTF-16 cho mỗi dòng **đã bao gồm dấu phân cách hoặc newline**. Với 500 dòng, estimate bằng 24.000. Nếu thực tế dài hơn, builder vẫn tự mở rộng; nếu thực tế ngắn hơn, phần dư không xuất hiện trong chuỗi kết quả nhưng vùng chứa có thể chiếm bộ nhớ.

### Chọn giữa ước lượng chính xác và ước lượng gần đúng

| Dữ liệu | Cách tính phù hợp | Lý do |
| --- | --- | --- |
| Danh sách các `String` có sẵn | Cộng `length()`, prefix, suffix và separator | Có thể tính chính xác |
| Ghép `char` hoặc newline cố định | Cộng số lần thêm nhân độ dài từng thành phần | Thường tính chính xác |
| Dòng CSV cần escape dấu ngoặc kép | Tính sau escaping, hoặc ước lượng dựa trên dữ liệu | Dữ liệu nguồn có thể dài ra |
| Số, ngày, phần trăm định dạng theo locale | Tính độ dài chuỗi đã định dạng nếu cần chính xác | Kích thước phụ thuộc cách biểu diễn |
| Số lượng bản ghi biết nhưng nội dung biến động | Dung lượng trung bình nhân số bản ghi | Ước lượng đủ dùng |
| Luồng không biết lúc nào kết thúc | Bắt đầu vừa phải, mở rộng khi cần, có thể `ensureCapacity` | Không có tổng độ dài đáng tin |

Một công thức quá phức tạp, trùng lặp logic với chính bước nối chuỗi, có thể dễ sai và gây thêm overhead. Ước lượng nên phục vụ tối ưu hóa, không trở thành nguồn lỗi nghiệp vụ.

## 5. `ensureCapacity`, `setLength` và `trimToSize` khác nhau thế nào?

`StringBuilder` có ba API dễ bị hiểu nhầm:

| API | Tác động lên `length()` | Tác động lên `capacity()` |
| --- | --- | --- |
| `ensureCapacity(minimum)` | Không đổi | Bảo đảm tối thiểu số đơn vị UTF-16 được yêu cầu nếu cần tăng; có thể tăng nhiều hơn |
| `setLength(newLength)` | Đổi đúng thành `newLength` | Có thể phải tăng khi `newLength` vượt capacity; phần được thêm có giá trị `\u0000` |
| `trimToSize()` | Không đổi | Cố giảm phần dung lượng chưa dùng; API không bảo đảm luôn đạt đúng `length()` |

`ensureCapacity` phù hợp khi **đã tạo builder và sau đó mới biết nhu cầu lớn hơn**:

```java
StringBuilder builder = new StringBuilder();
builder.append("header:");
builder.ensureCapacity(1000);
builder.append("data");

System.out.println(builder.length());           // 11
System.out.println(builder.capacity() >= 1000); // true
```

Đây là đoạn có thể chạy trong `jshell` hoặc trong phương thức. Lệnh `ensureCapacity(1000)` không thêm 1000 ký tự; nó chỉ yêu cầu chỗ trống. Nếu số được truyền nhỏ hơn hoặc bằng 0, `ensureCapacity` không cần thay đổi dung lượng. Nó không phải lời hứa "capacity đúng bằng 1000": sau tăng, capacity có thể lớn hơn.

Đừng dùng `setLength(1000)` để "đặt trước capacity" vì nó làm cho chuỗi thực sự có độ dài 1000 bằng cách thêm các đơn vị `\u0000`. Các đơn vị NUL đó là **nội dung thật**, làm sai dữ liệu nếu gửi đi hoặc ghi tệp. Để dành chỗ, dùng constructor hoặc `ensureCapacity`.

`trimToSize()` có thể giúp giải phóng phần dư lớn sau một giai đoạn nối chuỗi nếu phải giữ builder lâu, nhưng cũng có thể khiến lần nối tiếp theo lại phải mở rộng. Đừng gọi nó sau mỗi `append()`.

## 6. Quan sát mở rộng dung lượng trong Java

Lưu thành `BuilderGrowthDemo.java`:

```java
public class BuilderGrowthDemo {
    public static void main(String[] args) {
        StringBuilder builder = new StringBuilder(4);
        System.out.println("initial=" + builder.length() + "/" + builder.capacity());

        builder.append("abcd");
        System.out.println("filled=" + builder.length() + "/" + builder.capacity());

        builder.append('e');
        System.out.println("expanded=" + builder.length() + "/" + builder.capacity());

        builder.append("0123456789");
        System.out.println("expanded-again=" + builder.length()
                + "/" + builder.capacity());

        StringBuilder initial = new StringBuilder();
        StringBuilder fromText = new StringBuilder("abc");
        System.out.println("default=" + initial.capacity());
        System.out.println("from-text=" + fromText.capacity());
    }
}
```

Chạy:

```bash
javac BuilderGrowthDemo.java
java BuilderGrowthDemo
```

Trên OpenJDK thông dụng (đã kiểm chứng với triển khai OpenJDK), kết quả:

```text
initial=0/4
filled=4/4
expanded=5/10
expanded-again=15/22
default=16
from-text=19
```

Ở lần đầu, builder có 4 chỗ. Sau `"abcd"` nó đầy nhưng chưa tăng. Thêm `'e'` làm length lên 5 nên capacity mở rộng thành 10. Thêm 10 ký tự tiếp theo làm length thành 15, capacity lúc đó thành 22. **Các giá trị mở rộng sau append mang tính quan sát triển khai**, không phải điều kiện mà code ứng dụng cần phụ thuộc vào. Giá trị capacity từ bộ dựng được tài liệu Java định nghĩa rõ hơn và có thể dùng trực tiếp để kiểm chứng ước lượng.

## 7. Unicode: vì sao không dùng byte hoặc số code point làm capacity?

Với `StringBuilder`, `length()` và `capacity()` đo theo **đơn vị mã UTF-16**, không phải byte UTF-8. Ví dụ:

```java
import java.nio.charset.StandardCharsets;

String value = "A\uD83D\uDE00";
StringBuilder builder = new StringBuilder(value.length());
builder.append(value);

System.out.println(builder.length());
System.out.println(builder.capacity());
System.out.println(value.codePointCount(0, value.length()));
System.out.println(value.getBytes(StandardCharsets.UTF_8).length);
```

Có thể chạy trong `jshell`; kết quả lần lượt là:

```text
3
3
2
5
```

`"A😀"` gồm 3 đơn vị UTF-16, 2 code point và 5 byte UTF-8. Vì vậy capacity cần để append đúng một bản `value` là 3. Nếu dùng 2 (code point count), builder vẫn chạy nhưng phải mở rộng. Nếu dùng 5 (byte UTF-8), builder sẽ cấp dư theo đơn vị capacity.

Một dấu kết hợp hoặc cụm emoji phức tạp còn có thể gồm nhiều code point nhưng người đọc cảm nhận như một ký tự. Không dùng số grapheme cluster để đo capacity. Nếu có thao tác thêm mã Unicode bằng `appendCodePoint(int)`, số đơn vị tăng là `Character.charCount(codePoint)`: 1 cho ký tự BMP hợp lệ, 2 cho ký tự bổ sung.

Đừng suy luận bộ nhớ heap thực tế bằng công thức cứng `capacity * 2`. Triển khai Java hiện đại có thể dùng Compact Strings và cơ chế lưu trữ trong JVM; có chi phí đối tượng, mảng, căn chỉnh và mã hóa nội bộ. `capacity()` là chỉ số hữu ích để dự báo **chỗ chứa logic**, không phải đồng hồ đo byte RAM.

## 8. Tối ưu hóa đúng chỗ

Chỉ định dung lượng là tối ưu hóa đáng cân nhắc khi:

1. Nối rất nhiều phần trong vòng lặp và kích thước cuối tương đối đoán được.
2. Mỗi yêu cầu hoặc mỗi lần xử lý đều tạo ra builder lớn; chi phí cấp phát và copy xuất hiện trong profiler.
3. Kết quả luôn theo mẫu ổn định: có nhãn, phân cách hoặc số bản ghi đã biết.
4. Một builder lớn được dùng trong đường chạy nóng và việc chọn capacity đã được benchmark chứng minh có lợi.

Không nhất thiết chỉ định capacity trong mọi lệnh nối vài từ. `StringBuilder()` mặc định đã có một lượng chỗ nhỏ; compiler cũng có thể tối ưu nhiều biểu thức nối chuỗi bằng `+` theo cách riêng. Đừng thay mọi phép nối chuỗi bằng một builder chỉ vì tin rằng constructor có số capacity luôn nhanh hơn.

Chú ý những trường hợp gây phản tác dụng:

- **Ước lượng quá thấp:** vẫn tự tăng nhiều lần, có thể cấp phát/sao chép trung gian.
- **Ước lượng quá cao:** lãng phí vùng chứa, tăng áp lực bộ nhớ hoặc dẫn đến `OutOfMemoryError`.
- **Tính toán sai/tràn số:** số âm có thể gây `NegativeArraySizeException`; cộng/nhân bằng `int` không kiểm soát có thể tràn. Dùng `Math.addExact`/`multiplyExact` khi tính từ nhiều phần và đặt giới hạn nghiệp vụ phù hợp.
- **Lấy `String.length()` của nguồn trước escaping:** dữ liệu sau escaping có thể dài hơn.
- **Dùng capacity làm số byte network:** độ dài payload UTF-8 phải tính từ `byte[]` thực sự gửi.
- **Gọi `toString()` liên tục trong vòng lặp:** tạo `String` trung gian không cần thiết; thường nên append xong rồi chuyển sang `String` một lần.
- **Chia sẻ builder giữa các luồng:** `StringBuilder` không đồng bộ hóa và không bảo đảm an toàn khi nhiều thread sửa đồng thời; dùng sở hữu riêng theo tác vụ hoặc giải pháp đồng bộ phù hợp.

### Kiểm tra hiệu năng như thế nào?

Đo `builder.length()` và `builder.capacity()` sau khi xây dựng giúp kiểm chứng ước lượng có thiếu/thừa nhiều hay không. Nhưng capacity **không tự chứng minh chương trình chạy nhanh hơn**. Khi cần so sánh chiến lược, benchmark bằng JMH với dữ liệu đại diện, có warmup, nhiều lần chạy và tránh để JVM tối ưu bỏ kết quả. Theo dõi tổng thời gian, allocation rate và GC bằng profiler khi thích hợp; nếu phải duyệt dữ liệu một lần nữa để tính capacity, hãy tính cả chi phí duyệt ấy.

Một cách thực dụng là bắt đầu bằng `new StringBuilder()`, chỉ định capacity khi bài toán đã có dự báo hợp lý; điều chỉnh sau khi có đo đạc thay vì dùng công thức nhân cố định cho mọi chuỗi.

## 9. Bài tập tự kiểm tra

**Bài 1.** Cần ghép ba chuỗi `"abc"`, `"Java"`, `"17"`, giữa chúng có chuỗi phân cách `" | "` (3 đơn vị UTF-16). Capacity tối thiểu để không tăng trong quá trình nối là bao nhiêu?

**Bài 2.** Cần tạo 100 dòng, mỗi dòng có đúng 30 đơn vị UTF-16 và kết thúc bằng `"\r\n"`. Capacity tối thiểu là bao nhiêu? Nếu đổi newline thành `"\n"` thì kết quả ra sao?

**Bài 3.** Vì sao `new StringBuilder(100)` khác hoàn toàn với `new StringBuilder().setLength(100)`? Cả hai có `length()` ban đầu bằng 0 không?

**Bài 4.** Với `String text = "A\uD83D\uDE00";`, kết quả của `text.length()` và `text.getBytes(StandardCharsets.UTF_8).length` bằng bao nhiêu? Nên truyền số nào vào constructor khi chỉ append `text` một lần?

**Bài 5.** Ứng dụng luôn nối 10 từ ngắn. Việc tính toán chính xác length trước khi nối có chắc tăng hiệu năng không? Bạn cần đo gì để kết luận?

**Gợi ý đáp án:** (1) 3 + 4 + 2 + 2×3 = **15**; (2) 100×(30+2) = **3200**, dùng LF là **3100**; (3) constructor số nguyên đặt capacity 100, length 0, còn `setLength(100)` thêm đủ nội dung NUL để length 100; (4) length 3, UTF-8 byte 5, capacity **3**; (5) không chắc: phải đo chi phí tính capacity, số lần tăng/cấp phát, thời gian và GC trong workload thực tế.

### Tài liệu tham khảo

- [`StringBuilder` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/StringBuilder.html)
- [`AbstractStringBuilder` — OpenJDK source](https://github.com/openjdk/jdk/blob/master/src/java.base/share/classes/java/lang/AbstractStringBuilder.java) (quy tắc mở rộng ở mức triển khai, có thể thay đổi theo phiên bản).
- [`Character.charCount` — Java SE 17](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Character.html#charCount(int)).
