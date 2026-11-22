# Chọn interface, lớp trừu tượng hoặc factory cho một điểm mở rộng

## 1. Hiểu đúng bài toán

**Điểm mở rộng (extension point)** là vị trí mà một ứng dụng hoặc thư viện cho phép mã bên ngoài cung cấp hành vi mới mà không cần sửa phần lõi. Trong Java, ví dụ điển hình là thêm một bộ biến đổi dữ liệu, một bộ kiểm tra quy tắc hoặc một adapter cho hệ thống bên thứ ba.

Thiết kế điểm mở rộng cần trả lời ba câu hỏi **khác nhau**:

- **Mã mở rộng phải làm được gì?** Đây là **hợp đồng hành vi**. Interface thường phù hợp nhất.
- **Các triển khai có bắt buộc dùng chung một quy trình hoặc trạng thái nền không?** Abstract class có thể cung cấp **khung triển khai** và bảo vệ bất biến.
- **Ai chọn, cấu hình và tạo đối tượng triển khai?** Factory chịu trách nhiệm **khởi tạo và lựa chọn**.

Vì vậy, interface, abstract class và factory không phải lúc nào cũng là ba phương án loại trừ nhau. Một thiết kế thường dùng **interface làm hợp đồng công khai**, **abstract class làm lớp nền tùy chọn**, và **factory trả về interface**. Host chỉ phụ thuộc vào hợp đồng, không phụ thuộc trực tiếp vào từng plugin.

Ví dụ: một hệ thống nhận văn bản và áp dụng nhiều kiểu biến đổi. Host gọi **Transformer.transform(input)**. Nhà phát triển plugin cung cấp triển khai Transformer; một factory chọn triển khai theo tên và cấu hình. Một số plugin có thể kế thừa lớp nền xử lý chuẩn hóa đầu vào, một số khác triển khai trực tiếp interface.

## 2. So sánh nhanh ba công cụ

| Tiêu chí | Interface | Abstract class | Factory |
|---|---|---|---|
| Mục đích chính | Công bố khả năng và hợp đồng gọi | Tái sử dụng mã, giữ bất biến, định nghĩa quy trình có điểm móc | Chọn và tạo đối tượng, che giấu cách khởi tạo |
| Host nhìn thấy | Kiểu trừu tượng cùng các phương thức | Thường chỉ cần nhìn interface mà lớp nền triển khai | Phương thức tạo, đầu vào cấu hình và kiểu kết quả |
| Nhiều kiểu triển khai khác nhau | Rất phù hợp, kể cả các class đã có superclass | Bị giới hạn bởi đơn kế thừa class | Có thể tạo bất kỳ kiểu triển khai nào phù hợp hợp đồng |
| Logic/trạng thái dùng chung | Default method hỗ trợ logic đơn giản, không giữ trạng thái instance | Có field, constructor, method cụ thể, protected hook | Quản lý cấu hình, dependency và chính sách tạo/cache |
| Buộc tuân thủ một chuỗi thao tác | Chỉ thông qua đặc tả và kiểm thử; default method không tự khóa việc override | Có thể dùng public final template method | Không trực tiếp; có thể chỉ tạo những triển khai hợp lệ |
| Thêm provider khi chạy | Kết hợp registry, DI hoặc ServiceLoader | Không tự giải quyết việc khám phá provider | Có thể bọc registry/ServiceLoader để chọn provider |
| Đánh đổi | Hợp đồng phải nhỏ, rõ, ổn định | Ràng buộc kế thừa và API protected/constructor | Thêm lớp gián tiếp và chính sách vòng đời |

**Quy tắc khởi đầu:** Nếu điểm mở rộng chỉ cần mô tả “làm gì”, bắt đầu bằng **interface**. Chỉ thêm abstract class khi có bất biến hoặc quy trình chung thực sự đáng bảo vệ. Thêm factory khi việc chọn hay tạo đối tượng cần được tách khỏi host.

