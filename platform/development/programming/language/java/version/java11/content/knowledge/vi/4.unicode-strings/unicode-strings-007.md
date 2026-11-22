# Java 11+ — `String.repeat(int count)` với số lần bằng 0, âm và rất lớn

## 1. `repeat` lặp cái gì?

Từ **Java 11**, lớp `java.lang.String` có phương thức:

```java
public String repeat(int count)
```

Phương thức trả về chuỗi được tạo bằng cách **nối nguyên chuỗi ban đầu `count` lần liên tiếp**. Nó không thêm khoảng trắng, dấu phân cách hay ký tự xuống dòng; cũng không sửa đối tượng `String` ban đầu vì `String` là immutable.

```java
"ab".repeat(3)     // "ababab"
"-".repeat(5)      // "-----"
"Hi\n".repeat(2)   // "Hi\nHi\n": dấu xuống dòng vốn có trong chuỗi nguồn
```

`count` là số lần lặp **cả chuỗi**, không phải số ký tự muốn nhận được; kiểu của `count` là `int`. Các quy tắc về 0, số âm và số rất lớn vẫn được áp dụng trong Java hiện đại.

## 2. `count == 0`: trả về chuỗi rỗng

Với **bất kỳ chuỗi nguồn không null nào**, kể cả chuỗi có nhiều ký tự hoặc chứa Unicode, `repeat(0)` trả về `""`:

```java
"Java".repeat(0)       // ""
"🌍".repeat(0)          // ""
"".repeat(0)           // ""
"abc".repeat(0).length() // 0
```

Điều này không phải lỗi: nối 0 bản sao thì không có phần tử nào trong kết quả. `repeat(0)` **không** trả về chuỗi nguồn, một dấu cách hoặc chuỗi văn bản `"null"`.

Phân biệt ba trường hợp dễ nhầm:

- `"abc".repeat(0)` → `""` vì số lần bằng 0.
- `"".repeat(1_000_000)` → `""` vì chuỗi nguồn rỗng dù số lần dương rất lớn.
- `((String) null).repeat(0)` → **`NullPointerException`** vì không có đối tượng để gọi phương thức; không hề vào được `repeat`.

`repeat(0)` hữu ích khi tạo chuỗi thụt dòng/ký tự phân cách với số lượng tính toán được, nhưng hãy cân nhắc xem giá trị 0 có hợp lệ trong nghiệp vụ không. Nếu yêu cầu phải có ít nhất một bản sao, kiểm tra `count >= 1` **trước khi** gọi phương thức.

## 3. `count < 0`: luôn ném `IllegalArgumentException`

`String.repeat` không hiểu số âm là “lặp 0 lần”, “lặp ngược” hay “bỏ ký tự”. Số lần âm không có nghĩa và sẽ gây lỗi:

```java
"ab".repeat(-1);          // IllegalArgumentException
"ab".repeat(-100);        // IllegalArgumentException
"".repeat(-1);            // IllegalArgumentException, dù chuỗi nguồn rỗng
```

**Điểm cần nhớ:** khi `count < 0`, lỗi xảy ra **kể cả chuỗi nguồn rỗng**. Kiểm tra giá trị âm được thực hiện trước quy tắc trả `""` cho chuỗi rỗng.

Đây là unchecked exception (`IllegalArgumentException` thuộc `RuntimeException`): có thể để lỗi truyền lên nơi xử lý input, hoặc chủ động chặn dữ liệu không hợp lệ. Ví dụ khi ứng dụng muốn coi số âm là lỗi nhập liệu:

```java
if (count < 0) {
    throw new IllegalArgumentException("count must be >= 0");
}
String result = text.repeat(count);
```

Không tự động chuyển số âm về 0, trừ khi đặc tả nghiệp vụ yêu cầu rõ ràng: việc âm thầm thay đổi input có thể che giấu lỗi tính toán ở phía trước. Đừng phụ thuộc vào **nội dung thông báo lỗi** của JDK; kiểu `IllegalArgumentException` mới là hợp đồng API đáng tin cậy.

## 4. `count` rất lớn: giới hạn độ dài, bộ nhớ và tràn số

Khi `count` dương và `text` không rỗng, về mặt toán học:

```text
số đơn vị UTF-16 của kết quả = text.length() × count
```

Kết quả phải được biểu diễn bằng một `String` duy nhất. Điều đó có các hệ quả:

1. **Độ dài vượt giới hạn biểu diễn:** `String.length()` trả `int`. Nếu số đơn vị UTF-16 cần có vượt quá `Integer.MAX_VALUE`, yêu cầu chắc chắn không thể biểu diễn thành một `String` hợp lệ. OpenJDK có thể báo `OutOfMemoryError` khi phát hiện giới hạn triển khai bị vượt.
2. **Độ dài chưa vượt `int` vẫn có thể hết bộ nhớ:** tạo chuỗi đầu ra lớn cần vùng nhớ lớn và JVM có thể ném `OutOfMemoryError` vì heap/giới hạn mảng hoặc điều kiện bộ nhớ thực tế.
3. **Chi phí tăng theo kích thước kết quả:** chuỗi có độ dài N phải chiếm bộ nhớ tỉ lệ với N, đồng thời cần xử lý dữ liệu để tạo kết quả; `repeat` không tạo một “chuỗi lặp ảo” được tính dần lúc đọc.
4. **Không có một ngưỡng số lần an toàn cho mọi chuỗi:** `"x".repeat(n)` và `"một chuỗi dài".repeat(n)` có kích thước đầu ra khác nhau. Số lần chỉ hợp lệ về kiểu `int` chưa đủ để đảm bảo khả thi.

Ví dụ **chỉ để phân tích kích thước, không gọi `repeat` để cấp phát**:

```java
int count = Integer.MAX_VALUE; // 2_147_483_647
String text = "ab";

long required = (long) text.length() * count;
// required == 4_294_967_294 (> Integer.MAX_VALUE)
```

Vì `"ab"` có 2 đơn vị UTF-16, kết quả giả định quá dài cho `String.length()`. Gọi trực tiếp `"ab".repeat(Integer.MAX_VALUE)` có thể dẫn đến `OutOfMemoryError` trong OpenJDK. Đặc biệt, đừng thử `"x".repeat(Integer.MAX_VALUE)` chỉ để “xem có chạy không”: độ dài logic là trong miền `int` nhưng quá trình cấp phát có thể tiêu tốn bộ nhớ rất lớn.

**Bẫy tràn số `int`:** không viết phép kiểm tra giới hạn như `text.length() * count > limit` nếu cả hai toán hạng là `int`. Phép nhân có thể tràn **trước khi** so sánh. Ví dụ `2 * Integer.MAX_VALUE` khi tính bằng `int` cho giá trị `-2`, khiến việc kiểm tra bị sai. Ép một toán hạng sang `long` **trước khi nhân**:

```java
long required = (long) text.length() * count;
if (required > maxAllowedUtf16Units) {
    throw new IllegalArgumentException("output too large");
}
```

Dùng `long` ở đây phù hợp vì tích của hai số `int` không âm vẫn nằm trong miền `long`. Giới hạn `maxAllowedUtf16Units` cần do ứng dụng đặt dựa trên dữ liệu và tài nguyên thực tế; vượt kiểm tra này là **điều kiện đủ để từ chối**, còn vượt qua nó **không phải** lời hứa sẽ cấp phát thành công. Đừng dùng `catch (OutOfMemoryError)` như cơ chế giới hạn dữ liệu thông thường.

### Ngoại lệ quan trọng với chuỗi nguồn rỗng

`"".repeat(Integer.MAX_VALUE)` vẫn trả `""` và không cần tạo chuỗi dài, vì không có dữ liệu để lặp. Nhưng `"".repeat(-1)` vẫn ném `IllegalArgumentException`. Khi xét kích thước, phải kiểm tra **đồng thời** giá trị `count` và độ dài chuỗi nguồn.

## 5. Với Unicode, `length()` không đếm code point

`String.repeat` ghép **toàn bộ nội dung chuỗi nguồn** theo đúng thứ tự. Nó không chuyển đổi Unicode, không chuẩn hóa chuỗi và không tự tách một ký tự hiển thị thành các lần lặp độc lập.

Java `String.length()` đếm các **đơn vị mã UTF-16**; một Unicode code point nằm ngoài Basic Multilingual Plane thường chiếm **hai** đơn vị UTF-16 (một cặp surrogate). Ví dụ ký tự 🌍 có độ dài Java bằng 2 dù hiển thị thành một biểu tượng:

```java
String globe = "\uD83C\uDF0D"; // 🌍
String triple = globe.repeat(3);

triple.length();                         // 6 đơn vị UTF-16
triple.codePointCount(0, triple.length()); // 3 code point
```

