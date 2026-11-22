# Đổi static thành instance hoặc thay đổi class thành interface

## 1. Vì sao những thay đổi này ảnh hưởng đến tương thích nhị phân?

Trong Java, một thư viện không chỉ được sử dụng thông qua mã nguồn. Sau khi biên dịch, mã nguồn của ứng dụng khách trở thành các class file chứa tham chiếu đến kiểu, phương thức, field và các chỉ dẫn gọi tương ứng. Khi thư viện được nâng phiên bản, JVM phải liên kết các tham chiếu đã được biên dịch đó với định nghĩa mới.

Tương thích nhị phân (binary compatibility) mô tả khả năng các class file đã biên dịch trước đó tiếp tục liên kết và chạy với phiên bản mới của thư viện mà không cần biên dịch lại. Một thay đổi có thể trông nhỏ trong mã nguồn nhưng làm thay đổi cách JVM diễn giải tham chiếu trong bytecode.

Hai thay đổi cần đặc biệt chú ý trong migration Java là:

- Chuyển một phương thức từ static thành instance hoặc từ instance thành static.
- Chuyển một kiểu đã khai báo là class thành interface hoặc ngược lại.

Các thay đổi này ảnh hưởng đến loại thao tác mà bytecode cũ sử dụng. Nếu bytecode cũ kỳ vọng một phương thức static nhưng runtime cung cấp phương thức instance, hoặc bytecode kỳ vọng một class nhưng runtime cung cấp interface, quá trình liên kết có thể thất bại với IncompatibleClassChangeError.

Vì vậy, không nên đánh giá tương thích chỉ bằng cách xem mã nguồn mới có biên dịch hay không. Cần xem xét cả client đã biên dịch từ trước, bytecode, cấu trúc kiểu và hành vi khi chạy với thư viện mới.

## 2. Phân biệt source compatibility, binary compatibility và behavioral compatibility

Ba khái niệm này trả lời ba câu hỏi khác nhau:

| Loại tương thích | Câu hỏi | Cách kiểm tra |
|---|---|---|
| Source compatibility | Mã nguồn client cũ có thể biên dịch lại với API mới không? | Biên dịch lại các client hoặc module phụ thuộc. |
| Binary compatibility | Class file client cũ có thể liên kết với thư viện mới mà không biên dịch lại không? | Chạy binary cũ với thư viện mới; dùng công cụ kiểm tra tương thích nhị phân. |
| Behavioral compatibility | Client sau khi liên kết có còn nhận được hành vi và kết quả như mong đợi không? | Unit test, integration test, contract test và kiểm thử runtime. |

Một thay đổi có thể vẫn giữ nguyên tên phương thức và tham số nhưng phá vỡ binary compatibility. Ngược lại, một thư viện có thể giữ được binary compatibility nhưng thay đổi kết quả xử lý, thứ tự gọi callback hoặc cách đồng bộ khiến behavioral compatibility bị ảnh hưởng.

Trong tài liệu migration, cần ghi rõ loại tương thích đang được đánh giá. “Build thành công” thường chỉ chứng minh một phần source/build compatibility; nó không tự chứng minh các binary client đã phát hành trước đó vẫn chạy được.

## 3. Đổi phương thức static thành instance

### 3.1. Khác biệt về cách gọi

Phương thức static thuộc về lớp. Nó được gọi thông qua tên lớp và không có receiver object. Phương thức instance được gọi trên một đối tượng cụ thể và có receiver để JVM thực hiện dispatch.

Ví dụ API ban đầu:

~~~java
package com.example.pricing;

public class PriceCalculator {
    public static long calculate(long amount, int percent) {
        return amount * percent / 100;
    }
}
~~~

Client sử dụng API static:

~~~java
long result = PriceCalculator.calculate(10_000, 5);
~~~

Ở phiên bản thư viện mới, nhóm phát triển muốn chuyển phép tính thành hành vi của một đối tượng:

~~~java
package com.example.pricing;

public class PriceCalculator {
    public long calculate(long amount, int percent) {
        return amount * percent / 100;
    }
}
~~~