## 3. Khi nào chọn interface?

Chọn interface nếu:

1. Host chỉ cần gọi một khả năng; các provider có thể dùng thuật toán, thư viện hoặc superclass khác nhau.
2. Người viết plugin không nên bị ép kế thừa một cây class của framework.
3. Cần dễ thay thế provider bằng fake/stub trong kiểm thử, hoặc cho phép triển khai bằng lambda khi interface là functional interface.
4. Hợp đồng cần là ranh giới ổn định giữa module lõi và module mở rộng.

Một hợp đồng tối thiểu có thể là:

~~~java
/** Nhận chuỗi khác null và trả về chuỗi khác null. */
public interface Transformer {
    String transform(String input);
}
~~~

Đoạn này mô tả **hành vi**, chưa quyết định ai tạo đối tượng hoặc thuật toán triển khai. Phần chú thích cần được chuyển thành quy tắc có thể kiểm thử: xử lý null ra sao, có được thay đổi dữ liệu đầu vào không, exception nào được ném, có an toàn khi gọi đồng thời không và có cần đóng tài nguyên không.

Interface có thể có phương thức default, static và private (với phiên bản Java phù hợp), nhưng **không có field trạng thái của từng instance**. Default method nên cung cấp hành vi mặc định có ý nghĩa độc lập; không nên dùng để che giấu một hợp đồng quá lớn hay làm mọi plugin bị buộc tuân theo logic không phù hợp.

**Tránh “god interface”:** Nếu mỗi provider chỉ hỗ trợ một phần trong hàng chục phương thức, hãy tách các khả năng thành interface nhỏ, hoặc mô tả capability rõ ràng. Cung cấp phương thức ném UnsupportedOperationException khắp nơi thường là dấu hiệu hợp đồng sai.

## 4. Khi nào chọn abstract class?

Chọn abstract class nếu những triển khai thực sự phải chia sẻ **một thuật toán khung (Template Method)**, một bất biến hoặc trạng thái được quản lý thống nhất. Ví dụ: mọi bộ xử lý thuộc một họ đều phải kiểm tra input, chuẩn hóa, đo thời gian rồi mới gọi bước biến đổi tùy biến.

~~~java
import java.util.Objects;

// Đoạn minh họa; Transformer là interface đã định nghĩa ở trên.
public abstract class NormalizingTransformer implements Transformer {
    @Override
    public final String transform(String input) {
        String normalized = Objects.requireNonNull(input, "input").strip();
        return transformNormalized(normalized);
    }

    protected abstract String transformNormalized(String normalized);
}
~~~

Phương thức **transform** được đánh dấu **final**, nên subclass chỉ thay đổi bước **transformNormalized**, không thể bỏ qua bước kiểm tra null và strip do lớp nền quản lý. Lớp nền có thể dùng constructor để kiểm tra các phụ thuộc hoặc trạng thái chung nếu thực sự cần.

Đổi lại, Java chỉ cho phép **extends một class**. Provider đã kế thừa class khác không thể kế thừa lớp nền này. API protected và constructor của abstract class cũng trở thành bề mặt tương thích mà người viết thư viện phải duy trì.

Vì vậy, nếu dùng lớp nền, hãy ưu tiên cho nó **implements interface công khai**, còn host nhận **interface**. Để plugin được phép triển khai trực tiếp interface mà không kế thừa lớp nền; chỉ đặt quy tắc vào lớp nền khi đó là quy tắc của *họ triển khai dùng lớp nền*. Nếu quy tắc bắt buộc với **mọi** provider, phải thể hiện trong hợp đồng và kiểm tra ở ranh giới host, thay vì giả định mọi provider đều kế thừa một class.

**Không cần abstract class** nếu chỉ chia sẻ vài utility không trạng thái: một helper/service được truyền vào bằng composition thường ít ràng buộc hơn kế thừa.

## 5. Khi nào chọn factory?

