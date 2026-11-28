# Charset.forName(), tên chuẩn, bí danh và lỗi UnsupportedCharsetException

> **Chương:** UTF-8 mặc định  
> **Module:** `JAVA_VERSION_JAVA18`  
> **Mục tiêu:** Tra cứu charset theo tên động, hiểu tên chuẩn và alias, kiểm tra charset có được runtime hỗ trợ hay không, xử lý đúng `IllegalCharsetNameException`, `UnsupportedCharsetException` và `NullPointerException`. Biết khi nào nên dùng `StandardCharsets` và khi nào nên dùng `Charset.forName()` trên JDK hiện đại.

## 1. Vì sao cần tra cứu charset theo tên?

Trong Java, nhiều API nhận một đối tượng `Charset` để chuyển đổi byte và ký tự. Có hai tình huống phổ biến:

- Ứng dụng biết trước encoding của định dạng dữ liệu, ví dụ UTF-8 trong một giao thức hoặc file format.
- Ứng dụng nhận tên charset từ cấu hình, tham số dòng lệnh hoặc metadata bên ngoài và cần tra cứu lúc chạy.

Tình huống thứ nhất nên dùng hằng số chuẩn như `StandardCharsets.UTF_8`. Tình huống thứ hai có thể dùng `Charset.forName(name)` vì tên chỉ được biết khi chương trình chạy.

Không nên xem `Charset.forName()` là cách viết dài hơn của `StandardCharsets.UTF_8`. Hai cách giải quyết hai yêu cầu khác nhau:

- Hằng số trong `StandardCharsets` biểu diễn những charset Java bắt buộc phải hỗ trợ.
- `Charset.forName()` tra cứu theo tên hoặc alias và có thể thất bại nếu tên sai hoặc runtime không có charset đó.

JEP 400 làm UTF-8 trở thành default charset của Java từ JDK 18 theo cấu hình mặc định. Điều này không thay đổi quy tắc tra cứu tên charset: `Charset.forName("UTF-8")` vẫn là thao tác yêu cầu một charset theo tên; `Charset.defaultCharset()` mới là API hỏi default charset của JVM.

## 2. Charset, canonical name và alias

### 2.1. Charset là gì?

`Charset` đại diện cho một ánh xạ giữa chuỗi ký tự Unicode và chuỗi byte. Nó định nghĩa cách:

- Encode ký tự thành byte.
- Decode byte thành ký tự.
- Xử lý dữ liệu không thể biểu diễn hoặc chuỗi byte không hợp lệ thông qua encoder/decoder và các chính sách lỗi tương ứng.

Một charset có tên chuẩn và có thể có nhiều tên bí danh. Ví dụ, một runtime có thể nhận nhiều cách viết cho cùng một encoding. Những cách viết đó không phải các encoding khác nhau chỉ vì chuỗi tên khác nhau.

Các đối tượng `Charset` là immutable và thread-safe. Các encoder/decoder được tạo từ charset có trạng thái riêng; không suy ra rằng một `CharsetEncoder` hoặc `CharsetDecoder` đang được dùng đồng thời cũng thread-safe.

### 2.2. Tên chuẩn — canonical name

`Charset.name()` trả về tên chuẩn của charset. Tên chuẩn là tên dùng để định danh charset trong API Java và được chuẩn hóa theo quy ước của charset tương ứng.

Ví dụ:

~~~java
import java.nio.charset.Charset;

public class CanonicalNameExample {
    public static void main(String[] args) {
        Charset charset = Charset.forName("utf-8");
        System.out.println(charset.name());
    }
}
~~~

Kết quả:

~~~text
UTF-8
~~~

Tên đầu vào có thể viết thường, nhưng `name()` trả về tên chuẩn mà đối tượng charset công bố.

Dùng `name()` khi cần ghi lại charset thực sự đã được chọn vào log hoặc metadata. Không dùng nguyên chuỗi người dùng nhập làm bằng chứng rằng runtime đã chọn đúng charset.

### 2.3. Alias — tên bí danh

`Charset.aliases()` trả về tập alias của charset. Alias là những tên khác mà runtime chấp nhận để tra cứu cùng charset.