Mã nguồn client cần thay đổi để tạo hoặc nhận một đối tượng:

~~~java
PriceCalculator calculator = new PriceCalculator();
long result = calculator.calculate(10_000, 5);
~~~

Ở mức ngôn ngữ, đây là thay đổi cách sử dụng API. Ở mức bytecode, thay đổi này còn làm thay đổi opcode được dùng để gọi phương thức.

### 3.2. Bytecode sử dụng opcode khác nhau

Khi biên dịch một lời gọi static, compiler tạo chỉ dẫn invokestatic. Khi gọi phương thức instance của class, compiler thường tạo invokevirtual; với phương thức instance được khai báo qua interface, compiler sử dụng invokeinterface. Một số trường hợp đặc biệt như constructor, phương thức private hoặc lời gọi super sử dụng invokespecial.

Ví dụ minh họa:

~~~text
Client được biên dịch với API static:

  invokestatic
    com/example/pricing/PriceCalculator.calculate:(JI)J

Client được biên dịch với API instance:

  invokevirtual
    com/example/pricing/PriceCalculator.calculate:(JI)J
~~~

Tên phương thức và descriptor tham số/giá trị trả về có thể giữ nguyên. Tuy nhiên, opcode trong client đã được biên dịch phản ánh cách gọi static hay instance. JVM kiểm tra tính nhất quán giữa loại invocation và phương thức thực tế được phân giải.

Nếu client cũ vẫn chứa invokestatic nhưng phiên bản thư viện mới khai báo phương thức đó là instance, JVM có thể ném IncompatibleClassChangeError khi đường đi thực thi liên kết đến lời gọi. Trường hợp ngược lại cũng gây lỗi: client cũ dùng invokevirtual hoặc invokeinterface nhưng thư viện mới cung cấp phương thức static.

Lỗi cụ thể xuất hiện khi nào phụ thuộc vào thời điểm JVM phân giải tham chiếu và đường code được thực thi. Không nên giả định mọi lỗi đều xuất hiện ngay khi tiến trình khởi động.

### 3.3. Tại sao giữ nguyên tên và chữ ký vẫn không đủ?

Descriptor của phương thức trong class file chủ yếu mô tả tên, kiểu tham số và kiểu trả về. Tính static không được thể hiện như một phần của descriptor theo cách giúp JVM tự chuyển đổi lời gọi cũ thành lời gọi mới. Thông tin invocation nằm trong chỉ dẫn bytecode và loại tham chiếu phương thức.

Do đó, hai phiên bản sau không thể được xem là tương đương nhị phân chỉ vì cùng tên và cùng kiểu tham số:

~~~java
// Phiên bản A
public static Result execute(Request request) { ... }

// Phiên bản B
public Result execute(Request request) { ... }
~~~

Trong cùng một class, Java cũng không cho phép khai báo hai phương thức chỉ khác nhau ở static modifier nhưng có cùng signature. Vì vậy, không thể giữ phương thức static cũ và thêm một phương thức instance cùng tên/cùng tham số trong chính class đó để hỗ trợ cả hai kiểu gọi.

### 3.4. Tác động đến kế thừa và dispatch

Phương thức static không được override theo cơ chế đa hình của instance method. Một phương thức static cùng signature trong lớp con có thể che khuất (hide) phương thức static của lớp cha. Phương thức instance có thể được override và việc chọn implementation phụ thuộc vào kiểu thực tế của receiver.

Ví dụ:

~~~java
class BaseFormatter {
    static String format(String value) {
        return "base:" + value;
    }
}

class CustomFormatter extends BaseFormatter {
    static String format(String value) {
        return "custom:" + value;
    }
}
~~~

Đây là static method hiding. Nếu API được chuyển thành instance method, quan hệ giữa lớp cha và lớp con có thể trở thành overriding và dispatch theo object. Thay đổi đó có thể ảnh hưởng đến:

- Implementation nào được gọi khi sử dụng biến có kiểu khai báo là lớp cha.
- Các lớp con đã biên dịch trước đó.
- Annotation @Override và các khai báo trùng signature.
- Method reference, method handle, proxy hoặc code được sinh bởi framework.
- Vòng đời đối tượng và nơi lưu trạng thái cấu hình.

Static method cũng không có monitor riêng của object. Nếu phương thức cũ được khai báo synchronized static, khóa đồng bộ là monitor của Class; khi chuyển thành synchronized instance, khóa là monitor của từng object. Thay đổi này có thể làm thay đổi mức độ đồng bộ giữa các lời gọi, ngay cả khi phần thân phương thức giống nhau.

### 3.5. Tác động đến source code và API client

Sau khi chuyển static thành instance, các client cần thay đổi cách gọi và cách tạo dependency. Các lời gọi qua tên lớp sẽ không còn hợp lệ khi biên dịch lại. Client có thể cần dependency injection, factory hoặc cấu hình vòng đời đối tượng.

Các tình huống cần rà soát gồm:

- Gọi trực tiếp qua tên class.
- Gọi trong static initializer hoặc static method khác.
- Method reference dạng Type::method.
- Reflection tìm phương thức và gọi bằng Method.invoke.
- Method handle được tạo với REF_invokeStatic.
- Mã nguồn được sinh tự động hoặc được compile riêng trong module khác.

Với reflection, việc tìm thấy một Method cùng tên không đảm bảo cách gọi cũ vẫn đúng. Client có thể cần cập nhật cách lấy receiver và invocation. Với method handle, reference kind và loại lookup cũng cần được điều chỉnh.

## 4. Đổi phương thức instance thành static

Chiều thay đổi ngược lại cũng phá vỡ giả định của binary cũ.

Ví dụ phiên bản cũ:

~~~java
public class TokenValidator {
    public boolean isValid(String token) {
        return token != null && !token.isBlank();
    }
}
~~~

Client đã biên dịch:

~~~java
TokenValidator validator = new TokenValidator();
boolean valid = validator.isValid(token);
~~~

Phiên bản mới chuyển phương thức thành static:

~~~java
public class TokenValidator {
    public static boolean isValid(String token) {
        return token != null && !token.isBlank();
    }
}
~~~

Client mới có thể gọi:

~~~java
boolean valid = TokenValidator.isValid(token);
~~~

Client cũ vẫn mang invocation kiểu instance. Khi chạy với thư viện mới, JVM có thể ném IncompatibleClassChangeError do bytecode mong đợi một phương thức instance nhưng phương thức được phân giải là static.

Trong Java source, một static method có thể bị gọi qua biểu thức instance trong một số trường hợp, dù cách viết đó không được khuyến khích. Tuy nhiên, việc client source biên dịch lại được không chứng minh binary cũ tương thích. Compiler sẽ tạo bytecode mới theo định nghĩa hiện tại; binary đã phát hành vẫn giữ opcode cũ.

Ngoài ra, chuyển instance thành static làm mất receiver object. Nếu implementation trước đây dựa vào field, dependency, trạng thái hoặc override của subclass, cần thiết kế lại hành vi và đánh giá tác động đến test, concurrency và lifecycle.

## 5. Thay đổi một class thành interface

### 5.1. Class và interface có hợp đồng kiểu khác nhau

Class là một kiểu có thể định nghĩa constructor, trạng thái instance, implementation và quan hệ kế thừa một lớp cha. Interface định nghĩa một hợp đồng mà các class có thể triển khai; interface không có constructor và không thể được khởi tạo trực tiếp bằng new.

Ví dụ API ban đầu là class:

~~~java
package com.example.storage;

public class RecordStore {
    public Record find(String id) {
        // Implementation
        return null;
    }
}
~~~

Client có thể khởi tạo class:

~~~java
RecordStore store = new RecordStore();
Record record = store.find("A-100");
~~~

Nếu phiên bản thư viện mới thay cùng tên kiểu thành interface:

~~~java
package com.example.storage;

public interface RecordStore {
    Record find(String id);
}
~~~