Factory giải quyết câu hỏi: “Từ tên provider, cấu hình và phụ thuộc hiện có, lấy được đối tượng triển khai bằng cách nào?”. Nó hữu ích khi:

- Cần chọn triển khai theo cấu hình, môi trường, feature flag hoặc khả năng hệ thống.
- Constructor của các provider khác nhau, có bước validate, khởi tạo phụ thuộc hoặc quản lý tài nguyên.
- Host không nên biết tên class cụ thể và các chi tiết tạo plugin.
- Cần quy định rõ đối tượng mới cho mỗi yêu cầu, một đối tượng cho mỗi phiên, hay cache một đối tượng dùng chung.

Một factory thường trả về **interface**, ví dụ:

~~~java
import java.util.Map;

// Đoạn minh họa; Transformer được định nghĩa ở trên.
public interface TransformerFactory {
    Transformer create(String id, Map<String, String> options);
}
~~~

Interface là **kiểu hợp đồng của sản phẩm**; factory là **cách có được sản phẩm**. Hai khái niệm bổ sung nhau. Factory cũng có thể được mô tả bằng interface để thay thế cách đăng ký/khám phá provider.

Factory **không mặc định cần thiết**: nếu chỉ có một class đơn giản, constructor rõ ràng và không có chính sách lựa chọn hoặc vòng đời, gọi constructor hoặc để dependency-injection container tạo đối tượng có thể đủ. Cũng không nên tạo factory chỉ để đổi tên thao tác new mà không tạo ra ranh giới trừu tượng có ích.

Trong hệ thống thực tế, hãy cân nhắc cấu hình kiểu rõ ràng thay vì Map chuỗi; Map chỉ giúp ví dụ bên dưới ngắn gọn và chạy độc lập.

## 6. Ví dụ hoàn chỉnh: phối hợp cả ba

Ví dụ Java 17 sau chứa trong **một tệp ExtensionChoiceDemo.java**. Interface Transformer là hợp đồng host; NormalizingTransformer là lớp nền **tùy chọn**; UppercaseTransformer kế thừa lớp nền; PrefixTransformer triển khai trực tiếp interface; factory tạo cả hai và trả về cùng kiểu Transformer.

~~~java
import java.util.Locale;
import java.util.Map;
import java.util.Objects;

public class ExtensionChoiceDemo {
    @FunctionalInterface
    public interface Transformer {
        String transform(String input);
    }

    public static abstract class NormalizingTransformer implements Transformer {
        @Override
        public final String transform(String input) {
            String normalized = Objects.requireNonNull(input, "input").strip();
            return transformNormalized(normalized);
        }

        protected abstract String transformNormalized(String normalized);
    }

    public static final class UppercaseTransformer extends NormalizingTransformer {
        @Override
        protected String transformNormalized(String normalized) {
            return normalized.toUpperCase(Locale.ROOT);
        }
    }

    public static final class PrefixTransformer implements Transformer {
        private final String prefix;

        public PrefixTransformer(String prefix) {
            this.prefix = Objects.requireNonNull(prefix, "prefix");
        }

        @Override
        public String transform(String input) {
            return prefix + Objects.requireNonNull(input, "input");
        }
    }

    public interface TransformerFactory {
        Transformer create(String id, Map<String, String> options);
    }

    public static final class BuiltinTransformerFactory implements TransformerFactory {
        @Override
        public Transformer create(String id, Map<String, String> options) {
            Objects.requireNonNull(options, "options");
            return switch (Objects.requireNonNull(id, "id")) {
                case "upper" -> new UppercaseTransformer();
                case "prefix" -> new PrefixTransformer(
                        Objects.requireNonNull(options.get("prefix"), "missing prefix option"));
                default -> throw new IllegalArgumentException("Unknown transformer: " + id);
            };
        }
    }

    public static void main(String[] args) {
        TransformerFactory factory = new BuiltinTransformerFactory();

        Transformer first = factory.create("upper", Map.of());
        Transformer second = factory.create("prefix", Map.of("prefix", ">> "));

        System.out.println(first.transform("  java  "));
        System.out.println(second.transform("plugin"));
    }
}
~~~