Ví dụ:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class CharsetAliases {
    public static void main(String[] args) {
        Charset charset = StandardCharsets.UTF_8;

        System.out.println("canonical=" + charset.name());
        for (String alias : charset.aliases()) {
            System.out.println("alias=" + alias);
        }
    }
}
~~~

Đầu ra có dạng:

~~~text
canonical=UTF-8
alias=...
alias=...
~~~

Tập alias cụ thể phụ thuộc charset provider và JDK. Không copy một danh sách alias quan sát được trên một máy thành danh sách bắt buộc cho mọi vendor.

`aliases()` trả về tập không thể sửa đổi. Có thể duyệt, kiểm tra hoặc ghi log; không thể thêm alias vào tập này để thay đổi cách tra cứu của JVM.

### 2.4. Tên không phân biệt chữ hoa/chữ thường

Tên charset không phân biệt chữ hoa/chữ thường khi tra cứu. Ví dụ các cách viết sau đều được nhận diện là UTF-8 trên JDK chuẩn:

~~~java
import java.nio.charset.Charset;

public class CharsetNameCase {
    public static void main(String[] args) {
        System.out.println(Charset.forName("UTF-8").name());
        System.out.println(Charset.forName("utf-8").name());
        System.out.println(Charset.forName("UtF-8").name());
    }
}
~~~

Kết quả:

~~~text
UTF-8
UTF-8
UTF-8
~~~

Không cần tự chuyển tên sang chữ hoa để gọi API. Nếu muốn chuẩn hóa chuỗi cấu hình cho mục đích hiển thị, vẫn nên lấy tên đã chọn từ `Charset.name()`.

### 2.5. Tên chuẩn không phải lúc nào cũng giống chuỗi người dùng nhập

Khi nhận cấu hình `utf-8` hoặc một alias khác do runtime công bố, hãy lưu lại cả hai nếu cần chẩn đoán:

- Giá trị cấu hình ban đầu.
- Canonical name từ `charset.name()`.

Ví dụ log:

~~~text
configuredCharset=utf-8
resolvedCharset=UTF-8
~~~

Điều này giúp phân biệt giá trị cấu hình với charset mà runtime thực sự đã resolve.

## 3. Dùng Charset.forName()

### 3.1. Cú pháp và hành vi

Cú pháp:

~~~java
Charset charset = Charset.forName("UTF-8");
~~~

`Charset.forName(String charsetName)` tìm charset theo tên hoặc alias. Nếu runtime hỗ trợ tên đó, phương thức trả về một đối tượng `Charset`.

Tên được tra cứu không phân biệt chữ hoa/chữ thường. Nếu không tìm thấy charset được hỗ trợ, phương thức ném `UnsupportedCharsetException`. Nếu tên không hợp lệ theo quy tắc đặt tên charset, phương thức ném `IllegalCharsetNameException`. Nếu truyền `null`, phương thức ném `NullPointerException`.

Các trường hợp cần phân biệt:

| Đầu vào | Kết quả |
|---|---|
| Tên chuẩn được hỗ trợ, ví dụ `UTF-8` | Trả về charset |
| Alias được runtime hỗ trợ | Trả về charset theo tên chuẩn |
| Tên hợp lệ nhưng runtime không hỗ trợ | `UnsupportedCharsetException` |
| Chuỗi không phải tên charset hợp lệ | `IllegalCharsetNameException` |
| `null` | `NullPointerException` |

Không có cơ chế fallback tự động sang UTF-8 khi `forName()` thất bại. Nếu ứng dụng muốn fallback, ứng dụng phải định nghĩa chính sách đó một cách tường minh.

### 3.2. Ví dụ tra cứu tên chuẩn

~~~java
import java.nio.charset.Charset;

public class CharsetForName {
    public static void main(String[] args) {
        Charset charset = Charset.forName("UTF-8");

        System.out.println(charset.name());
        System.out.println(charset.displayName());
    }
}
~~~

`name()` là tên chuẩn dùng để định danh. `displayName()` là tên hiển thị, có thể phụ thuộc locale và không nên dùng làm khóa cấu hình hoặc định danh giao thức.

### 3.3. Ví dụ tra cứu alias

~~~java
import java.nio.charset.Charset;