Client mới không thể tiếp tục dùng new RecordStore(). Nó cần một implementation cụ thể hoặc một factory:

~~~java
RecordStore store = new DefaultRecordStore();
Record record = store.find("A-100");
~~~

Đây không chỉ là thay đổi cú pháp. Class file đã biên dịch trước đó chứa giả định rằng RecordStore là class. Khi runtime cung cấp interface cùng tên nhị phân, các thao tác cần class có thể không còn hợp lệ.

### 5.2. Thay đổi class thành interface

Các client cũ có thể chứa những cấu trúc sau:

- Lệnh new RecordStore() để khởi tạo đối tượng.
- Một lớp con khai báo extends RecordStore.
- Lời gọi phương thức instance thông qua invokevirtual.
- Tham chiếu đến constructor hoặc các thành phần chỉ có ý nghĩa trong class.

Khi RecordStore trở thành interface, JVM có thể phát hiện loại kiểu không khớp khi phân giải hoặc thực thi các tham chiếu cũ. Ví dụ, client cũ dùng new với một kiểu hiện là interface có thể gặp IncompatibleClassChangeError. Một lớp đã biên dịch với superclass là RecordStore cũng không thể tiếp tục coi interface mới là superclass.

Nếu một phương thức được gọi qua kiểu class cũ, bytecode có thể sử dụng invokevirtual. Khi kiểu runtime đã đổi thành interface, tham chiếu và opcode không còn khớp với loại kiểu được phân giải. JVM có thể ném IncompatibleClassChangeError.

### 5.3. Thay đổi interface thành class

Chiều ngược lại cũng không tương thích với binary cũ.

Giả sử phiên bản cũ khai báo:

~~~java
public interface EventHandler {
    void handle(Event event);
}
~~~

Client triển khai interface:

~~~java
public class AuditHandler implements EventHandler {
    @Override
    public void handle(Event event) {
        // Handle event
    }
}
~~~

Client đã biên dịch ghi nhận EventHandler là interface. Nếu thư viện mới thay cùng tên đó thành class, quan hệ implements trong binary cũ sẽ không còn hợp lệ. JVM có thể ném IncompatibleClassChangeError vì client mong đợi một interface nhưng runtime cung cấp class.

Các lời gọi instance method qua interface cũ thường sử dụng invokeinterface. Khi kiểu được phân giải thành class, giả định interface của bytecode cũ bị phá vỡ.

### 5.4. Khác biệt về cấu trúc và ngữ nghĩa

Khi đổi class thành interface hoặc ngược lại, cần rà soát các đặc điểm sau:

| Đặc điểm | Class | Interface |
|---|---|---|
| Khởi tạo | Có thể có constructor và dùng new nếu không abstract. | Không có constructor; không thể khởi tạo trực tiếp. |
| Kế thừa | Một class chỉ extends một class trực tiếp. | Một interface có thể extends nhiều interface. |
| Triển khai | Class có thể implements nhiều interface. | Class triển khai interface bằng implements. |
| Trạng thái instance | Có thể có field instance. | Không có field instance; field được khai báo trong interface là public static final. |
| Method implementation | Có thể có abstract và concrete method. | Có abstract, default, static và private method theo phiên bản Java hỗ trợ. |
| Static method | Được gọi qua tên class; có thể bị hide trong lớp con. | Được gọi qua tên interface và không được kế thừa như instance/default method. |
| Constructor chain | Có lời gọi constructor của superclass. | Không có constructor chain. |
| Dispatch | Instance method dùng cơ chế class inheritance và virtual dispatch. | Instance method có thể được thực thi bởi class triển khai; default method có quy tắc chọn implementation riêng. |

Thay đổi loại kiểu có thể làm thay đổi thiết kế factory, dependency injection, mock, proxy, serialization, reflection, annotation processing và cách framework phát hiện implementation. Ngay cả khi một implementation mới cung cấp cùng method, client cũ vẫn có thể không liên kết được vì loại kiểu trong API đã đổi.

### 5.5. Default method không làm thay đổi class/interface trở nên tương thích