Biên dịch và chạy (cần JDK 17 trở lên):

~~~bash
javac -encoding UTF-8 ExtensionChoiceDemo.java
java ExtensionChoiceDemo
~~~

Kết quả chuẩn:

~~~text
JAVA
>> plugin
~~~

Giải thích:

1. **first** nhận triển khai UppercaseTransformer. Lớp nền kiểm tra null, bỏ khoảng trắng đầu/cuối bằng String.strip rồi uppercase với Locale.ROOT, nên đầu ra là “JAVA”.
2. **second** nhận PrefixTransformer, không kế thừa NormalizingTransformer. Nó ghép prefix với input giữ nguyên, nên đầu ra là “>> plugin”.
3. Host chỉ thao tác với **TransformerFactory** và **Transformer**. Host không cần downcast và không cần gọi constructor của hai provider.
4. Factory ở đây dùng **switch cố định** để dễ chạy độc lập. Nó phù hợp khi danh sách provider do ứng dụng kiểm soát; nếu muốn JAR ngoài đăng ký provider mà không sửa switch, cần thay phần tìm provider bằng registry, DI hoặc ServiceLoader.
5. Lớp nền là tùy chọn: **strip không phải cam kết chung** của mọi Transformer. Hợp đồng chung chỉ đảm bảo đầu vào/đầu ra khác null và hành vi transform theo từng triển khai. Muốn host luôn nhận đầu vào đã chuẩn hóa, nên chuẩn hóa tại host hoặc ghi rõ và kiểm thử nghĩa vụ đó cho mọi plugin.

Trong dự án thật, tách interface công khai ra package API, đặt các provider ở module triển khai, và đặt factory/registry ở lớp tích hợp. Các kiểu nested trong ví dụ chỉ để chạy gọn trong một tệp.

## 7. Nếu provider đến từ JAR/module bên ngoài

Khi “mở rộng” nghĩa là **thêm provider mới sau khi host được biên dịch**, cần thêm **cơ chế khám phá (discovery)** ngoài interface/abstract class. Java cung cấp **ServiceLoader**, hoặc ứng dụng có thể dùng DI container hay registry riêng.

Một thiết kế thường dùng **provider factory** thay vì đăng ký trực tiếp đối tượng Transformer cần cấu hình:

~~~java
import java.util.Map;

// Mảnh API minh họa trong module SPI; Transformer là kiểu hợp đồng.
public interface TransformerProvider {
    String id();
    Transformer create(Map<String, String> options);
}
~~~

Host có thể dùng ServiceLoader để tìm các TransformerProvider được đăng ký, chọn provider theo id rồi gọi create. Với provider trên classpath, cơ chế service file sử dụng đường dẫn **META-INF/services/tên.đầy.đủ.của.TransformerProvider**, trong đó liệt kê tên lớp triển khai đầy đủ; provider phải đáp ứng các điều kiện khởi tạo của ServiceLoader, thường là một lớp công khai có constructor không tham số. Với Java Platform Module System, module tiêu thụ khai báo **uses**, module provider khai báo **provides ... with ...** và tuân thủ quy tắc provider của JPMS.

Khi chuyển từ switch sang registry, cần xử lý thêm **id trùng**, provider không có, cấu hình thiếu, lỗi khởi tạo, và chính sách vòng đời. Có thể khởi tạo provider một lần nhưng vẫn tạo **Transformer mới** cho mỗi phiên nếu implementation có trạng thái thay đổi. Khởi tạo một instance dùng chung chỉ khi hợp đồng xác nhận an toàn cho truy cập đồng thời và tương thích với vòng đời.

**ServiceLoader chỉ là cơ chế phát hiện/khởi tạo provider**, không phải hệ thống sandbox, hot-swap hoặc unload plugin tự động. Nếu cần nạp gỡ JAR, cô lập classloader/module layer, quản lý phiên bản thư viện và giải phóng tài nguyên, phải thiết kế các trách nhiệm đó riêng.