public class ResolveAlias {
    public static void main(String[] args) {
        Charset charset = Charset.forName("utf-8");

        for (String alias : charset.aliases()) {
            Charset resolved = Charset.forName(alias);
            if (!resolved.name().equals(charset.name())) {
                throw new AssertionError("Alias resolved to another charset");
            }
        }

        System.out.println("All reported aliases resolve to "
                + charset.name());
    }
}
~~~

Ví dụ dùng chính alias mà đối tượng charset công bố. Nó không giả định một alias cụ thể phải tồn tại trên mọi runtime.

### 3.4. Không so sánh object identity

Khi so sánh hai charset, hãy dùng `equals()` hoặc canonical name:

~~~java
Charset first = Charset.forName("UTF-8");
Charset second = Charset.forName("utf-8");

System.out.println(first.equals(second));
System.out.println(first.name().equals(second.name()));
~~~

Kết quả:

~~~text
true
true
~~~

Không dùng `first == second` làm hợp đồng. Ứng dụng cần so sánh charset theo định danh, không dựa vào việc runtime có trả về cùng một object instance hay không.

## 4. Tên charset hợp lệ và IllegalCharsetNameException

### 4.1. Phân biệt tên sai cú pháp với charset không được hỗ trợ

Hai lỗi sau có ý nghĩa khác nhau:

- `IllegalCharsetNameException`: chuỗi không phải tên charset hợp lệ.
- `UnsupportedCharsetException`: tên hợp lệ nhưng không có charset tương ứng được hỗ trợ trong runtime.

Tên charset hợp lệ dùng các chữ cái ASCII, chữ số và một số dấu phân cách được API cho phép như `-`, `+`, `:`, `_` và `.`; ký tự đầu tiên phải là chữ cái hoặc chữ số. Ví dụ `UTF 8` không hợp lệ vì chứa khoảng trắng, trong khi `X-EXAMPLE-CHARSET` có hình thức tên hợp lệ dù runtime có thể không hỗ trợ.

Ví dụ chuỗi chứa khoảng trắng:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.IllegalCharsetNameException;

public class InvalidCharsetName {
    public static void main(String[] args) {
        try {
            Charset.forName("UTF 8");
        } catch (IllegalCharsetNameException exception) {
            System.out.println(exception.getClass().getSimpleName());
            System.out.println(exception.getCharsetName());
        }
    }
}
~~~

Kết quả:

~~~text
IllegalCharsetNameException
UTF 8
~~~

Tên charset tuân theo quy tắc cú pháp do API quy định. Không tự sửa mọi ký tự lạ hoặc xóa dấu cách rồi tiếp tục mà không có quy tắc cấu hình rõ ràng.

### 4.2. UnsupportedCharsetException là lỗi khác

Một tên có cú pháp hợp lệ nhưng không có provider hỗ trợ sẽ dẫn đến `UnsupportedCharsetException`.

Ví dụ sau chỉ tạo ra kết quả này khi runtime không có provider đăng ký tên đó:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.UnsupportedCharsetException;

public class UnsupportedCharsetName {
    public static void main(String[] args) {
        try {
            Charset.forName("X-EXAMPLE-CHARSET-NOT-INSTALLED");
        } catch (UnsupportedCharsetException exception) {
            System.out.println(exception.getClass().getSimpleName());
            System.out.println(exception.getCharsetName());
        }
    }
}
~~~

Kết quả mong đợi trong runtime không có provider cho tên thử nghiệm:

~~~text
UnsupportedCharsetException
X-EXAMPLE-CHARSET-NOT-INSTALLED
~~~

Đây là tên hợp lệ về mặt cú pháp nhưng không phải charset chuẩn bắt buộc. Một môi trường có provider tùy biến hoàn toàn có thể hỗ trợ tên đó; vì vậy không dùng nó làm test portable nếu không kiểm soát provider.

### 4.3. NullPointerException

`Charset.forName(null)` không có ý nghĩa tra cứu và ném `NullPointerException`.

Nếu tên đến từ cấu hình hoặc API bên ngoài, kiểm tra null trước để trả lỗi cấu hình có ngữ nghĩa rõ ràng cho ứng dụng:

~~~java
static Charset resolveCharset(String configuredName) {
    if (configuredName == null) {
        throw new IllegalArgumentException("Charset name is required");
    }
    return Charset.forName(configuredName);
}
~~~

