# Kiểm thử tương thích khi bổ sung hành vi vào interface (Java 8 và JDK hiện đại)

## 1. Mục tiêu và vấn đề cần giải quyết

Một interface Java là **hợp đồng công khai** giữa thư viện và code triển khai. Từ Java 8, người thiết kế API có thể bổ sung **default method** để cung cấp hành vi ngay trong interface, thường giúp các implementation cũ dùng được chức năng mới mà không phải tự viết method. Nhưng tuyên bố “thêm default method là tương thích” chỉ đúng khi bạn **nói rõ tương thích ở mức nào và đã kiểm thử điều gì**.

Bài học này tập trung trực tiếp vào **kiểm thử tương thích khi bổ sung hành vi vào interface**, không chỉ ôn cú pháp `default`. Bạn sẽ biết cách:

- Phân biệt **binary compatibility**, **source compatibility** và **behavioral compatibility**.
- Thiết kế bộ kiểm thử có **bản API v1 và v2**, giữ nguyên binary client cũ rồi thay thư viện mới.
- Phát hiện xung đột giữa các default method, khác biệt khi class override, và rủi ro `IncompatibleClassChangeError` tại thời điểm gọi.
- Kiểm tra cả caller cũ, implementation cũ, code dùng lambda/functional interface, và caller mới.
- Lập bảng bằng chứng và tiêu chí phát hành thay vì chỉ dựa vào một lần `mvn test` hoặc unit test chạy trên một phiên bản.
- Dùng công cụ và ví dụ **hiện còn áp dụng trên các JDK được duy trì**. Ví dụ chính dùng cú pháp Java 8; có thể chạy trên JDK hiện đại với `javac --release 8` để kiểm tra mức API/source/bytecode mục tiêu.

**Nguyên tắc quan trọng:** Tương thích nhị phân không đồng nghĩa “mọi client biên dịch lại được”, cũng không đồng nghĩa “hành vi chạy vẫn giống trước”. Java Language Specification (JLS) Chapter 13 mô tả quy tắc nhị phân; các thay đổi về ngữ nghĩa cần test nghiệp vụ riêng.

## 2. Ba chiều tương thích phải kiểm riêng

| Chiều | Câu hỏi | Bằng chứng thực tế |
| --- | --- | --- |
| **Binary** | File `.class` của client/implementation cũ còn liên kết, gọi chạy được khi thay API jar mới mà **không biên dịch lại client**? | Giữ class v1, chỉ thay jar API v2, chạy đường gọi cũ và đường gọi có liên quan |
| **Source** | Toàn bộ **mã nguồn** của client/implementation cũ còn biên dịch được khi dùng API v2? | Clean compile từ nguồn cũ với dependency v2, ghi rõ compiler/release |
| **Behavioral/contract** | Kết quả, exception, side effect, thứ tự gọi, tính đồng thời và các bất biến nghiệp vụ có còn đúng? | Regression/contract tests, boundary tests, integration tests trước và sau |

Ví dụ: interface v1 chỉ có `String normalize(String)` abstract; v2 đổi thành default. Binary của class cũ có thể không hỏng, nhưng nếu default v2 dùng một quy tắc trim/normalization khác với implementation cũ, kết quả trên một client thay thế implementation có thể đổi. **Compiler không kiểm được ý nghĩa nghiệp vụ**.

Tương tự, thêm một default method thường là một thay đổi **binary-compatible** theo JLS, nhưng có thể dẫn đến **source collision** khi biên dịch lại, hoặc một lời gọi trên binary đã tồn tại ném `IncompatibleClassChangeError` nếu hai default độc lập trở thành ứng viên cạnh tranh. Đây là khác biệt đặc biệt cần đưa vào regression suite.

### Ma trận tối thiểu

| Client/implementation | Interface/runtime được cung cấp | Mục đích |
| --- | --- | --- |
| v1 binary, **không rebuild** | API v1 | Baseline đã biết đúng |
| v1 binary, **không rebuild** | API v2 | Kiểm tra binary compatibility và hành vi cũ |
| v1 source, **clean rebuild** | API v2 | Kiểm tra source compatibility, overload/override/conflict |
| v2 source và v2 implementation | API v2 | Kiểm tra tính năng mới, contract mới, ngoại lệ |
| v2 binary, không rebuild | API v1 | Chỉ khi cam kết hỗ trợ ngược: kiểm tra kỳ vọng thất bại/ràng buộc version |

Không chỉ chạy hàng “v2 source + v2 API”. Nếu mọi thứ luôn được build lại cùng nhau, một số lỗi binary trong ứng dụng đã triển khai sẽ không được phát hiện.

## 3. Những kiểu thay đổi cần phân loại trước khi test

### 3.1. Thêm default method vào interface

~~~java
// API v1:
public interface MessageFormatter {
    String format(String text);
}

// API v2 (minh họa phiên bản thay thế, không cùng file với v1):
public interface MessageFormatter {
    String format(String text);