## 8. Kiểm tra độ bền của hợp đồng mở rộng

Một điểm mở rộng tốt cần mô tả rõ hơn chữ ký phương thức:

| Nội dung hợp đồng | Câu hỏi phải trả lời |
|---|---|
| Input/output | Có cho phép null, dữ liệu rỗng, kết quả null hoặc biến đổi input không? |
| Lỗi | Exception nào do plugin ném, host xử lý hay bao bọc thế nào? |
| Thread safety | Một instance được gọi đồng thời không? Provider có được lưu trạng thái phiên không? |
| Vòng đời | Ai tạo, ai đóng, khi nào đóng? Có cần AutoCloseable hay hook shutdown không? |
| Tài nguyên | Ai sở hữu stream, executor, connection và trách nhiệm cleanup? |
| Thời gian chạy | Plugin có thể chạy chậm, block hoặc gọi lại host không? Cần timeout/giới hạn nào? |
| Tương thích | API tối thiểu, phiên bản nào được hỗ trợ và có kiểm thử compatibility không? |
| Tính độc lập | Hợp đồng có lộ class implementation/framework cụ thể khiến provider khó thay thế không? |

**Tiến hóa API cần thận trọng:**

- **Thêm abstract method vào interface** làm implementation cũ không đáp ứng hợp đồng mới: mã nguồn cũ phải được cập nhật; nếu binary cũ vẫn được tải, lời gọi phương thức thiếu có thể dẫn tới AbstractMethodError.
- **Thêm default method** thường giảm nhu cầu cập nhật implementation, nhưng vẫn có thể tạo xung đột phương thức hoặc mang ngữ nghĩa sai. Không xem default là bảo đảm tương thích trong mọi trường hợp.
- **Thay đổi constructor, protected hook hoặc thêm abstract method vào abstract class** có thể phá subclass ngoài thư viện. Vì vậy lớp nền nên nhỏ, ổn định và chỉ mang trách nhiệm có thật.
- **Đổi tên id provider, key cấu hình hoặc hành vi lỗi của factory** cũng là thay đổi hợp đồng, dù chữ ký Java không đổi.
- Tách khả năng mới thành interface bổ sung khi phù hợp hơn việc buộc tất cả provider cũ phải triển khai phương thức mới.

Để kiểm tra tương thích, tạo một **contract test suite** chạy trên mọi implementation: kiểm tra null, kết quả, lỗi, gọi lặp, gọi đồng thời (nếu được cam kết), lifecycle và hành vi biên. Test factory riêng cho id hợp lệ, id lạ, cấu hình sai và scope của đối tượng. Trong test host, có thể thay Transformer bằng lambda trả kết quả cố định để chứng minh host thực sự phụ thuộc vào interface.

## 9. Những lựa chọn dễ sai và cách sửa

**Ép tất cả plugin kế thừa một BasePlugin lớn.** Điều này khóa đường kế thừa, buộc provider phụ thuộc vào những hook không cần thiết và làm tiến hóa API khó khăn. Tách **interface công khai nhỏ**, chỉ giữ một abstract base tùy chọn cho họ triển khai có quy trình chung.

**Dùng abstract class chỉ để tái sử dụng vài dòng.** Nếu logic không cần ràng buộc một thuật toán, hãy chuyển thành helper/service và composition. Kế thừa chỉ nên dùng khi quan hệ “là một dạng của” thực sự có ý nghĩa và các điểm móc có giới hạn rõ.

**Host switch trên kiểu cụ thể, downcast provider rồi gọi phương thức riêng.** Khi đó hợp đồng Transformer không đủ cho nhu cầu host. Bổ sung capability interface phù hợp hoặc thiết kế lại SPI; giữ factory/registry ở ranh giới tạo đối tượng.