Đây là chính sách của ứng dụng. Nó chuyển lỗi null thành `IllegalArgumentException` có thông điệp do ứng dụng định nghĩa; không thay đổi hợp đồng gốc của `Charset.forName()`.

## 5. Dùng Charset.isSupported() khi chỉ cần kiểm tra khả năng hỗ trợ

`Charset.isSupported(String charsetName)` kiểm tra tên có được hỗ trợ bởi runtime hay không.

Ví dụ:

~~~java
import java.nio.charset.Charset;

public class CharsetSupportCheck {
    public static void main(String[] args) {
        System.out.println(Charset.isSupported("UTF-8"));
        System.out.println(Charset.isSupported("X-UNKNOWN-CHARSET"));
    }
}
~~~

Trong runtime không có provider cho tên thử nghiệm, kết quả:

~~~text
true
false
~~~

Phân biệt:

- Dùng `isSupported()` khi chỉ cần hỏi runtime có hỗ trợ tên đó không.
- Dùng `forName()` khi cần lấy đối tượng `Charset` để encode/decode.

`isSupported()` trả `false` với tên hợp lệ nhưng không được hỗ trợ. Tên sai cú pháp vẫn có thể ném `IllegalCharsetNameException`; truyền `null` ném `NullPointerException`. Không hiểu `false` là cách xử lý mọi loại input không hợp lệ.

Không cần gọi `isSupported()` rồi `forName()` trong mọi trường hợp. Nếu cuối cùng chắc chắn cần đối tượng charset, gọi `forName()` một lần và xử lý exception thường rõ ràng hơn.

## 6. Các charset chuẩn được Java bảo đảm

Java yêu cầu mọi implementation hỗ trợ các charset chuẩn được khai báo trong `StandardCharsets`:

| Hằng số | Tên chuẩn | Mô tả |
|---|---|---|
| `StandardCharsets.US_ASCII` | `US-ASCII` | ASCII 7-bit |
| `StandardCharsets.ISO_8859_1` | `ISO-8859-1` | Latin-1 |
| `StandardCharsets.UTF_8` | `UTF-8` | Unicode Transformation Format 8-bit |
| `StandardCharsets.UTF_16` | `UTF-16` | Unicode Transformation Format 16-bit |
| `StandardCharsets.UTF_16BE` | `UTF-16BE` | UTF-16 big-endian |
| `StandardCharsets.UTF_16LE` | `UTF-16LE` | UTF-16 little-endian |

Ví dụ:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class StandardCharsetsExample {
    public static void main(String[] args) {
        Charset utf8 = StandardCharsets.UTF_8;
        Charset byName = Charset.forName("UTF-8");

        System.out.println(utf8.name());
        System.out.println(utf8.equals(byName));
    }
}
~~~

Kết quả:

~~~text
UTF-8
true
~~~

Nếu encoding đã biết và thuộc danh sách chuẩn, ưu tiên hằng số `StandardCharsets`. Cách này:

- Không phải tra cứu chuỗi cấu hình.
- Không thể gặp `UnsupportedCharsetException` với charset chuẩn bắt buộc.
- Thể hiện rõ định dạng dữ liệu mà code mong đợi.
- Tránh lỗi chính tả trong tên charset.

Không đồng nhất việc Java bắt buộc hỗ trợ UTF-8 với việc default charset luôn luôn được chọn bằng UTF-8 ở mọi chế độ. JEP 400 quy định default charset trên JDK 18+ theo cấu hình mặc định; `StandardCharsets.UTF_8` là hằng số charset explicit.

## 7. Charset.forName() và Charset.defaultCharset() giải quyết hai việc khác nhau

| API | Câu hỏi được trả lời | Dùng khi |
|---|---|---|
| `Charset.forName(name)` | Runtime có charset được chỉ định bằng tên này không? | Tên đến từ config hoặc metadata |
| `Charset.isSupported(name)` | Runtime có hỗ trợ tên này không? | Kiểm tra capability |
| `Charset.defaultCharset()` | Charset mặc định của JVM hiện tại là gì? | Chẩn đoán hoặc API phụ thuộc default charset |
| `StandardCharsets.UTF_8` | Đối tượng UTF-8 chuẩn là gì? | Dữ liệu/giao thức quy định UTF-8 |

