# Phân biệt thứ tự khám phá với thứ tự ưu tiên do ứng dụng quy định

## 1. Hai khái niệm khác nhau

Trong Java, ServiceLoader tìm các implementation (provider) của một service interface. Khi duyệt iterator, ta quan sát một thứ tự provider. Đây là **thứ tự khám phá**, chịu ảnh hưởng bởi metadata, classloader, module và cách đóng gói. Nó không phải một chính sách ưu tiên nghiệp vụ.

**Ưu tiên của ứng dụng** là quy tắc do host quy định để chọn provider phù hợp: điều kiện hỗ trợ, cấu hình cho phép, mức priority, cách phá hòa và hành vi khi không có ứng viên.

Ví dụ, một ứng dụng có ba exporter: DefaultExporter, CsvExporter và FastCsvExporter. Provider xuất hiện đầu tiên không nhất thiết là exporter tốt nhất cho yêu cầu CSV. Nếu ứng dụng dùng ServiceLoader.iterator().next() làm “mặc định”, thay đổi dependency hoặc merge JAR có thể thay đổi lựa chọn mà không đổi mã nghiệp vụ.

Cần tách hai câu hỏi:

1. **Ai đang sẵn có?** Do ServiceLoader và môi trường runtime trả lời.
2. **Ai được chọn cho yêu cầu này?** Do chính sách của ứng dụng trả lời.

## 2. Nguồn gốc của thứ tự khám phá

### Classpath và META-INF/services

Trên classpath, provider có thể được khai báo trong tệp:

\`\`\`text
META-INF/services/com.example.spi.Exporter
\`\`\`

Nội dung là các tên binary của provider, mỗi dòng một tên:

\`\`\`text
com.example.plugins.BasicExporter
com.example.plugins.FastExporter
\`\`\`

Trong một service-configuration file, thứ tự dòng là thứ tự khai báo. Nhưng một ứng dụng có thể nhìn thấy nhiều file cùng tên từ nhiều JAR. Thứ tự mà classloader tìm thấy các resources này phụ thuộc cấu hình nạp, các JAR và cơ chế triển khai. Khi tạo shaded/uber JAR, việc hợp nhất service descriptors cũng có thể ảnh hưởng thứ tự hiển thị.

**Không dùng vị trí trong descriptor hoặc classpath làm priority** trừ khi đó là một hợp đồng triển khai được kiểm soát chủ động, có quy định và test rõ. Trong hệ plugin mở rộng, chính sách chọn độc lập với discovery order dễ bảo trì hơn.

### Named modules

Với Java Platform Module System (JPMS), named module có thể đăng ký provider bằng khai báo provides ... with ... trong module-info.java. Thứ tự tìm provider khi duyệt các module không phải một thang ưu tiên nghiệp vụ. Cần kiểm thử trong module layer triển khai thực tế thay vì giả định rằng thứ tự module path phản ánh priority.

### Cache và reload

ServiceLoader có thể cache provider instance khi duyệt iterator; reload() loại bỏ cache này và các iterator/stream cũ không còn hợp lệ. Dù một lần duyệt sau có thể thấy thứ tự tương tự, caching/reload không định nghĩa chính sách ưu tiên. Muốn đổi priority phải thay chính sách hoặc dữ liệu cấu hình của ứng dụng.

## 3. Thiết kế bộ chọn quyết định được

Một chiến lược minh bạch gồm bốn bước:

1. Khám phá tập provider mà host có quyền sử dụng.
2. **Lọc** ứng viên theo khả năng hỗ trợ tác vụ và điều kiện cho phép.
3. **Xếp hạng** ứng viên hợp lệ theo mức ưu tiên mà host định nghĩa.
4. **Phá hòa** bằng quy tắc ổn định hoặc báo lỗi khi mơ hồ.

Ví dụ: priority càng cao càng ưu tiên; khi bằng priority, ID của provider được so sánh theo thứ tự chữ cái tăng dần; provider ID phải duy nhất. Khi không có provider hợp lệ, hệ thống ném lỗi với thông điệp rõ.

Bảng ví dụ:

| Provider | Hỗ trợ text | Priority | Chọn cho text? |
| --- | --- | ---: | --- |
| basic | Có | 10 | Không, vì thấp hơn |
| smart | Có | 100 | Có |
| image | Không | 200 | Không, vì không hỗ trợ |

Một provider không hỗ trợ tác vụ phải bị loại **trước khi so priority**, dù số priority cao nhất.

## 4. Ví dụ Java 17+ chạy được

Ví dụ tách service API, hai implementation và selector. Cố ý đặt provider ưu tiên thấp trước trong META-INF/services để chứng minh việc chọn không phụ thuộc thứ tự khám phá.

Cấu trúc thư mục:

\`\`\`text
sample/
  src/
    demo/spi/Formatter.java
    demo/plugins/BasicFormatter.java
    demo/plugins/SmartFormatter.java
    demo/Main.java
  resources/
    META-INF/services/demo.spi.Formatter
\`\`\`

**src/demo/spi/Formatter.java**

\`\`\`java
package demo.spi;

public interface Formatter {
    String id();
    int priority();
    boolean supports(String requestedFormat);
    String format(String input);
}
\`\`\`

**src/demo/plugins/BasicFormatter.java**

\`\`\`java
package demo.plugins;

import demo.spi.Formatter;

public final class BasicFormatter implements Formatter {
    public BasicFormatter() {}

    public String id() { return "basic"; }
    public int priority() { return 10; }
    public boolean supports(String requestedFormat) {
        return "text".equals(requestedFormat);
    }
    public String format(String input) {
        return "basic:" + input;
    }
}
\`\`\`

**src/demo/plugins/SmartFormatter.java**

\`\`\`java
package demo.plugins;

import demo.spi.Formatter;

public final class SmartFormatter implements Formatter {
    public SmartFormatter() {}

    public String id() { return "smart"; }
    public int priority() { return 100; }
    public boolean supports(String requestedFormat) {
        return "text".equals(requestedFormat);
    }
    public String format(String input) {
        return "smart:" + input;
    }
}
\`\`\`

**resources/META-INF/services/demo.spi.Formatter**

\`\`\`text
demo.plugins.BasicFormatter
demo.plugins.SmartFormatter
\`\`\`

**src/demo/Main.java**

\`\`\`java
package demo;

import demo.spi.Formatter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.NoSuchElementException;
import java.util.ServiceLoader;
import java.util.Set;

public final class Main {
    private static final Comparator<Formatter> RANKING =
            Comparator.comparingInt(Formatter::priority)
                    .reversed()
                    .thenComparing(Formatter::id);

    static Formatter choose(Iterable<Formatter> providers, String requested) {
        List<Formatter> eligible = new ArrayList<>();
        Set<String> ids = new HashSet<>();

        for (Formatter candidate : providers) {
            if (!ids.add(candidate.id())) {
                throw new IllegalStateException(
                        "Duplicate provider ID: " + candidate.id());
            }
            if (candidate.supports(requested)) {
                eligible.add(candidate);
            }
        }

        return eligible.stream()
                .min(RANKING)
                .orElseThrow(() -> new NoSuchElementException(
                        "No provider for " + requested));
    }

    public static void main(String[] args) {
        List<Formatter> providers = new ArrayList<>();
        for (Formatter candidate : ServiceLoader.load(Formatter.class)) {
            providers.add(candidate);
        }

        System.out.println("Discovery order:");
        for (Formatter candidate : providers) {
            System.out.println(candidate.id() + " priority="
                    + candidate.priority());
        }

        Formatter selected = choose(providers, "text");
        System.out.println("Selected: " + selected.id());
        System.out.println("Value: " + selected.format("hello"));

        Collections.reverse(providers);
        System.out.println("Selected after reverse: "
                + choose(providers, "text").id());
    }
}
\`\`\`

Biên dịch và chạy từ thư mục sample trên bash:

\`\`\`bash
mkdir -p out
javac -d out src/demo/spi/Formatter.java src/demo/plugins/BasicFormatter.java src/demo/plugins/SmartFormatter.java src/demo/Main.java
cp -R resources/. out/
java -cp out demo.Main
\`\`\`

Output với metadata trong ví dụ:

\`\`\`text
Discovery order:
basic priority=10
smart priority=100
Selected: smart
Value: smart:hello
Selected after reverse: smart
\`\`\`

Chính sách của ví dụ xếp hạng theo priority giảm dần và ID tăng dần. Java Comparator.min(RANKING) chọn phần tử đứng đầu theo comparator đó. Số cao hơn thắng. Khi đảo thứ tự danh sách input, kết quả không đổi.

Trên Windows, thay mkdir -p và cp -R bằng lệnh PowerShell tương ứng, hoặc dùng git bash; javac và java vẫn chạy như thường.

**Chú ý:** các implementation không tự quyết định chính sách; chúng cung cấp dữ liệu priority qua interface, còn host quyết định cách đọc và so sánh. Một host khác có thể dùng file cấu hình để override.

## 5. Phân biệt các cách chọn sai và đúng

### Sai: chọn provider đầu tiên

\`\`\`java
Formatter selected = ServiceLoader.load(Formatter.class)
        .iterator()
        .next();
\`\`\`

Đoạn này có thể ném NoSuchElementException nếu không có provider, và nếu có thì nó lấy phần tử đầu tiên theo encounter order. Không kiểm tra supports(), không dùng priority() và không có tie-break.

Tương tự, dùng stream().findFirst() ngay trên stream provider chỉ chọn theo encounter order đang có.

### Đúng: lọc rồi xếp hạng theo policy

\`\`\`java
Formatter selected = ServiceLoader.load(Formatter.class)
        .stream()
        .map(ServiceLoader.Provider::get)
        .filter(provider -> provider.supports("text"))
        .min(Comparator.comparingInt(Formatter::priority)
                .reversed()
                .thenComparing(Formatter::id))
        .orElseThrow();
\`\`\`

Đây là đoạn code đặt trong method với các import thích hợp; nếu cần kiểm tra ID trùng, hãy thêm bước validation như method choose() trong ví dụ hoàn chỉnh. Stream tạo instance để đọc priority() và supports(); việc này có chi phí khởi tạo cần cân nhắc.

### Nếu priority bằng nhau

Nếu comparator chỉ so priority, hai provider cùng mức có thể bị chọn theo thứ tự đầu vào. Khi cần tính xác định, ứng dụng phải thêm tie-break ổn định, ví dụ ID duy nhất. Nếu ID trùng, nên fail fast để tránh định danh mơ hồ.

Nếu ứng dụng muốn xem việc “hai plugin đều ưu tiên số 100” là lỗi cấu hình, hãy validate xung đột thay vì tự động chọn theo ID. Đó cũng là một policy rõ ràng.

## 6. Chính sách do host sở hữu

Không phải lúc nào nên để mỗi provider tự quyết định priority. Với plugin bên thứ ba, một implementation có thể tự đặt priority rất cao để luôn thắng. Có thể để host lưu cấu hình:

\`\`\`yaml
providers:
  preferred: smart
  fallback:
    - basic
\`\`\`

Đây là schema minh họa, ứng dụng cần tự định nghĩa parser và validation. Cần quyết định rõ: preferred có bắt buộc có mặt? Nếu plugin preferred không hỗ trợ yêu cầu thì fallback hay báo lỗi? Nếu fallback gồm ID không tồn tại thì có chấp nhận không?

Một chính sách phổ biến là: ứng dụng xác minh eligibility trước, chọn provider được cấu hình nếu hợp lệ; nếu không có lựa chọn bắt buộc thì dùng priority; khi không có ứng viên, báo lỗi. Các quyết định thuộc hợp đồng ứng dụng, không được suy ra từ ServiceLoader.

## 7. Ưu tiên không đồng nghĩa khởi tạo trước

ServiceLoader khám phá provider theo nhu cầu. Khi dùng iterator để duyệt tất cả candidate, việc lấy instance có thể khởi tạo nhiều provider, dù chỉ một provider được chọn.

Nếu khởi tạo rất tốn kém, cân nhắc:

- Dùng metadata tĩnh trong descriptor/config registry do host quản lý.
- Dùng ServiceLoader.stream() và Provider.type() để lọc bằng thông tin type/annotation trước khi gọi Provider.get().
- Phân biệt rõ plugin metadata với plugin runtime instance.

Tuy nhiên Provider.type() không tự cung cấp priority() nếu priority là method của instance. Với named modules dùng provider factory method, type() có thể cho biết return type của factory method. Không áp dụng giả định về classpath provider cho mọi module.

Ngoài ra ServiceLoader không phải thread-safe; quản lý vòng đời loader/provider và đồng bộ nếu có nhiều thread truy cập.

## 8. Kiểm thử để chứng minh kết quả ổn định

Các case nên được tự động hóa:

| Case | Kỳ vọng |
| --- | --- |
| basic priority 10 xuất hiện trước smart priority 100 | smart thắng |
| Đảo thứ tự discovery | smart vẫn thắng |
| priority cao nhưng supports() trả false | Provider phù hợp khác thắng |
| Hai priority bằng nhau, ID khác nhau | Tie-break hoạt động |
| Hai ID trùng | Báo lỗi |
| Không có provider phù hợp | Báo lỗi rõ ràng |
| Cấu hình preferred không tồn tại | Fail fast hoặc fallback theo policy |
| JAR đã relocate/shade | ServiceLoader vẫn khám phá đầy đủ provider |

Một selector nhận Iterable/Collection sẽ dễ test bằng dữ liệu tự tạo hơn selector tự nạp classpath. Sau unit test policy, nên chạy integration test trên artifact đóng gói thật để xác minh service descriptors, provider class và classloader.

Nếu có plugin phiên bản mới, hãy giữ test hoán đổi danh sách và test tie-break. Bước này bảo vệ ứng dụng khỏi việc dependency order thay đổi ngầm.

## 9. Lỗi thường gặp

| Lỗi | Hậu quả | Giải pháp |
| --- | --- | --- |
| Dùng iterator().next() làm policy | Chọn theo thứ tự discovery | Lọc và xếp hạng |
| Dùng findFirst() trước filter/sort | Có thể chọn sai provider | Áp dụng điều kiện và ranking trước |
| Không phá hòa | Phụ thuộc encounter order khi bằng điểm | Tie-break hoặc báo lỗi |
| Không kiểm tra ID trùng | Provider mơ hồ | Validate ID |
| Priority cao dù không supports | Chọn sai khả năng | Filter eligibility trước |
| Chỉ kiểm thử bằng IDE | Bỏ sót lỗi metadata JAR | Test artifact cuối |
| Để plugin tự đặt priority không kiểm soát | Host khó giữ chính sách ổn định | Giới hạn priority hoặc cấu hình host |
| Bỏ qua chi phí constructor khi ranking | Khởi tạo quá nhiều plugin | Dùng metadata hoặc thiết kế discovery phù hợp |

## 10. Checklist triển khai

- [ ] Xác định rõ service interface và tập provider hợp lệ.
- [ ] Định nghĩa policy priority và eligibility riêng với discovery.
- [ ] Thêm tie-break hoặc lỗi mơ hồ cho priority bằng nhau.
- [ ] Quy định ID duy nhất, có validation.
- [ ] Test kết quả khi đảo thứ tự danh sách.
- [ ] Test policy fallback và provider không hỗ trợ.
- [ ] Test artifact JAR cuối với ServiceLoader.
- [ ] Không giả định thứ tự classpath/module path là thứ tự ưu tiên.

**Ghi nhớ:** ServiceLoader cho biết provider nào được tìm thấy; ứng dụng chịu trách nhiệm chọn provider nào được sử dụng. Một policy quyết định được, được kiểm thử với mọi thứ tự discovery, giúp plugin hoạt động ổn định khi build và môi trường triển khai thay đổi.