    default String formatTrimmed(String text) {
        return format(text.trim());
    }
}
~~~

**Lợi ích:** Một implementation cũ đã có `format` thường có thể nhận hành vi `formatTrimmed` từ default khi chạy với API v2 mà không sửa mã. **Rủi ro:** một interface khác được implementation đó triển khai có thể cũng có default cùng chữ ký; phải kiểm tra khả năng phân giải, cả ở source lẫn khi gọi binary cũ.

**Cảnh báo:** `formatTrimmed(null)` ném `NullPointerException` do `trim()`. Đây là ví dụ hợp đồng rõ ràng, không mặc nhiên “normalize mọi dữ liệu an toàn”. Nếu public API trước đây có chính sách null đặc biệt, test phải xác minh để tránh đổi hành vi âm thầm.

### 3.2. Thêm abstract method

~~~java
// API v1:
interface Reader {
    String read();
}

// API v2 (minh họa, không đặt chung file):
interface Reader {
    String read();
    String checksum(); // Abstract mới.
}
~~~

Theo quy tắc binary-compatibility của JLS, thêm abstract method vào interface **không phá liên kết của binary cũ chỉ vì sự tồn tại của method mới**. Nhưng:

- Clean rebuild một **concrete implementation cũ** thiếu `checksum()` sẽ **báo lỗi compile**.
- Nếu đường gọi mới `checksum()` được thực hiện trên một implementation binary cũ không có implementation phù hợp, có thể xuất hiện `AbstractMethodError` ở runtime.
- Một interface đã là **functional interface** (một SAM) có thể mất đặc tính SAM nếu bạn thêm abstract method độc lập thứ hai; các lambda/method reference target interface đó không còn biên dịch. Test phải bao gồm cả các client dùng lambda, không chỉ class `implements`.

Vì vậy, thêm abstract method **không** phải chiến lược mặc định để mở rộng thư viện muốn duy trì source compatibility.

### 3.3. Thêm static method

~~~java
interface TextRules {
    static boolean isEmpty(String text) {
        return text == null || text.isEmpty();
    }
}
~~~

Static method của interface được gọi qua `TextRules.isEmpty(...)`; nó **không** được thừa hưởng như instance method của class `implements TextRules`. Việc thêm static method không tự tạo nghĩa vụ implement, nhưng vẫn phải test API lookup/source nếu tên mới gây nhầm lẫn hoặc tương tác với overload trong code thực tế.

### 3.4. Đổi abstract thành default, hoặc thay đổi default sẵn có

~~~java
// v1:
interface Parser {
    String parse(String value);
}

// v2:
interface Parser {
    default String parse(String value) {
        return value.trim();
    }
}
~~~

Một method từ abstract chuyển thành default có thể làm bớt nghĩa vụ implement trong một số implementation, và JLS xem thay đổi này **binary-compatible** theo nghĩa xác định; tuy nhiên vẫn có nguy cơ xung đột default ở invocation. Ngược lại, đổi logic bên trong default đang dùng có thể giữ binary/source compatibility nhưng **đổi hành vi**: quy tắc null, locale, exception, kết quả trả về hoặc side effect. Những rủi ro này chỉ thấy rõ bằng contract test.

### 3.5. Không đồng nhất với các thay đổi khác

Xóa method, đổi tên, đổi type của parameter/return, chuyển instance sang static, đổi accessibility, sửa hierarchy hay đổi generic contract là các thay đổi **khác hẳn** việc chỉ thêm một default. Chúng có thể phá source/binary/behavior theo những cách riêng (ví dụ `NoSuchMethodError`, `IllegalAccessError`, `VerifyError`). Không áp dụng nhầm kết luận “adding default is binary compatible” cho các thay đổi đó.

## 4. Cơ chế chọn default: lớp thắng, nhánh cụ thể hơn thắng, xung đột phải giải quyết

Khi có nhiều implementation ứng viên cùng chữ ký, Java tuân theo các quy tắc ngôn ngữ về override và kế thừa:

1. **Concrete method thích hợp của class/superclass** có ưu tiên so với default method của interface (thường gọi *class wins*).
2. Một subinterface override method từ superinterface có thể cung cấp implementation **cụ thể hơn**.
3. Nếu class triển khai **hai interface độc lập** đều có default tương đương mà không có lời giải rõ, clean compilation thường thất bại: cần class **override**.
4. Hai đường đi tới **cùng một default declaration** qua diamond không nhất thiết tạo xung đột.

~~~java
interface Left {
    default String tag() {
        return "L";
    }
}

interface Right {
    default String tag() {
        return "R";
    }
}

// Sai khi compile mới vì hai default độc lập:
// class Broken implements Left, Right {}

// Đúng: giải quyết xung đột rõ ràng.
class Resolved implements Left, Right {
    @Override
    public String tag() {
        return Left.super.tag() + Right.super.tag();
    }
}
~~~