Interface có thể cung cấp default method để thêm một implementation dùng chung cho các class triển khai. Cơ chế này hữu ích khi thiết kế API interface phát triển theo thời gian, nhưng không biến một class hiện có thành interface theo cách binary-compatible.

Ví dụ:

~~~java
public interface EventHandler {
    void handle(Event event);

    default boolean supports(Event event) {
        return true;
    }
}
~~~

Việc thêm một default method vào một interface đang tồn tại thường có thể tương thích nhị phân hơn so với việc thay class bằng interface. Tuy vậy, vẫn cần xem xét xung đột với method cùng signature trong superclass hoặc interface khác, và kiểm tra hành vi khi có nhiều default method cạnh tranh.

Không nên dùng default method như một cách giải quyết tự động cho mọi binary break. Cần phân tích cụ thể hierarchy và các implementation hiện có.

## 6. Các lỗi liên kết thường gặp

Khi một thư viện được thay phiên bản nhưng client chưa được biên dịch lại, những thay đổi về loại method hoặc loại type có thể biểu hiện thành lỗi ở runtime.

| Lỗi | Nguyên nhân thường gặp trong bối cảnh này | Hướng điều tra |
|---|---|---|
| IncompatibleClassChangeError | Binary cũ kỳ vọng static nhưng gặp instance hoặc ngược lại; client kỳ vọng class nhưng runtime cung cấp interface hoặc ngược lại. | Kiểm tra bytecode invocation, loại kiểu trong JAR runtime và phiên bản class được nạp. |
| NoSuchMethodError | Method descriptor hoặc tên method mà binary tham chiếu không còn được cung cấp. | So sánh tên, tham số, kiểu trả về và API thực tế trong JAR được nạp. |
| AbstractMethodError | Runtime dispatch tới một method abstract nhưng implementation thực tế không cung cấp implementation cần thiết, thường do tổ hợp interface/implementation không đồng bộ. | Kiểm tra version của interface, implementation và hierarchy. |
| NoClassDefFoundError | Class/interface cần thiết không có trên runtime classpath hoặc không tải được. | Kiểm tra dependency, classloader và artifact thực tế. |

Không nên kết luận nguyên nhân chỉ dựa trên tên exception. Hãy thu thập stack trace đầy đủ, classloader, vị trí JAR được nạp và bytecode của client.

### 6.1. Kiểm tra bytecode bằng javap

Khi có file class của client cũ, dùng javap để xem chỉ dẫn gọi:

~~~bash
javap -classpath client-old.jar -c -verbose com.example.Client
~~~

Tìm các opcode như:

- invokestatic: client được biên dịch để gọi phương thức static.
- invokevirtual: client được biên dịch để gọi instance method của class.
- invokeinterface: client được biên dịch để gọi instance method qua interface.
- invokespecial: thường dùng cho constructor, private method hoặc lời gọi super.

Đối với kiểu class/interface, xem constant pool, class declaration và cấu trúc superclass/interfaces trong output verbose. Có thể dùng javap -verbose trên class library cũ và mới để so sánh metadata, nhưng cần kiểm tra đúng artifact mà ứng dụng thực tế đang nạp.

### 6.2. Loại trừ lỗi do nạp nhầm phiên bản

Một số lỗi nhìn giống binary incompatibility thực chất do runtime nạp nhầm JAR:

- Có nhiều phiên bản cùng artifact trong classpath.
- Fat JAR hoặc application server chứa bản thư viện cũ.
- Container image chưa được cập nhật dù build đã tạo artifact mới.
- Classloader của plugin, application server hoặc module layer chọn một bản khác.
- Cache hoặc thư mục triển khai vẫn giữ class file cũ.

Hãy xác định class thực tế được nạp từ đâu, ví dụ thông qua Class.getProtectionDomain().getCodeSource() trong chẩn đoán phù hợp, JVM class-loading logs hoặc công cụ quan sát runtime. Sau đó đối chiếu checksum/version của artifact.