Vậy nếu chuỗi nguồn có `k` đơn vị UTF-16 và lặp `n` lần, chuỗi thành công sẽ có `k × n` đơn vị UTF-16. Không suy kích thước bộ nhớ từ số ký tự **nhìn thấy** trên màn hình: emoji, dấu kết hợp (combining marks) và các cụm grapheme có thể khiến số ký tự hiển thị, số code point và `length()` khác nhau. Lặp chuỗi không thực hiện Unicode normalization.

Khi đặt giới hạn cho `repeat`, kiểm tra `text.length()` là cách đơn giản để dự đoán độ dài **theo API `String`**. Nếu ứng dụng cần giới hạn số **byte của tệp/HTTP response**, phải xét encoding đầu ra (ví dụ UTF-8) và kích thước dữ liệu thực tế; phép nhân UTF-16 không thay thế cho hạn mức byte.

## 6. Ví dụ Java 11+ chạy được và kết quả kiểm chứng

Lưu thành tệp **`RepeatEdgeCases.java`**:

```java
import java.util.Objects;

public final class RepeatEdgeCases {
    static String repeatBounded(String text, int count, long maxUtf16Units) {
        Objects.requireNonNull(text, "text");

        if (count < 0) {
            throw new IllegalArgumentException("negative count");
        }
        if (maxUtf16Units < 0) {
            throw new IllegalArgumentException("negative limit");
        }

        long needed = (long) text.length() * count;
        if (needed > maxUtf16Units) {
            throw new IllegalArgumentException("too large");
        }
        return text.repeat(count);
    }

    public static void main(String[] args) {
        String pattern = "ab";

        System.out.println("zero=<" + pattern.repeat(0) + ">");
        System.out.println("one=<" + pattern.repeat(1) + ">");
        System.out.println("three=<" + pattern.repeat(3) + ">");

        try {
            pattern.repeat(-2);
        } catch (IllegalArgumentException e) {
            System.out.println("negative=IllegalArgumentException");
        }

        try {
            "".repeat(-1);
        } catch (IllegalArgumentException e) {
            System.out.println("empty-negative=IllegalArgumentException");
        }

        System.out.println("empty-huge=<" + "".repeat(Integer.MAX_VALUE) + ">");

        String globe = "\uD83C\uDF0D";
        String globes = globe.repeat(3);
        System.out.println("unicode-units=" + globes.length());
        System.out.println(
                "unicode-codepoints=" +
                globes.codePointCount(0, globes.length()));

        long hypothetical = (long) pattern.length() * Integer.MAX_VALUE;
        System.out.println("large-units=" + hypothetical);

        try {
            repeatBounded(pattern, Integer.MAX_VALUE, 1000);
        } catch (IllegalArgumentException e) {
            System.out.println("large=rejected-by-limit");
        }

        System.out.println("bounded=<" + repeatBounded(pattern, 3, 1000) + ">");
    }
}
```

Biên dịch và chạy với JDK 11 trở lên. Cờ `--release 11` kiểm tra cả cú pháp và API tương thích Java 11:

```bash
javac --release 11 RepeatEdgeCases.java
java RepeatEdgeCases
```

Kết quả stdout chính xác:

```text
zero=<>
one=<ab>
three=<ababab>
negative=IllegalArgumentException
empty-negative=IllegalArgumentException
empty-huge=<>
unicode-units=6
unicode-codepoints=3
large-units=4294967294
large=rejected-by-limit
bounded=<ababab>
```

Giải thích các điểm quan trọng:

- `zero=<>` minh họa chuỗi rỗng bằng cặp dấu `< >`, tránh nhìn nhầm một dòng trống.
- Hai dòng `negative` bắt chính xác loại ngoại lệ, kể cả khi chuỗi nguồn là `""`.
- `empty-huge=<>` là trường hợp số lần rất lớn nhưng kết quả vẫn rỗng.
- `unicode-units=6` và `unicode-codepoints=3` chứng minh khác biệt giữa UTF-16 và code point.
- `large-units=4294967294` chỉ tính trước kích thước bằng `long`; ví dụ **không** cấp phát chuỗi khổng lồ.
- `repeatBounded` từ chối đầu ra vượt hạn mức 1.000 đơn vị UTF-16 trước khi gọi `repeat`. Hạn mức này chỉ là giá trị minh họa; ứng dụng phải chọn hạn mức phù hợp.