Ví dụ:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class CharsetChoice {
    public static void main(String[] args) {
        Charset configured = Charset.forName("UTF-8");
        Charset defaultCharset = Charset.defaultCharset();

        System.out.println("configured=" + configured.name());
        System.out.println("default=" + defaultCharset.name());
        System.out.println("same=" + configured.equals(defaultCharset));
        System.out.println("constant=" + StandardCharsets.UTF_8.name());
    }
}
~~~

Trên JDK 18+ với cấu hình mặc định, kết quả thường là:

~~~text
configured=UTF-8
default=UTF-8
same=true
constant=UTF-8
~~~

Nếu runtime dùng chế độ tương thích hoặc cấu hình startup khác, default charset có thể khác. `forName("UTF-8")` vẫn tra cứu UTF-8; nó không hỏi default charset.

## 8. Liệt kê charset runtime hỗ trợ

`Charset.availableCharsets()` trả về map các canonical name và đối tượng charset mà runtime hiện tại hỗ trợ.

Ví dụ:

~~~java
import java.nio.charset.Charset;

public class AvailableCharsets {
    public static void main(String[] args) {
        Charset.availableCharsets().forEach((name, charset) ->
                System.out.println(name + " -> " + charset.displayName()));
    }
}
~~~

Map được trả về là không thể sửa đổi và các khóa được sắp xếp theo thứ tự không phân biệt chữ hoa/chữ thường. Nó hữu ích cho công cụ chẩn đoán hoặc trang cấu hình cần hiển thị các charset khả dụng.

Không nên:

- Hard-code toàn bộ kết quả `availableCharsets()` làm expected output cho mọi vendor.
- Giả định mọi runtime có cùng charset ngoài nhóm bắt buộc.
- Dùng `displayName()` làm khóa định danh vì tên hiển thị có thể phụ thuộc locale.
- Giả định mọi charset trong danh sách đều phù hợp với một giao thức cụ thể.

Danh sách có thể phản ánh các charset được cung cấp qua provider trong runtime. Khi dùng charset bổ sung, cần ghi module/JAR/provider và cách runtime phát hiện provider đó.

## 9. Charset provider và charset ngoài nhóm chuẩn

Java có SPI `java.nio.charset.spi.CharsetProvider` để runtime có thể phát hiện charset provider bổ sung.

Một provider có thể cung cấp charset ngoài nhóm chuẩn. Điều đó có nghĩa:

- Một tên không được hỗ trợ trong runtime A có thể được hỗ trợ trong runtime B nếu B cài provider.
- `Charset.availableCharsets()` có thể có thêm canonical name.
- `Charset.forName(name)` có thể thành công trên một môi trường nhưng ném `UnsupportedCharsetException` trên môi trường khác.
- Ứng dụng phụ thuộc charset provider phải khai báo và đóng gói provider như một dependency.

Với ứng dụng modular, provider cần được đóng gói và đăng ký theo cơ chế service của JPMS. Ví dụ descriptor module có thể khai báo:

~~~java
module com.example.charset.provider {
    provides java.nio.charset.spi.CharsetProvider
        with com.example.charset.CustomCharsetProvider;
}
~~~

Tên class trên là minh họa; provider thật phải triển khai SPI và cung cấp các charset hợp lệ. Khi triển khai, kiểm tra module/provider có mặt trong runtime image và được service mechanism phát hiện.

Không nhầm charset provider với việc thêm alias vào `Charset.aliases()`. Alias là tên khác của charset do provider công bố; người dùng ứng dụng không thể tự sửa alias set của một charset có sẵn.

## 10. Xử lý tên charset lấy từ cấu hình

Tên charset thường đến từ:

- File cấu hình.
- Biến môi trường.
- HTTP metadata hoặc content type.
- Tham số dòng lệnh.
- Cấu hình database/message broker.
- Metadata của một file được nhập từ bên ngoài.

Đây là input cần validation. Không nên truyền trực tiếp mọi giá trị chưa kiểm tra vào API rồi để lỗi kỹ thuật lan ra ngoài giao diện người dùng.

### 10.1. Hàm resolve có thông báo rõ ràng

~~~java
import java.nio.charset.Charset;
import java.nio.charset.IllegalCharsetNameException;
import java.nio.charset.UnsupportedCharsetException;