## 7. Vì sao không nên thay đổi trực tiếp API đã phát hành?

Một API public có thể được sử dụng bởi nhiều client mà nhóm phát triển thư viện không kiểm soát: ứng dụng nội bộ, plugin, integration module, batch job hoặc thư viện của đối tác. Những client này có thể đã được biên dịch từ lâu và không thể đồng loạt cập nhật.

Thay static thành instance làm thay đổi invocation contract. Thay class thành interface làm thay đổi type contract. Dù mã nguồn thư viện mới trông sạch hơn hoặc thiết kế linh hoạt hơn, binary cũ vẫn chứa giả định của phiên bản trước.

Nếu thư viện được phân phối như một API ổn định, cần coi những thay đổi này là thay đổi phá vỡ tương thích. Việc phát hành phiên bản major mới có thể là lựa chọn phù hợp, nhưng không khiến binary cũ tự động chạy được với API mới. Client cần được nâng cấp hoặc có một lớp tương thích.

## 8. Chiến lược migration an toàn

### 8.1. Giữ static facade và giới thiệu instance service mới

Nếu muốn chuyển từ static utility sang instance service có dependency hoặc cấu hình, có thể giữ class cũ làm facade trong giai đoạn chuyển tiếp.

Ví dụ:

~~~java
public final class PriceCalculator {
    private static final PriceCalculationService DEFAULT =
            new PriceCalculationService(DefaultRateProvider.INSTANCE);

    private PriceCalculator() {
    }

    /**
     * @deprecated Use PriceCalculationService instead.
     */
    @Deprecated(since = "2.0", forRemoval = true)
    public static long calculate(long amount, int percent) {
        return DEFAULT.calculate(amount, percent);
    }
}
~~~

API mới được cung cấp ở một kiểu riêng:

~~~java
public final class PriceCalculationService {
    private final RateProvider rateProvider;

    public PriceCalculationService(RateProvider rateProvider) {
        this.rateProvider = rateProvider;
    }

    public long calculate(long amount, int percent) {
        return rateProvider.apply(amount, percent);
    }
}
~~~

Client cũ vẫn gọi PriceCalculator.calculate(...), nên bytecode cũ tiếp tục tìm thấy phương thức static với cùng descriptor. Client mới có thể inject PriceCalculationService. Khi đã có kế hoạch loại bỏ facade, thư viện có thể thực hiện breaking change ở một major release sau, theo chính sách tương thích đã công bố.

Không thể khai báo thêm một instance method cùng tên và cùng tham số ngay trong PriceCalculator trong khi vẫn giữ static method cũ. Tách API instance sang class/service mới là cách giữ hai contract cùng tồn tại.

### 8.2. Giữ class cũ và giới thiệu interface mới

Nếu muốn trừu tượng hóa một class thành interface, hãy giới thiệu interface với tên nhị phân mới, sau đó cho class hiện tại triển khai interface đó:

~~~java
public interface RecordStoreContract {
    Record find(String id);
}
~~~

~~~java
public class RecordStore implements RecordStoreContract {
    @Override
    public Record find(String id) {
        // Implementation hiện có
        return null;
    }
}
~~~

Client mới có thể phụ thuộc vào RecordStoreContract, trong khi client cũ vẫn sử dụng RecordStore như một class. Cách tiếp cận này mở rộng abstraction mà không thay đổi loại kiểu của tên đã phát hành.

Nếu tên interface mong muốn phải là RecordStore, có thể giới thiệu interface đó trong một package hoặc artifact mới, còn class cũ được giữ ở package cũ làm adapter. Cần tránh trùng fully qualified name trong cùng classloader.

### 8.3. Dùng adapter hoặc facade để duy trì hợp đồng cũ

Adapter có thể chuyển lời gọi từ API cũ sang implementation mới. Khi thiết kế adapter, cần giữ:

- Tên nhị phân và descriptor của method cũ.
- Loại method static/instance như client cũ kỳ vọng.
- Kiểu class/interface của các type cũ.
- Quy tắc exception, null, thứ tự gọi và semantics được client sử dụng.
- Hành vi lifecycle và thread-safety cần thiết.