## 7. Nếu thật sự cần xuất dữ liệu rất lớn

Nếu mục tiêu là **ghi hàng triệu bản sao ra tệp hoặc luồng I/O**, không nhất thiết phải tạo một `String` khổng lồ. Có thể ghi từng phần vào một `Writer` truyền dữ liệu ra ngoài (ví dụ `BufferedWriter` bọc `FileWriter`):

```java
// Đoạn minh họa dùng trong lớp có import java.io.IOException và java.io.Writer.
static void repeatToWriter(Writer writer, String piece, int count)
        throws IOException {
    if (count < 0) {
        throw new IllegalArgumentException("negative count");
    }
    for (int i = 0; i < count; i++) {
        writer.write(piece);
    }
}
```

Cách này không cần materialize toàn bộ kết quả trong một `String` nếu `writer` thực sự truyền/buffer từng phần ra ngoài; **không** dùng `StringWriter` nếu mục tiêu là tránh giữ dữ liệu trong RAM. Vẫn phải đặt hạn mức hợp lý về thời gian, số lần lặp và tổng dữ liệu xuất ra, vì việc stream không làm biến mất chi phí I/O. Nếu yêu cầu phải trả về một `String` duy nhất, hãy giới hạn độ dài trước khi gọi `repeat` như mục 6.

## 8. Các lỗi suy luận thường gặp

| Nhận định sai | Cách hiểu đúng |
| --- | --- |
| “`repeat(0)` giữ nguyên chuỗi.” | `repeat(0)` luôn tạo **giá trị** rỗng `""`. |
| “Chuỗi nguồn rỗng thì `repeat(-1)` cũng rỗng.” | Số âm luôn gây `IllegalArgumentException`. |
| “Số lần là `int` nên chắc chắn tạo được kết quả.” | `int` chỉ giới hạn input, không đảm bảo dung lượng cho output. |
| “Chỉ cần kiểm tra `text.length() * count` bằng `int`.” | Có thể tràn số; nhân sau khi ép sang `long`. |
| “`Integer.MAX_VALUE` là số ký tự có thể cấp phát được.” | Đây là giới hạn kiểu trả về `length()`; bộ nhớ/giới hạn nội bộ có thể nhỏ hơn rất nhiều. |
| “`String.repeat` tự cắt bớt khi thiếu RAM.” | Không cắt bớt; thao tác có thể thất bại bằng `OutOfMemoryError`. |
| “`length()` chính là số emoji/code point.” | `length()` đếm đơn vị UTF-16, có thể khác code point và grapheme. |
| “Bắt `OutOfMemoryError` là đủ để xử lý input quá lớn.” | Kiểm tra giới hạn **trước cấp phát**; `OutOfMemoryError` có thể đe dọa ổn định tiến trình. |
| “`repeat` tự thêm dấu ngắt giữa các bản sao.” | Phương thức nối nguyên văn, không chèn separator. |

## 9. Checklist áp dụng thực tế

1. Xác định `count` có được phép bằng 0 không. Nếu có, hãy chấp nhận `""` như kết quả hợp lệ.
2. Từ chối `count < 0` theo hợp đồng của API, kể cả khi nguồn rỗng.
3. Nếu `text` có thể là `null`, xử lý `null` tường minh trước lời gọi; `repeat(0)` không cứu được tham chiếu `null`.
4. Với chuỗi lớn, tính `(long) text.length() * count` và kiểm tra cả giới hạn nghiệp vụ lẫn tài nguyên khả dụng.
5. Phân biệt đơn vị UTF-16, code point, ký tự hiển thị và byte đầu ra khi xử lý Unicode.
6. Nếu kết quả rất lớn chỉ để ghi ra ngoài, cân nhắc ghi theo luồng thay vì tạo một `String` duy nhất.

### Tài liệu chính thức

- [Oracle Java 11 API — `String.repeat(int)`](https://docs.oracle.com/en/java/javase/11/docs/api/java.base/java/lang/String.html#repeat(int))
- [Oracle Java 25 API — `String.repeat(int)` và `String.length()`](https://docs.oracle.com/en/java/javase/25/docs/api/java.base/java/lang/String.html#repeat(int))
- [OpenJDK 17 — mã nguồn triển khai `String.repeat(int)`](https://github.com/openjdk/jdk17/blob/master/src/java.base/share/classes/java/lang/String.java)