public final class CharsetConfig {
    public static Charset resolve(String configuredName) {
        if (configuredName == null || configuredName.isBlank()) {
            throw new IllegalArgumentException(
                    "Configuration 'charset' must not be blank");
        }

        try {
            return Charset.forName(configuredName);
        } catch (IllegalCharsetNameException exception) {
            throw new IllegalArgumentException(
                    "Invalid charset name: " + configuredName, exception);
        } catch (UnsupportedCharsetException exception) {
            throw new IllegalArgumentException(
                    "Charset is not supported: " + configuredName, exception);
        }
    }

    public static void main(String[] args) {
        Charset charset = resolve(args.length == 0 ? "UTF-8" : args[0]);
        System.out.println(charset.name());
    }
}
~~~

Compile:

~~~shell
javac --release 18 -d out CharsetConfig.java
~~~

Chạy:

~~~shell
java -cp out CharsetConfig utf-8
~~~

Kết quả:

~~~text
UTF-8
~~~

Ví dụ giữ nguyên giá trị cấu hình khi gọi `forName()`. Nếu format cấu hình cho phép khoảng trắng ở đầu/cuối, có thể trim trước nhưng phải quy định điều đó ở lớp parse cấu hình; không tự âm thầm thay đổi tên charset ở mọi nơi.

### 10.2. Chọn fallback có chủ đích

Một số ứng dụng có thể muốn fallback về UTF-8 nếu cấu hình thiếu. Chính sách đó nên phân biệt:

- Không có cấu hình: dùng default do ứng dụng định nghĩa, thường là `StandardCharsets.UTF_8`.
- Có cấu hình nhưng tên sai: báo lỗi cấu hình.
- Có cấu hình hợp lệ nhưng runtime không hỗ trợ: báo dependency/provider bị thiếu hoặc yêu cầu cài đặt phù hợp.

Ví dụ:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

static Charset configuredCharset(String name) {
    if (name == null || name.isBlank()) {
        return StandardCharsets.UTF_8;
    }
    return Charset.forName(name);
}
~~~

Ở đây fallback chỉ áp dụng khi giá trị vắng mặt. Nếu tên đã được cung cấp nhưng sai, `forName()` vẫn báo lỗi. Cách này tránh việc typo như `UTF_8` bị âm thầm đổi sang UTF-8 và che khuất cấu hình sai.

Không dùng `Charset.defaultCharset()` làm fallback cho một định dạng file/giao thức đã quy định UTF-8. Default charset là cấu hình JVM; định dạng dữ liệu cần encoding explicit.

## 11. Những exception liên quan và cách xử lý

| Exception | Khi nào xảy ra | Cách xử lý |
|---|---|---|
| `IllegalCharsetNameException` | Tên không hợp lệ theo cú pháp charset | Kiểm tra input/config; không tự sửa âm thầm |
| `UnsupportedCharsetException` | Tên hợp lệ nhưng runtime không hỗ trợ | Cài/đóng gói provider phù hợp hoặc báo cấu hình không được hỗ trợ |
| `NullPointerException` | Tên truyền vào là `null` | Validate null ở biên ứng dụng |
| `IllegalArgumentException` do ứng dụng | Lớp config chuyển lỗi lookup thành lỗi cấu hình | Giữ cause để chẩn đoán |
| `UnsupportedOperationException` | Không phải lỗi tra cứu tên; có thể gặp ở API khác khi thao tác không được hỗ trợ | Xem contract của API thực sự được gọi |

`IllegalCharsetNameException` và `UnsupportedCharsetException` đều là các loại `IllegalArgumentException`, nhưng ý nghĩa khác nhau. Nếu cần đưa thông báo phù hợp cho người dùng, bắt riêng từng loại trước khi chuyển thành exception của tầng cấu hình.

Không bắt `Exception` chung quanh mọi thao tác charset rồi fallback sang UTF-8. Cách đó có thể che lỗi lập trình, lỗi I/O hoặc lỗi dữ liệu.

## 12. Kiểm thử tên chuẩn, alias và lỗi một cách portable

### 12.1. Test charset chuẩn

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class StandardCharsetTest {
    public static void main(String[] args) {
        Charset resolved = Charset.forName("UTF-8");

        if (!resolved.equals(StandardCharsets.UTF_8)) {
            throw new AssertionError("UTF-8 lookup did not resolve to UTF-8");
        }

        if (!"UTF-8".equals(resolved.name())) {
            throw new AssertionError("Unexpected canonical name");
        }
    }
}
~~~