**Chú ý với binary cũ:** JLS `13.5.7` giải thích rằng thêm default có thể không làm hỏng việc **link** binary cũ, nhưng một lời gọi có liên quan vẫn có thể ném `IncompatibleClassChangeError` nếu một qualifying interface có hai default thích hợp độc lập. Vì vậy phải test **invoke thực tế**, không chỉ tải class thành công hoặc chạy một test không đi qua method đó.

Đừng đoán rằng thứ tự `implements Left, Right` sẽ quyết định implementation; Java không lựa chọn default theo thứ tự khai báo đó. Nếu ứng dụng có nhiều implementation ngoài quyền kiểm soát, hãy bổ sung coverage bằng các adapter/fixture mô phỏng chúng.

## 5. Thiết kế regression/contract test đúng mục tiêu

### 5.1. Chụp hành vi v1 trước khi sửa interface

Với mỗi API public dự kiến thêm default, ghi lại:

- Method hiện có, chữ ký JVM có liên quan và các generic bounds;
- Input hợp lệ, input biên, null nếu hợp đồng cho phép, encoding/locale/timezone nếu có liên quan;
- Output, kiểu exception, trạng thái side effect, thứ tự và số lần gọi;
- Các implementation trực tiếp, subclass, lớp kế thừa nhiều interface, adapter, proxy/mock đang được dùng;
- Target functional interface được dùng bởi lambda hoặc method reference;
- Tính đồng thời, serialization/ABI hay reflection nếu sản phẩm có phụ thuộc thật.

Một test contract nên mô tả **hành vi quan sát được** thay vì chi tiết private hoặc text implementation. Nếu đổi cấu trúc class mà hành vi vẫn đúng, test không nên thất bại chỉ vì tên helper đã đổi.

### 5.2. Bộ test cho default mới

Cho v2 có `formatTrimmed`, tối thiểu cần kiểm:

1. Implementation v1 không override method mới vẫn dùng được default;
2. Implementation v2 override method mới thật sự được dispatch đến override;
3. `formatTrimmed` gọi `format` của **đúng instance**, không tạo object thay thế;
4. Kết quả được giữ đúng cho chuỗi có/không có khoảng trắng, chuỗi rỗng;
5. Null được xử lý theo **chính sách API** (ném exception hay trả giá trị dự phòng); không tự phỏng đoán;
6. Exception từ `format` không bị nuốt hoặc biến thành success giả;
7. Code xử lý đồng thời không bị biến thành unsafe khi default mới gọi thêm stateful operations.

Nếu API mới chuyển kết quả qua service/DB/network, kiểm cả idempotency, retry, timeout và side effect. Đó là behavioral compatibility, không phải trách nhiệm của compiler.

### 5.3. Bộ test riêng cho inheritance/override

Một interface có thể được nhiều kiểu sử dụng; test các hình dạng sau:

| Fixture | Cần xác minh |
| --- | --- |
| Concrete class trực tiếp `implements` một interface | Kế thừa default mới, không bắt buộc implement |
| Concrete class có method cùng chữ ký | Class method/override được chọn; kết quả đúng |
| Subinterface override default | Implementation lấy bản chuyên biệt; không gọi nhầm bản cha |
| Một class implement hai interface độc lập có default trùng | Compile-time conflict hoặc override tường minh |
| Diamond đi đến cùng default khai báo ở gốc | Không đánh đồng với hai default độc lập |
| Lambda gán cho `@FunctionalInterface` | Bổ sung default không làm thay đổi SAM; bổ sung abstract độc lập có thể phá |
| Implementation chỉ có binary v1 | Chạy được khi cung cấp API v2, không phụ thuộc rebuild |
| Runtime classpath khác với compile classpath | Test phát hiện nhầm jar/duplicate class, `NoSuchMethodError` và lỗi invoke khi có |

### 5.4. Phân biệt test âm và test dương

Test **dương** dùng source hợp lệ và kỳ vọng compile/run thành công. Test **âm** dùng fixture có chủ đích không hợp lệ và kỳ vọng compiler báo lỗi, chẳng hạn class không override hai default độc lập. Đừng trộn cả hai vào một source file rồi khiến CI luôn fail mà không nói đó là test âm.

Một test âm đáng tin nên kiểm **exit code khác 0**, không phụ thuộc cứng vào câu chữ lỗi compiler từng phiên bản hay locale. Với runtime error, kiểm kiểu exception và tình huống tạo ra lỗi, không chỉ tìm một chuỗi stack trace.

## 6. Ví dụ chạy độc lập: kiểm tra hành vi kế thừa/override/giải quyết xung đột

Để không phụ thuộc Maven, Gradle hay framework test, tạo file **`InterfaceEvolutionChecks.java`** (UTF-8). Mã chạy trên một JDK hiện đại và chỉ dùng tính năng Java 8:

~~~java
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.Locale;

public class InterfaceEvolutionChecks {
    interface Sink {
        void write(String value);