Một adapter chỉ duy trì được tương thích nếu nó thực sự giữ các điểm liên kết mà binary cũ tham chiếu. Đổi tên method hoặc thay loại type ở cùng fully qualified name không thể được khắc phục chỉ bằng cách giữ lại phần thân logic.

### 8.4. Phát hành major version và hướng dẫn chuyển đổi

Nếu mục tiêu kiến trúc bắt buộc phải đổi static thành instance hoặc class thành interface ở cùng tên API, hãy xác định đây là breaking change:

1. Công bố phiên bản major hoặc artifact/package mới theo chính sách phát hành.
2. Cung cấp migration guide nêu cách tạo object, inject dependency hoặc triển khai interface mới.
3. Liệt kê API và binary contract bị thay đổi.
4. Cung cấp adapter/facade nếu có thể duy trì một giai đoạn tương thích.
5. Cho client thời gian chuyển đổi và xác định mốc loại bỏ API cũ.
6. Kiểm tra các ứng dụng/plugin phụ thuộc trước khi triển khai đồng bộ.

Major version là tín hiệu cho người dùng thư viện biết có breaking changes; nó không phải cơ chế tương thích runtime.

## 9. Kiểm thử binary compatibility

Để phát hiện các lỗi kiểu này, cần kiểm tra client đã biên dịch trước đó với thư viện mới. Chỉ biên dịch lại toàn bộ workspace sẽ tạo bytecode theo API mới và có thể che khuất lỗi của binary cũ.

### 9.1. Kiểm thử client cũ với thư viện mới

Quy trình kiểm thử tối thiểu:

1. Build phiên bản thư viện cũ, ví dụ version 1.
2. Biên dịch một client fixture dựa trên version 1.
3. Giữ nguyên class file client, không biên dịch lại.
4. Thay thư viện runtime bằng version 2.
5. Chạy client cũ với version 2 trên classpath.
6. Ghi nhận lỗi liên kết hoặc hành vi sai.

Ví dụ classpath chạy:

~~~bash
java -cp "client-old.jar:library-v2.jar" com.example.Client
~~~

Trên Windows, dấu phân cách classpath là dấu chấm phẩy:

~~~powershell
java -cp "client-old.jar;library-v2.jar" com.example.Client
~~~

Nếu client cũ chạy được, đó là bằng chứng cho đường code đã được thực thi trong fixture; vẫn cần kiểm tra các entry point và đường gọi khác.

### 9.2. Kiểm tra source compatibility riêng

Sau bài kiểm thử binary, biên dịch client source cũ với thư viện mới. Việc này giúp xác định API nào không còn biên dịch được, nhưng kết quả phải được ghi riêng với binary test.

Ví dụ:

~~~bash
javac -cp library-v2.jar Client.java
~~~

Nếu source compile thất bại vì client vẫn gọi phương thức static hoặc dùng extends/implements theo loại kiểu cũ, đó là bằng chứng về source incompatibility. Nếu source compile thành công nhưng binary cũ thất bại, nguyên nhân nằm ở sự khác biệt giữa bytecode cũ và contract runtime mới.

### 9.3. Dùng javap để xác nhận opcode và type metadata

Có thể kiểm tra client fixture đã biên dịch với thư viện cũ:

~~~bash
javap -classpath client-old.jar -c -verbose com.example.Client
~~~

Với thay đổi static/instance, xác định invocation opcode. Với thay đổi class/interface, xem metadata kiểu và cách client sử dụng kiểu đó. Kiểm tra thêm class file của thư viện cũ và mới để chắc chắn đúng phiên bản được so sánh.

### 9.4. Dùng công cụ kiểm tra API

Trong thư viện có cam kết API ổn định, có thể tích hợp công cụ như japicmp hoặc Revapi để so sánh API giữa hai phiên bản. Những công cụ này giúp phát hiện thay đổi signature, modifier, hierarchy và các thay đổi API khác trước khi phát hành.