Đây là test portable vì UTF-8 là charset chuẩn bắt buộc.

### 12.2. Test aliases do runtime công bố

~~~java
import java.nio.charset.Charset;
import java.nio.charset.StandardCharsets;

public class CharsetAliasTest {
    public static void main(String[] args) {
        Charset charset = StandardCharsets.UTF_8;

        for (String alias : charset.aliases()) {
            Charset resolved = Charset.forName(alias);
            if (!resolved.name().equals(charset.name())) {
                throw new AssertionError("Alias resolved incorrectly: " + alias);
            }
        }
    }
}
~~~

Test này không giả định alias list giống nhau giữa mọi JDK. Nó kiểm tra invariant: mỗi alias mà đối tượng hiện tại công bố phải resolve về cùng canonical name.

### 12.3. Test tên sai cú pháp

~~~java
import java.nio.charset.Charset;
import java.nio.charset.IllegalCharsetNameException;

public class IllegalCharsetTest {
    public static void main(String[] args) {
        try {
            Charset.forName("UTF 8");
            throw new AssertionError("Expected IllegalCharsetNameException");
        } catch (IllegalCharsetNameException expected) {
            System.out.println("invalid-name");
        }
    }
}
~~~

Đầu ra mong đợi:

~~~text
invalid-name
~~~

### 12.4. Test charset không được hỗ trợ

Test `UnsupportedCharsetException` chỉ portable khi test kiểm soát danh sách provider. Với runtime tiêu chuẩn không cài provider tên thử nghiệm:

~~~java
import java.nio.charset.Charset;
import java.nio.charset.UnsupportedCharsetException;

public class UnsupportedCharsetTest {
    public static void main(String[] args) {
        String name = "X-EXAMPLE-CHARSET-NOT-INSTALLED";

        try {
            Charset.forName(name);
            throw new AssertionError("Test charset unexpectedly supported");
        } catch (UnsupportedCharsetException expected) {
            System.out.println("unsupported-name");
        }
    }
}
~~~

Đầu ra mong đợi trong điều kiện provider đã được kiểm soát:

~~~text
unsupported-name
~~~

Nếu test chạy trong runtime có provider bổ sung, test phải dùng tên fixture do chính test/provider kiểm soát hoặc xác minh capability trước. Không chọn một tên tùy tiện rồi giả định mọi máy đều không hỗ trợ nó.

## 13. Quy trình chẩn đoán khi charset lookup khác nhau giữa hai môi trường

Khi `Charset.forName(name)` thành công trên máy phát triển nhưng ném `UnsupportedCharsetException` trên production:

1. Ghi chính xác chuỗi cấu hình trước khi normalize.
2. Ghi canonical name nếu lookup thành công.
3. Ghi `java --version`, `java.vendor` và `java.runtime.version`.
4. Kiểm tra `Charset.availableCharsets()` trên hai runtime.
5. Kiểm tra JAR/module provider có được đóng gói ở cả hai môi trường không.
6. Với modular app, kiểm tra module provider và service registration.
7. Kiểm tra custom runtime image có giữ module/dependency cần thiết không.
8. Tạo một chương trình tối thiểu chỉ gọi `Charset.forName(name)`.
9. Không thay đổi tên cấu hình thành alias ngẫu nhiên để làm lỗi biến mất; xác minh tên đó có nằm trong tài liệu/provider.
10. Ghi kết luận: input sai cú pháp, charset không được hỗ trợ hay provider không được triển khai.

Thông tin môi trường nên được thu thập mà không làm lộ dữ liệu nhạy cảm trong config. Nếu tên charset lấy từ content type bên ngoài, log giá trị đã sanitize và giới hạn độ dài input.

## 14. Những nhầm lẫn thường gặp