        default String normalize(String value) {
            return value.trim();
        }

        default void writeNormalized(String value) {
            write(normalize(value));
        }
    }

    static class Collector implements Sink {
        final List<String> values = new ArrayList<String>();

        @Override
        public void write(String value) {
            values.add(value);
        }
    }

    static final class LoudCollector extends Collector {
        @Override
        public String normalize(String value) {
            return value.trim().toUpperCase(Locale.ROOT);
        }
    }

    interface Named {
        default String id() {
            return "base";
        }
    }

    interface Detailed extends Named {
        @Override
        default String id() {
            return "detail";
        }
    }

    static final class Item implements Detailed {
    }

    interface Left {
        default String stamp() {
            return "L";
        }
    }

    interface Right {
        default String stamp() {
            return "R";
        }
    }

    static final class Both implements Left, Right {
        @Override
        public String stamp() {
            return Left.super.stamp() + Right.super.stamp();
        }
    }

    @FunctionalInterface
    interface Transformer {
        String transform(String value);

        default String kind() {
            return "default";
        }
    }

    public static void main(String[] args) {
        Collector oldStyle = new Collector();
        oldStyle.writeNormalized("  A ");
        System.out.println("inherited: " + oldStyle.values);

        LoudCollector overridden = new LoudCollector();
        overridden.writeNormalized("  b ");
        System.out.println("override: " + overridden.values);

        System.out.println("subinterface: " + new Item().id());
        System.out.println("conflict resolved: " + new Both().stamp());

        Transformer transformer = value ->
            value.toUpperCase(Locale.ROOT);

        System.out.println("functional: "
            + transformer.transform("ok") + "/" + transformer.kind());

        if (!oldStyle.values.equals(Arrays.asList("A"))
                || !overridden.values.equals(Arrays.asList("B"))
                || !"detail".equals(new Item().id())
                || !"LR".equals(new Both().stamp())
                || !"OK".equals(transformer.transform("ok"))) {
            throw new AssertionError("Interface contract changed");
        }
        System.out.println("checks: PASS");
    }
}
~~~

Biên dịch trên một JDK được bảo trì, có hỗ trợ target 8:

~~~text
javac --release 8 -encoding UTF-8 InterfaceEvolutionChecks.java
java InterfaceEvolutionChecks
~~~

**Stdout chính xác (6 dòng):**

~~~text
inherited: [A]
override: [B]
subinterface: detail
conflict resolved: LR
functional: OK/default
checks: PASS
~~~

**Tại sao đúng?**

1. `Collector` không override `normalize`/`writeNormalized`, nên thừa hưởng cả hai default: `"  A "` → `"A"`.
2. `LoudCollector` ghi đè `normalize`: default `writeNormalized` gọi virtual method trên đúng instance `LoudCollector`, do đó `"  b "` → `"B"`.
3. `Detailed` chuyên biệt hóa default `Named.id` thành `"detail"`.
4. `Both` phải override `stamp` vì hai default độc lập; dùng `Left.super` và `Right.super` rõ ràng, trả `"LR"`.
5. `Transformer` vẫn là functional interface vì chỉ `transform` trừu tượng, `kind` là default; lambda hoạt động bình thường.
6. Các điều kiện `AssertionError` nêu một phần contract. Nếu sai, chương trình không in `checks: PASS`.

Ví dụ này kiểm **behavioral/source** trong một snapshot API. Nó **không thay thế test binary hai phiên bản** ở mục kế tiếp, vì compiler ở đây build mọi kiểu cùng nhau.

## 7. Thực hành quan trọng nhất: test binary v1 với interface v2

Muốn chứng minh binary compatibility, **giữ nguyên client và implementation v1 đã biên dịch**. Chỉ thay interface jar/class theo v2 rồi chạy. Làm trong thư mục thực hành riêng, không trộn các phiên bản cùng một thư mục output.

### 7.1. Cấu trúc thư mục

~~~text
compat-lab/
  v1/
    src/sample/Formatter.java
    src/sample/LegacyFormatter.java
    src/sample/Client.java
    out/                     (tạo bằng javac)
  v2/
    src/sample/Formatter.java
    src/sample/ClientV2.java
    out/                     (tạo bằng javac)
~~~

Hai file `Formatter.java` có cùng tên class và package nhưng nằm trong **hai thư mục riêng**; không đưa cả hai source vào cùng lệnh compile.

### 7.2. API và implementation v1

**`v1/src/sample/Formatter.java`**

~~~java
package sample;

public interface Formatter {
    String format(String text);
}
~~~

**`v1/src/sample/LegacyFormatter.java`**

~~~java
package sample;

public final class LegacyFormatter implements Formatter {
    @Override
    public String format(String text) {
        return "[" + text + "]";
    }
}
~~~

**`v1/src/sample/Client.java`**

~~~java
package sample;

public final class Client {
    public static void main(String[] args) {
        Formatter formatter = new LegacyFormatter();
        System.out.println(formatter.format("A"));
    }
}
~~~