Kết quả công cụ so sánh API nên được kết hợp với binary fixture test. Việc so sánh metadata giúp phát hiện sớm thay đổi, còn chạy binary cũ với thư viện mới xác nhận tác động ở runtime đối với các đường code được kiểm tra.

## 10. Ma trận đánh giá thay đổi

| Thay đổi | Client source cũ khi biên dịch lại | Binary client cũ với thư viện mới | Hướng migration |
|---|---|---|---|
| Static method → instance method | Lời gọi qua tên class không còn hợp lệ; cần object/receiver. | Có thể ném IncompatibleClassChangeError do invokestatic gặp instance method. | Giữ static facade; giới thiệu service instance ở kiểu mới. |
| Instance method → static method | Cần đổi cách gọi và đánh giá receiver/state; một số cú pháp gọi qua object có thể vẫn biên dịch nhưng semantics thay đổi. | Có thể ném IncompatibleClassChangeError do invokevirtual/invokeinterface gặp static method. | Giữ instance adapter hoặc chuyển API mới sang tên/kiểu riêng. |
| Class → interface | new và extends không còn hợp lệ; cần implementation và implements. | Binary kỳ vọng class có thể ném IncompatibleClassChangeError khi runtime cung cấp interface. | Giữ class cũ; giới thiệu interface mới với tên/package khác. |
| Interface → class | implements không còn hợp lệ; client phải kế thừa class hoặc dùng API mới. | Binary kỳ vọng interface có thể ném IncompatibleClassChangeError khi runtime cung cấp class. | Giữ interface cũ; giới thiệu implementation/class mới hoặc API mới. |

Đây là đánh giá tổng quát. Kết quả thực tế còn phụ thuộc vào method descriptor, hierarchy, classloader, các tham chiếu được thực thi và phiên bản artifact đang được nạp.

## 11. Quy trình đánh giá trước khi chấp nhận thay đổi

Khi review một đề xuất đổi static thành instance hoặc đổi class thành interface, nên thực hiện theo thứ tự:

1. Xác định API public bị ảnh hưởng và fully qualified name của kiểu.
2. Tìm tất cả client/module phụ thuộc trực tiếp và gián tiếp.
3. Xác định các client có thể được biên dịch lại và các binary đã phát hành cần tiếp tục hỗ trợ.
4. So sánh class file cũ/mới và invocation opcode hoặc type metadata.
5. Chạy binary fixture cũ với thư viện mới.
6. Biên dịch source client với thư viện mới để kiểm tra source compatibility riêng.
7. Kiểm thử hành vi, đặc biệt dispatch, lifecycle, synchronization, reflection và framework integration.
8. Chọn chiến lược adapter/facade, API bổ sung hoặc major version.
9. Ghi rõ client nào cần nâng cấp, thời hạn chuyển đổi và điều kiện loại bỏ API cũ.

Với hệ thống nhiều module, cần kiểm tra module được build cùng repository và module được phân phối riêng. Một module có thể được biên dịch lại trong CI, trong khi plugin hoặc ứng dụng tích hợp bên ngoài vẫn giữ binary cũ. Không nên xem kết quả build toàn repository là đại diện cho mọi consumer.

## 12. Kết luận

Đổi static thành instance làm thay đổi cách bytecode gọi phương thức; đổi class thành interface làm thay đổi loại kiểu mà bytecode cũ kỳ vọng. Cả hai đều có thể phá vỡ binary compatibility và dẫn đến IncompatibleClassChangeError khi client cũ liên kết với thư viện mới.

Muốn migration an toàn, cần xác định rõ contract đã phát hành, giữ adapter/facade khi cần tương thích, hoặc công bố breaking change với hướng dẫn chuyển đổi. Kiểm thử client binary cũ với thư viện mới, kiểm tra bytecode bằng javap và so sánh API bằng công cụ chuyên dụng giúp phát hiện rủi ro trước khi phát hành. Source compatibility, binary compatibility và behavioral compatibility cần được đánh giá riêng để quyết định migration có thể triển khai an toàn hay không.