| Nhầm lẫn | Cách hiểu đúng |
|---|---|
| `Charset.forName("UTF-8")` hỏi default charset | Nó tra cứu charset tên UTF-8; `defaultCharset()` mới hỏi default |
| `UTF8` và `UTF-8` chắc chắn là hai charset | Một tên có thể là alias của canonical name; kiểm tra bằng `name()` |
| Alias list giống nhau trên mọi JDK | Provider/vendor có thể công bố alias khác nhau |
| `isSupported()` xử lý mọi input sai bằng `false` | Tên sai cú pháp có thể ném `IllegalCharsetNameException`; null ném NPE |
| `UnsupportedCharsetException` nghĩa là tên sai cú pháp | Tên hợp lệ nhưng runtime không hỗ trợ |
| `forName()` tự fallback sang UTF-8 | Không có fallback tự động |
| Mọi charset ngoài UTF-8 đều lỗi thời | Java vẫn hỗ trợ nhiều charset chuẩn; chọn theo format/giao thức |
| `displayName()` là canonical name | Dùng `name()` để lấy canonical name |
| So sánh charset bằng `==` là hợp đồng | Dùng `equals()` hoặc so sánh canonical name |
| `StandardCharsets.UTF_8` phụ thuộc default charset | Đây là hằng số explicit, không phụ thuộc default |
| JEP 400 làm mọi I/O tự động UTF-8 | Chỉ thay default charset; nhiều API có quy tắc encoding riêng hoặc nhận charset tường minh |

## 15. Bài tập thực hành

### Bài 1 — Chuẩn hóa tên charset

Gọi `Charset.forName()` với `UTF-8`, `utf-8` và `UtF-8`. In `name()` cho từng kết quả.

**Tiêu chí đạt:** Giải thích được vì sao tên đầu vào khác chữ hoa/chữ thường nhưng canonical name thống nhất.

### Bài 2 — Khám phá alias

Lấy `StandardCharsets.UTF_8.aliases()`, duyệt từng alias và resolve lại bằng `Charset.forName()`.

**Tiêu chí đạt:** Kiểm tra mọi alias do runtime công bố trỏ về cùng canonical name mà không hard-code danh sách alias.

### Bài 3 — Phân biệt hai loại lỗi

Thử một tên không hợp lệ như `UTF 8` và một tên hợp lệ nhưng không được provider hỗ trợ.

**Tiêu chí đạt:** Phân biệt `IllegalCharsetNameException` với `UnsupportedCharsetException`, nêu điều kiện để test unsupported có thể tái hiện.

### Bài 4 — Kiểm tra charset provider

Liệt kê `Charset.availableCharsets()` trên JDK đầy đủ và custom runtime image của dự án. Nếu có provider bổ sung, kiểm tra module/service configuration.

**Tiêu chí đạt:** Giải thích được vì sao hai runtime có thể có danh sách charset khác nhau.

### Bài 5 — Thiết kế fallback

Viết hàm đọc tên charset từ config. Khi config vắng mặt, dùng UTF-8 explicit; khi tên sai hoặc không được hỗ trợ, trả lỗi cấu hình có cause.

**Tiêu chí đạt:** Không âm thầm fallback khi config đã cung cấp một tên sai.

## 16. Tài liệu chính thức

1. [Charset — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/Charset.html): `forName`, `isSupported`, `name`, `aliases`, `availableCharsets` và exception.
2. [StandardCharsets — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/StandardCharsets.html): các charset bắt buộc được hỗ trợ.
3. [IllegalCharsetNameException — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/IllegalCharsetNameException.html): lỗi tên charset không hợp lệ.
4. [UnsupportedCharsetException — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/UnsupportedCharsetException.html): lỗi charset không được runtime hỗ trợ.
5. [CharsetProvider — Java SE 27 API](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/nio/charset/spi/CharsetProvider.html): SPI cho provider charset bổ sung.
6. [JEP 400 — UTF-8 by Default](https://openjdk.org/jeps/400): thay đổi default charset từ JDK 18 và lưu ý tương thích.
7. [JEP 247 — Compile for Older Platform Versions](https://openjdk.org/jeps/247): bối cảnh API baseline khi compile với release cũ.

**Kết quả cần đạt:** Có thể nhận tên charset từ cấu hình, resolve đúng canonical name, kiểm tra alias, phân biệt tên sai cú pháp với charset không được hỗ trợ và chọn fallback theo chính sách ứng dụng. Khi dùng encoding cố định như UTF-8, ưu tiên `StandardCharsets.UTF_8`; khi cần tra cứu tên động, dùng `Charset.forName()` và xử lý lỗi theo đúng nguyên nhân.