Từ thư mục `compat-lab` (đã tạo các thư mục `src` ở trên):

~~~text
javac --release 8 -d v1/out v1/src/sample/Formatter.java v1/src/sample/LegacyFormatter.java v1/src/sample/Client.java
java -cp v1/out sample.Client
~~~

Kết quả:

~~~text
[A]
~~~

Giữ nguyên toàn bộ bytecode `v1/out`; **không chạy lại `javac` để ghi đè các file này** khi test với v2.

### 7.3. API v2 bổ sung default

**`v2/src/sample/Formatter.java`**

~~~java
package sample;

public interface Formatter {
    String format(String text);

    default String formatTrimmed(String text) {
        return format(text.trim());
    }
}
~~~

**`v2/src/sample/ClientV2.java`**

~~~java
package sample;

public final class ClientV2 {
    public static void main(String[] args) {
        Formatter formatter = new LegacyFormatter();
        System.out.println(formatter.formatTrimmed(" B "));
    }
}
~~~

Compile **chỉ API v2**, không rebuild class `LegacyFormatter` hay `Client` cũ:

~~~text
javac --release 8 -d v2/out v2/src/sample/Formatter.java
~~~

Trên Linux/macOS, dấu phân cách `classpath` là dấu hai chấm `:`; trên Windows là dấu chấm phẩy `;`. Tất cả ví dụ dưới đây dùng Linux/macOS; khi chạy PowerShell/Windows, thay `v2/out:v1/out` bằng `v2/out;v1/out` (nếu cần, đặt toàn bộ giá trị trong dấu nháy).

**Test 1 — binary client cũ + interface mới:**

~~~text
java -cp v2/out:v1/out sample.Client
~~~

Stdout dự kiến:

~~~text
[A]
~~~

Classloader tìm `sample.Formatter` v2 trước vì `v2/out` đứng trước trong classpath, nhưng vẫn dùng `LegacyFormatter.class` và `Client.class` từ `v1/out`. Kết quả cũ được giữ, cho thấy **lời gọi cũ trong fixture** tương thích trong trường hợp kiểm thử này.

**Test 2 — caller mới + implementation binary cũ:**

~~~text
javac --release 8 -cp v2/out:v1/out -d v2/out v2/src/sample/ClientV2.java
java -cp v2/out:v1/out sample.ClientV2
~~~

Stdout dự kiến:

~~~text
[B]
~~~

Ở đây `ClientV2` gọi default `formatTrimmed` trên `LegacyFormatter` binary cũ. Default được kế thừa qua interface v2, gọi lại virtual `format` của implementation cũ, nên `" B "` được trim thành `"B"` và format thành `"[B]"`.

**Quan trọng về phạm vi kết luận:** Hai test trên chỉ chứng minh hành vi **của fixture cụ thể**. Không thể từ đó tuyên bố mọi plugin/client ngoài hệ thống đều an toàn. Cần lặp với các implementation và tổ hợp interface thật trong sản phẩm.

### 7.4. Chạy kiểm thử với client mới và runtime cũ khi có yêu cầu

Nếu `ClientV2` gọi `formatTrimmed` nhưng runtime chỉ chứa interface v1, lời gọi tới method không tồn tại trong runtime API cũ có thể gây `NoSuchMethodError`. Điều này không mâu thuẫn với kết luận “v1 binary chạy với v2 API”: bạn đã đảo chiều tổ hợp phiên bản. Chỉ kiểm nếu ứng dụng thực sự cam kết **client v2 chạy được trên library v1**; thông thường cần dùng dependency version tối thiểu rõ ràng.

Để test đúng, đặt `ClientV2.class` trong output **riêng** rồi dùng classpath có API v1 trước; không thể giả vờ test runtime v1 khi vô tình vẫn để `Formatter.class` v2 xuất hiện trước trong cùng classpath.

### 7.5. Vì sao phải tách output/classpath?

Nếu build tool tự động rebuild mọi thứ khi thay interface, hoặc classpath chứa lẫn cả `Formatter.class` v1/v2 mà không kiểm thứ tự, test sẽ không còn trả lời câu hỏi binary compatibility. Trong CI thực tế:

- Xuất bản artifact v1 và lưu checksum/binary test fixtures;
- Biên dịch client v1 bằng **dependency v1**, giữ nguyên `.class`/jar;
- Chạy client đó cùng dependency v2, không rebuild client;
- Trong một job khác, clean compile source cũ bằng dependency v2;
- Kiểm tra classpath/dependency resolution thực tế, tránh duplicate classes hoặc jar transitive kéo sai version.

## 8. Hai ví dụ rủi ro bắt buộc có test âm

### 8.1. Thêm default tạo conflict

Phiên bản v1:

~~~java
interface Greeter {
    // Chưa có method hello().
}

interface Badge {
    default String hello() {
        return "badge";
    }
}