**Cho factory kiêm luôn toàn bộ thuật toán xử lý.** Factory nên tập trung vào lựa chọn, validate cấu hình và xây dựng đối tượng. Hành vi nghiệp vụ nằm ở implementation tương ứng; tránh một factory khổng lồ chứa mã cho mọi plugin.

**Chia sẻ singleton stateful mà không xác định thread safety.** Nếu Transformer giữ bộ đếm, buffer hoặc context theo request, việc dùng chung có thể gây race condition và rò rỉ dữ liệu giữa yêu cầu. Factory phải đưa ra scope rõ ràng; provider phải có hợp đồng concurrency phù hợp.

**Tin rằng ServiceLoader tự giải quyết an toàn và tương thích.** Discovery không xác thực mã bên thứ ba, không tự giới hạn quyền truy cập và không bảo đảm tương thích nhị phân. Cần kiểm soát provider được phép tải, API version, phụ thuộc và cơ chế cách ly nếu môi trường yêu cầu.

**Tạo quá nhiều tầng factory/abstract class khi chưa có nhu cầu.** Với hai chiến lược đơn giản, interface cùng constructor/DI có thể đủ. Bổ sung factory khi xuất hiện một chính sách chọn/khởi tạo có lý do cụ thể, và bổ sung abstract class khi thấy quy trình dùng chung ổn định.

## 10. Cách ra quyết định cho một điểm mở rộng mới

Đi theo thứ tự sau:

1. **Viết hợp đồng quan sát được:** host gọi phương thức nào, input/output, lỗi, đồng thời, tài nguyên và vòng đời ra sao? Nếu có nhiều implementation không cùng quan hệ kế thừa, mô tả bằng **interface**.
2. **Xác định bất biến thực sự dùng chung:** có một chuỗi bước mà subclass chỉ được thay một vài hook hay không? Nếu có, xây **abstract class implements interface**, dùng final cho template method cần được bảo vệ. Nếu chỉ chia sẻ tiện ích, ưu tiên composition.
3. **Quyết định người tạo đối tượng:** host biết kiểu cụ thể và việc new luôn đơn giản hay cần lựa chọn động, tiêm dependency, cấu hình hoặc quản lý scope? Trường hợp sau dùng **factory trả về interface**.
4. **Xác định cách tìm provider:** nếu tập provider đóng, switch/DI có thể đủ; nếu JAR mới phải tự đăng ký, thiết kế provider registry hoặc ServiceLoader bên sau factory.
5. **Thử một provider không dùng lớp nền và một fake cho host:** nếu host vẫn chạy qua interface mà không cần downcast hay biết implementation, ranh giới mở rộng đang được giữ đúng.
6. **Thử thay đổi phiên bản API:** một provider viết ở phiên bản cũ còn biên dịch/chạy được không, và lỗi không tương thích được phát hiện ở đâu?

### Ba tình huống điển hình

| Tình huống | Lựa chọn khuyến nghị | Lý do |
|---|---|---|
| Cho bên thứ ba bổ sung thuật toán xử lý văn bản độc lập | **Interface** làm SPI | Không ép provider theo superclass; host chỉ gọi hợp đồng |
| Nhiều bộ parser cùng bắt buộc theo chuỗi kiểm tra → đọc → parse → cleanup | **Interface + abstract class tùy chọn hoặc bắt buộc trong họ parser** | Template method kiểm soát trình tự chung và chỉ mở các hook cần thiết |
| Người dùng chọn provider theo tên; từng provider cần token, cấu hình, kết nối hoặc scope riêng | **Interface + factory**, có thể thêm registry/ServiceLoader | Tách thuật toán khỏi việc tạo, chọn, cấu hình và quản lý vòng đời |

**Tiêu chuẩn của một thiết kế tốt:** host biết **hợp đồng và cách yêu cầu một provider**, mỗi provider chỉ cần biết **phần nghĩa vụ của nó**, còn chi tiết khởi tạo và triển khai được giữ sau ranh giới trừu tượng.