// Với v1, class này hợp lệ:
class DualService implements Greeter, Badge {
}
~~~

Phiên bản v2 của `Greeter`:

~~~java
interface Greeter {
    default String hello() {
        return "greeter";
    }
}

// Khi clean compile DualService implements Greeter, Badge,
// hai default độc lập có thể xung đột; phải override tường minh.
~~~

Một cách xử lý source conflict:

~~~java
class DualService implements Greeter, Badge {
    @Override
    public String hello() {
        return Greeter.super.hello(); // Hoặc lựa chọn nghiệp vụ phù hợp.
    }
}
~~~

Các đoạn trên là **các phiên bản thay thế**, không được ghép cùng một tệp source. Nếu bạn chỉ giữ binary v1 và thay `Greeter` mới, không nhất thiết gặp lỗi ngay khi load class; xung đột có thể bộc lộ **khi gọi method** qua qualifying interface như JLS `13.5.7` mô tả, với `IncompatibleClassChangeError`. Bài test phải thực sự gọi đường liên quan và phân biệt lỗi compile-time với invocation-time.

### 8.2. Thêm abstract method phá source của implementation cũ

~~~java
// v1:
interface Job {
    void run();
}

// v2:
interface Job {
    void run();
    void cancel(); // Abstract method mới.
}

// Class cũ:
// class OldJob implements Job {
//     @Override public void run() { }
// }
~~~

`OldJob` là hợp lệ với v1; nếu clean compile against v2, thiếu `cancel`. Một client chỉ gọi `run` trên binary cũ vẫn có thể chạy với v2, nhưng khi gọi method mới trên instance đó, có nguy cơ `AbstractMethodError`. Nếu `Job` được sử dụng như functional interface, thêm abstract thứ hai còn làm việc gán `Job j = () -> ...` không hợp lệ khi biên dịch với v2.

**Lựa chọn:** Bổ sung default có semantics hợp lý, tạo một **subinterface** mở rộng contract, hoặc phát hành major version và migration rõ ràng. Không thêm default giả `return null` chỉ để compiler cho qua nếu kết quả đó không đúng nghiệp vụ.

## 9. Tự động hóa trong CI theo lớp bảo đảm

Một pipeline tối thiểu nên tách thành các job có mục đích rõ:

~~~text
1. baseline-v1:
   - build API v1 + client/implementation fixtures v1
   - chạy contract tests trên v1
   - lưu immutable artifacts (jar/.class) và output mong đợi

2. binary-compat-v2:
   - build API v2
   - chạy nguyên client/implementation v1 artifacts với API v2
   - thực thi các method cũ và đường default liên quan
   - fail nếu linkage/invocation error hoặc hành vi sai

3. source-compat-v2:
   - clean compile từ nguồn v1 với API v2
   - test compile fixtures: override, đa interface, lambda/SAM
   - test âm xác nhận conflict thật sự bị compiler từ chối

4. behavior-v2:
   - unit/contract/integration tests trên v2
   - input biên, null, exception, side effect, concurrency
   - kiểm tra override và subinterface có hành vi đúng

5. packaging-and-release:
   - kiểm runtime/classpath thực tế, dependency convergence
   - ghi rõ compatible versions và chính sách triển khai
~~~

Không cần công cụ đặc biệt để hiểu phương pháp này: `javac`, `java` và các file fixture là đủ chứng minh cả hai chiều cơ bản. Với dự án lớn, chạy job qua Maven/Gradle/JUnit đang được bảo trì để quản lý dependency và báo cáo; đừng phụ thuộc vào build cache làm thay thế kiểm thử **clean rebuild** hoặc kiểm thử **binary cũ chưa rebuild**.

### Phân vai công cụ

| Công cụ | Giúp làm gì | Không chứng minh điều gì một mình |
| --- | --- | --- |
| `javac --release N` | Kiểm tra source/API/bytecode tương thích N | Không bảo đảm runtime cũ được vá hoặc external dependency tương thích |
| `java -cp ...` với fixture v1 binary | Kiểm tra liên kết và hành vi thực thi ở tổ hợp version thật | Không chứng minh mọi implementation ngoài hệ thống |
| `javap -public`/`javap -s` | Quan sát method descriptors/API đã biên dịch | Không kiểm chứng nghiệp vụ/side effect |
| JUnit Jupiter (JUnit 5+) | Chạy contract/regression tests và assertions | Không tự kiểm binary nếu test luôn rebuild client |
| Maven/Gradle dependency tools | Phát hiện thư viện bị chọn sai version/duplicate | Không thay thế test runtime invocation |
| `jdeps` | Phân tích quan hệ phụ thuộc của bytecode | Không phải một verdict đầy đủ về source/binary/behavioral compatibility |

Nếu dùng công cụ so sánh API tự động (ví dụ các giải pháp phân tích bytecode/API được dự án bảo trì), coi kết quả là **tín hiệu hỗ trợ** và xác minh tình huống rủi ro bằng các fixture thực sự chạy. Không quảng bá một công cụ như lời bảo đảm tuyệt đối; semantics Java và test sản phẩm vẫn là căn cứ quyết định.

## 10. Các tình huống kiểm thử cụ thể không nên bỏ sót

### A. Class có implementation riêng trùng chữ ký mới

Nếu implementation cũ đã có `public String formatTrimmed(String)` trước khi interface v2 bổ sung cùng method dưới dạng default, method của **class** thường được ưu tiên cho instance đó. Source có thể vẫn compile nhưng default mới **không được chạy** trên class đó. Test phải xác minh behavior của phương thức class vẫn đúng hợp đồng mới, không chỉ thấy không có compile error.

### B. Hierarchy interface rộng

Một client có thể implement nhiều interface gián tiếp qua superclass hoặc subinterface. Hãy test graph kế thừa thực tế: hai default cạnh tranh, subinterface override một default, diamond chỉ kế thừa **cùng một declaration**, và class có method cụ thể.

### C. Overload và type inference

Thêm method overload hoặc default mới có thể làm source client có lời gọi `null`, lambda hoặc method reference trở nên **ambiguous** khi recompile, dù bytecode cũ giữ method descriptor đã chọn tại compile-time trước. Có một bài test cho từng call site nhạy cảm với overload nếu API có các overload áp dụng đồng thời.

### D. Checked exceptions

Nếu default method gọi abstract method có `throws IOException`, body default phải catch hoặc khai báo `throws IOException` tương ứng. Kiểm tra tương thích checked-exception contract khi override/recompile. Một thay đổi `throws` có thể không thay đổi bytecode linkage tương ứng, nhưng vẫn tác động đến source compile và chính sách lỗi của caller.

### E. Không sửa logic cũ ngoài ý muốn

Bổ sung default thường định nghĩa hành vi mới bằng những method trừu tượng có sẵn. Nếu nó thay đổi thứ tự, số lần hoặc ngữ cảnh gọi method cũ, các implementation có side effect (ghi DB, audit, cache, khóa...) có thể bị ảnh hưởng. Nên test số lần gọi và trạng thái trước/sau, không chỉ test kết quả trả về.

### F. Null và collection/stream contract

Default mới có thể gọi `trim` trên null, đọc một collection không hỗ trợ mutate, hoặc tạo pipeline lazy. Việc một default trên interface tồn tại **không** bảo đảm mọi implementation có cùng mức độ mutability/concurrency. Ví dụ các method mặc định của `Map` hay `Collection` có nghĩa vụ và ngoại lệ tùy contract; không gộp tất cả thành một behavior duy nhất.

### G. Runtime và dependency khác môi trường build

Một thư viện có thể biên dịch với JDK mới nhưng chạy trên JDK mục tiêu không đủ API; dependency transitive có thể kéo hai phiên bản của cùng thư viện; deployment nhiều service có thể nâng cấp không đồng thời. Test **đúng runtime và dependency graph được hỗ trợ**, không chỉ IDE/JDK của một developer.

### H. Performance và concurrency regression

Default mới làm tăng số lời gọi, tạo allocation hoặc locking có thể khiến chức năng chạy đúng nhưng chậm/không ổn định. Đo baseline và chạy concurrency/integration test khi có rủi ro thực tế, tránh tuyên bố “tương thích hoàn toàn” chỉ từ unit tests.

## 11. Checklist đánh giá bản phát hành

Trước khi phát hành API v2, review theo các câu hỏi có bằng chứng:

- [ ] API thay đổi **chỉ** thêm method hay còn đổi signature, inheritance, visibility, return type, generic bounds, exception contract?
- [ ] Đã lưu API v1, client binaries v1 và expected outputs mà không rebuild ngoài ý muốn?
- [ ] Client binaries v1 đã chạy với API v2 trên runtime hỗ trợ, kể cả những method/hierarchy bị ảnh hưởng?
- [ ] Mã nguồn v1 của implementation/client đã clean compile với API v2?
- [ ] Hai default trùng chữ ký đã được kiểm thử và có phương án override/migration?
- [ ] Implementation cũ có method cùng chữ ký mới đã được test về lựa chọn dispatch/hành vi?
- [ ] Lambda/method reference target interface cũ còn hợp lệ, nhất là khi thêm abstract method?
- [ ] Contract tests kiểm null, input biên, exception, thứ tự gọi, state và side effect?
- [ ] Có test caller mới và default method mới trên implementation v1?
- [ ] CI kiểm dependency/classpath của bản deploy, không dùng cả API v1 và v2 một cách vô tình?
- [ ] Đã ghi ranh giới hỗ trợ: JDK target, library versions và hướng dẫn migration?
- [ ] Nếu có interface/implementation của bên thứ ba, đã chọn fixture đại diện và nói rõ phần coverage còn thiếu?

Một thay đổi chỉ được gọi là **đạt tiêu chí phát hành** khi tất cả kiểm tra liên quan đến cam kết sản phẩm đều pass. Một vài test mẫu không chứng minh “mọi code Java ngoài tổ chức đều không gặp conflict”; hãy công bố rõ phạm vi tương thích được kiểm chứng.

## 12. Bài tập có đáp án định hướng

**Bài 1 — Phân biệt ba loại tương thích.** Giả sử thêm default `String trimAndFormat(String)`. Viết một ví dụ về mỗi rủi ro: source conflict khi class dùng hai interface, binary invocation gây conflict, và behavioral change do null. Đáp án định hướng: đây là **ba câu hỏi độc lập**, không thể suy từ test compile đơn lẻ.

**Bài 2 — Chạy test binary đúng nghĩa.** Làm theo mục 7, ghi output của `sample.Client` với v1 API và với v2 API; cả hai phải là `[A]`. Không sửa `LegacyFormatter.class` hoặc `Client.class` v1.

**Bài 3 — Client mới chạy với implementation cũ.** Biên dịch `ClientV2` against v2 API, chạy nó với `LegacyFormatter.class` v1 và `Formatter.class` v2 theo đúng classpath. Dự kiến `[B]`; mô tả tại sao `formatTrimmed` gọi lại `format` cũ.

**Bài 4 — Cố tình thêm abstract method.** Trên một interface v1 có một abstract method, thêm abstract method thứ hai. Kiểm tra class cũ không compile khi rebuild v2 và lambda dùng interface đó không còn là functional. Phân biệt lỗi source với `AbstractMethodError` khi một binary cũ thực sự bị gọi qua method mới.

**Bài 5 — Conflict độc lập.** Tạo hai interface mỗi loại có default `label()`, class implement cả hai; cố compile để quan sát lỗi. Viết override rõ ràng `Left.super.label()` hoặc phối hợp cả hai khi nghiệp vụ cho phép.

**Bài 6 — Đổi implementation của default.** v1 default trả `text.trim()`, v2 đổi sang uppercase (hoặc thay null handling). Xây contract test phát hiện output đã thay đổi dù binary vẫn link.

**Bài 7 — Class wins.** Tạo class có `public String formatTrimmed(String)` trước khi thêm default cùng chữ ký vào interface. Thử cả source rebuild và binary cũ; chứng minh class method được chọn và xác minh nó thỏa chính sách mới.

**Bài 8 — Test method overload với null.** Giả sử v1 có `send(String)`, v2 thêm `send(Integer)`. Kiểm tra call site `send(null)` khi recompile; diễn giải lỗi ambiguity và vì sao bytecode v1 vẫn ghi lời gọi tới một descriptor cụ thể.

**Bài 9 — Thiết kế CI.** Viết pipeline với ba job riêng: v1 baseline, binary-v1-on-v2, source-v1-on-v2. Gắn thêm contract regression suite. Giải thích tại sao “test v2-only” chưa đủ.

**Bài 10 — Phản biện câu khẳng định.** Có người nói: “JLS bảo thêm default binary compatible, vậy có thể release mà không cần thử client cũ.” Hãy chỉ ra phản ví dụ ở `13.5.7` và đề xuất kiểm thử invocation + clean compile + behavior.

**Tiêu chí đạt:** Bạn phân biệt chính xác source/binary/behavior compatibility, hiểu giới hạn quy tắc Java về default method, chạy được code mục 6 có sáu dòng output, thực hiện được thao tác mix binary hai phiên bản mục 7, và đề xuất kế hoạch release/CI có bằng chứng kiểm chứng.

## 13. Tài liệu chính thức và các quy tắc hiện còn áp dụng

- Java Language Specification, Java SE 25, **Chapter 13 Binary Compatibility** và `13.5.7 Interface Method Declarations: https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.5.7
- JLS, `13.2 What Binary Compatibility Is and Is Not: https://docs.oracle.com/javase/specs/jls/se25/html/jls-13.html#jls-13.2
- JLS, `9.4 Interface Method Declarations và `9.4.1 Method Overriding by (and in) Interfaces: https://docs.oracle.com/javase/specs/jls/se25/html/jls-9.html#jls-9.4.1
- JLS, `15.12 Method Invocation Expressions (overload/target selection): https://docs.oracle.com/javase/specs/jls/se25/html/jls-15.html#jls-15.12
- JDK compiler `javac --release`: https://docs.oracle.com/en/java/javase/25/docs/specs/man/javac.html

**Ghi nhớ:** Thêm hành vi vào interface là một hoạt động **API evolution**, không phải thao tác thêm vài dòng source và chạy một test duy nhất. Mọi kết luận về tương thích cần gắn với **phiên bản nào, tổ hợp classpath nào, loại test nào và hành vi quan sát được nào**. Giữ regression fixtures của API/client cũ, kiểm cả compile lẫn runtime invocation, rồi đánh giá semantics bằng contract tests trên JDK còn được duy trì.