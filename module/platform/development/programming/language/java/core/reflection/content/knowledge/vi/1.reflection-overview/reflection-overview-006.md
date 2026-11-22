# Khi nào nên dùng reflection và khi nào gọi trực tiếp trong Java?

Trong Java, **gọi trực tiếp** là lựa chọn mặc định khi chương trình biết kiểu và API cần dùng lúc biên dịch. **Reflection** là cơ chế kiểm tra cấu trúc của lớp và truy cập constructor, method, field hoặc annotation **khi chương trình đang chạy** thông qua các API như `Class`, `Constructor`, `Method` và `Field` trong `java.lang.reflect`.

Cả hai cách đều có thể dẫn tới cùng một hành vi. Quyết định nằm ở chỗ **mức độ động của yêu cầu**: có thật sự cần khám phá tên lớp, phương thức hoặc metadata ở runtime không? Reflection giúp giải bài toán động, nhưng tăng chi phí bảo trì, giảm kiểm tra kiểu tại compile time và có thêm giới hạn truy cập.

## 1. Phân biệt cơ chế

- **Gọi trực tiếp:** viết `service.execute()`, `new Service()` hoặc gọi qua interface. Compiler kiểm tra method có tồn tại, tham số/kiểu trả về có hợp lệ và quyền truy cập có cho phép. IDE có thể tìm tham chiếu, đổi tên và refactor một cách đáng tin cậy hơn.
- **Reflection:** lấy đối tượng mô tả lớp (`Class<?>`), tìm member bằng tên/chữ ký tại runtime rồi gọi qua `Method.invoke(...)` hoặc khởi tạo qua `Constructor.newInstance(...)`. Lỗi tên và chữ ký thường chỉ lộ ra khi chạy.
- **Đa hình không đồng nghĩa với reflection:** `Formatter formatter = ...; formatter.format(text);` vẫn là lời gọi Java thông thường. JVM có thể chọn implementation tại runtime nhờ virtual dispatch mà không cần `Method.invoke`.
- **Có `Class<?>` chưa chắc đã cần gọi method bằng reflection:** `SomeType.class` và `object.getClass()` chỉ lấy thông tin kiểu; chỉ dùng khả năng introspection nào thực sự cần.

Một lời gọi phản chiếu không tự động vượt qua giới hạn `private`, ranh giới Java module hay quyền truy cập. Cơ chế kiểm tra truy cập vẫn được áp dụng.

## 2. Chọn cách nào theo tình huống?

| Tình huống | Lựa chọn ưu tiên | Lý do |
| --- | --- | --- |
| Đã biết lớp, constructor, method và chữ ký khi viết mã | Gọi trực tiếp | An toàn kiểu, dễ refactor, dễ theo dõi luồng gọi |
| Có nhiều cách xử lý cùng một hợp đồng interface | Interface + đa hình, factory hoặc dependency injection | Chọn implementation linh hoạt mà không phải dò tên method |
| Phải đọc annotation, field, method của nhiều kiểu không biết trước | Reflection ở lớp hạ tầng/framework | Metadata chỉ có thể xác định đầy đủ lúc runtime |
| Cần nạp một implementation theo cấu hình hoặc plugin bên ngoài | `ServiceLoader` hoặc reflection có kiểm soát | Tên implementation có thể chưa biết khi biên dịch |
| Muốn gọi private method từ nghiệp vụ hoặc test | Ưu tiên thiết kế lại API/phân tách trách nhiệm | Tránh ghép chặt vào implementation và vi phạm đóng gói |
| Vòng lặp rất nóng, gọi method lặp lại thường xuyên | Ưu tiên lời gọi trực tiếp sau khi đo đạc | Hạn chế chi phí lookup/invoke và chuyển đổi kiểu |
| Truy cập API của dependency mà mã nguồn đã tham chiếu được | Gọi trực tiếp | Reflection thêm sự mong manh mà không tạo lợi ích động |

**Nguyên tắc:** chỉ đưa reflection vào nơi hệ thống thực sự phải xử lý thông tin chưa biết tại compile time; để phần còn lại giao tiếp qua kiểu hoặc interface rõ ràng.

## 3. Ví dụ: cùng một lời gọi, hai cách thực hiện

Tạo tệp `CallChoiceDemo.java`:

```java
import java.lang.reflect.Method;

public class CallChoiceDemo {
    public static class GreetingService {
        public String greet(String name) {
            return "Xin chào, " + name;
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        GreetingService service = new GreetingService();

        // Gọi trực tiếp: compiler biết kiểu và chữ ký.
        String direct = service.greet("An");

        // Reflection: tìm phương thức theo tên/chữ ký lúc chạy.
        Class<?> type = service.getClass();
        Method greetMethod = type.getMethod("greet", String.class);
        Object dynamic = greetMethod.invoke(service, "An");

        System.out.println("Direct: " + direct);
        System.out.println("Reflection: " + dynamic);
    }
}
```

Biên dịch và chạy bằng JDK 17 trở lên:

```bash
javac CallChoiceDemo.java
java CallChoiceDemo
```

Kết quả:

```text
Direct: Xin chào, An
Reflection: Xin chào, An
```

Phân tích:

1. `service.greet("An")` được compiler kiểm tra: đổi tên `greet` mà chưa sửa chỗ gọi sẽ sinh lỗi biên dịch.
2. `getMethod("greet", String.class)` chỉ tìm **public method** có đúng chữ ký tham số `String`, kể cả method public kế thừa. Nếu tên/chữ ký không tồn tại, chương trình nhận `NoSuchMethodException` lúc chạy.
3. `Method.invoke(service, "An")` trả về `Object` (hoặc `null` nếu method trả về `void`). Vì vậy phía gọi có thể cần kiểm tra và ép kiểu khi biết kiểu kết quả.
4. Nếu code bên trong `greet` ném exception, `invoke` bọc exception đó trong `InvocationTargetException`; cần xem `getCause()` để biết lỗi gốc. Lỗi truy cập có thể tạo `IllegalAccessException`.

Ở ví dụ này, reflection **không có lợi ích**: biết rõ `GreetingService` và `greet` ngay từ đầu nên nên dùng gọi trực tiếp.

## 4. Trường hợp reflection có lý do chính đáng: lớp được chọn ở runtime

Một hệ thống plugin có thể nhận tên implementation từ cấu hình, còn phần nghiệp vụ chỉ biết một interface chung. Có thể dùng reflection ở **điểm khởi tạo plugin**, rồi gọi trực tiếp qua interface sau đó.

Tạo tệp `RuntimeFormatterDemo.java`:

```java
import java.util.Locale;

public class RuntimeFormatterDemo {
    public interface Formatter {
        String format(String input);
    }

    public static class UpperFormatter implements Formatter {
        public UpperFormatter() {
        }

        @Override
        public String format(String input) {
            return input.toUpperCase(Locale.ROOT);
        }
    }

    public static void main(String[] args)
            throws ReflectiveOperationException {
        // Trong ứng dụng thật, giá trị này có thể lấy từ cấu hình tin cậy.
        String className = System.getProperty(
                "formatter.class", UpperFormatter.class.getName());

        Class<?> rawClass = Class.forName(className);
        Class<? extends Formatter> implementation =
                rawClass.asSubclass(Formatter.class);
        Formatter formatter =
                implementation.getDeclaredConstructor().newInstance();

        // Từ đây là đa hình thông thường, không gọi Method.invoke.
        System.out.println(formatter.format("reflection"));
    }
}
```

Chạy:

```bash
javac RuntimeFormatterDemo.java
java RuntimeFormatterDemo
```

Kết quả:

```text
REFLECTION
```

Điểm cần hiểu:

- `Class.forName(className)` tải/tìm class theo tên được biết tại runtime (với dạng này, việc khởi tạo class cũng có thể xảy ra). Class phải có trên classpath/module path phù hợp.
- `asSubclass(Formatter.class)` kiểm tra class có tương thích với `Formatter`; nếu không, phát sinh `ClassCastException`.
- `getDeclaredConstructor().newInstance()` yêu cầu constructor không tham số phù hợp và có thể truy cập từ nơi gọi. Nếu thiếu sẽ có `NoSuchMethodException`; nếu constructor ném lỗi thì lỗi được bọc trong `InvocationTargetException`.
- Sau khi tạo được `Formatter`, gọi `formatter.format(...)` qua interface là đủ. Không cần tiếp tục tìm và invoke method bằng reflection mỗi lần xử lý.
- Tên class lấy từ nguồn không đáng tin cậy có thể dẫn tới nạp/khởi tạo code ngoài ý muốn. Ứng dụng phải giới hạn provider được phép dùng, kiểm soát dependency, và không coi ép kiểu interface là cơ chế bảo mật.

Trong trường hợp hệ thống đã biết danh sách implementation, một **factory/registry** ánh xạ tên tới `Supplier<Formatter>` còn đơn giản hơn. Nếu cần cơ chế plugin chuẩn, **`ServiceLoader<Formatter>`** cho phép tìm provider qua cấu hình dịch vụ mà không phải tự ghép tên class và constructor trong mã nghiệp vụ. Framework dependency injection cũng thường xử lý bài toán chọn implementation tốt hơn reflection tự viết.

## 5. Những tình huống reflection thường được sử dụng

### Đọc metadata và xây dựng công cụ tổng quát

- Framework có thể quét annotation để thiết lập dependency injection, mapping, serialization hoặc validation.
- Công cụ debug, test runner và công cụ khám phá API có thể liệt kê method, field, constructor, annotation từ những lớp chỉ xuất hiện khi chạy.
- Thư viện chuyển đổi dữ liệu tổng quát có thể phải xử lý các kiểu domain không được liệt kê tường minh trong chính thư viện.

Ví dụ, một thư viện có thể duyệt `type.getDeclaredFields()` để đọc metadata field rồi quyết định cách ánh xạ dữ liệu. Việc này khác với nghiệp vụ biết sẵn `customer.getName()`: ở trường hợp sau, getter trực tiếp là giải pháp rõ ràng hơn.

### Plugin và phần mở rộng

Khi implementation do plugin cung cấp sau thời điểm biên dịch, ứng dụng có thể cần nạp class, kiểm tra hợp đồng, tạo instance tại runtime. Reflection hữu ích **ở biên tích hợp**, còn thao tác lâu dài nên thông qua interface đã định nghĩa. Nếu runtime thay đổi phương thức/tên kiểu không có hợp đồng chung, cân nhắc adapter hoặc giao thức ổn định thay vì rải các chuỗi tên method khắp hệ thống.

### Các lựa chọn trước khi dùng reflection

- **Interface/đa hình:** thay cho phân nhánh theo tên class và gọi method động.
- **Factory, registry, dependency injection:** thay cho dựng đối tượng bằng tên class khi tập implementation có thể khai báo được.
- **`ServiceLoader`:** cơ chế provider/plugin chuẩn của Java.
- **Annotation processing lúc biên dịch:** khi có thể tạo metadata/code sớm thay vì quét reflection mỗi lần chạy.
- **`MethodHandle` / `MethodHandles.Lookup`:** công cụ gọi động có kiểu chữ ký rõ hơn trong một số trường hợp nâng cao; vẫn cần kiểm tra quyền truy cập và đo hiệu năng, không phải lối tắt bắt buộc.

## 6. Chi phí, quyền truy cập và độ an toàn

**Kiểm tra kiểu và bảo trì.** Gọi trực tiếp giúp compiler phát hiện lỗi đổi tên hoặc thay đổi tham số sớm. Với `getMethod("save", ...)`, các tên member ở dạng chuỗi không được refactor chắc chắn; lỗi chỉ xuất hiện ở runtime. Nên tập trung chuỗi tên member ở một nơi, kiểm tra kết quả và có test tích hợp cho đường đi động.

**Hiệu năng.** Reflection có chi phí khám phá member, kiểm tra truy cập, gọi động và có thể sinh boxing/unboxing. Chi phí thực tế tùy phiên bản JDK, độ nóng của mã và khả năng tối ưu của JVM: không nên khẳng định mọi lời gọi reflection đều chậm hơn một hệ số cố định. Nếu bắt buộc dùng reflection, **tra cứu `Method`/`Constructor` một lần rồi tái sử dụng** khi hợp lý, tránh `getMethod` bên trong vòng lặp; dùng benchmark thích hợp như JMH trước khi tối ưu đoạn code nhạy cảm.

**Public, private và Java modules.**

- `getMethod(...)` tìm public method; `getDeclaredMethod(...)` tìm method được khai báo trực tiếp ở lớp đó, bao gồm cả non-public, nhưng **tìm thấy không có nghĩa là gọi được**.
- `setAccessible(true)`/`trySetAccessible()` có thể bị giới hạn bởi access checks và cơ chế module. Java 17+ áp dụng đóng gói mạnh đối với nhiều package/module; việc mở truy cập có thể thất bại với `InaccessibleObjectException` hoặc `trySetAccessible()` trả về `false`.
- Trong Java Platform Module System, `exports` cho phép sử dụng public API của package theo quy tắc module; `opens` hỗ trợ deep reflection vào package cho module được cấp quyền. Chỉ mở package thật sự cần cho framework và ưu tiên public contract rõ ràng.
- Không xây chức năng nghiệp vụ phụ thuộc vào private field/method của thư viện bên thứ ba; chúng có thể thay đổi không báo trước.

**Exception và chẩn đoán.** Ngoài `NoSuchMethodException`, cần phân biệt `ClassNotFoundException`, `IllegalAccessException`, `InstantiationException`, `InvocationTargetException` và `ClassCastException` theo bước thực hiện. Khi log `InvocationTargetException`, giữ cả cause gốc. Đưa tên class/method/chữ ký dự kiến vào thông báo lỗi sẽ giúp kiểm tra cấu hình nhanh hơn.

**An toàn và triển khai.** Không lấy tên lớp/phương thức trực tiếp từ input không tin cậy rồi thực thi tùy ý. Với native image hoặc môi trường phân tích mã theo mô hình closed world, reflective access có thể cần khai báo metadata hoặc cơ chế đăng ký phù hợp với runtime/framework; kiểm tra ngay từ giai đoạn build và test chạy thật trên mục tiêu triển khai.

## 7. Quy trình ra quyết định

1. **Tên lớp và method đã biết khi biên dịch?** Dùng gọi trực tiếp.
2. **Chỉ cần đổi implementation theo điều kiện/cấu hình?** Tạo interface + factory/DI/`ServiceLoader`; lời gọi nghiệp vụ vẫn trực tiếp qua interface.
3. **Cần đọc cấu trúc hoặc annotation của kiểu chưa biết trước?** Dùng reflection có giới hạn, gom phần truy cập động vào adapter/hạ tầng, kiểm tra lỗi và cache metadata nếu cần.
4. **Phải gọi method được xác định ở runtime?** Xác thực tên và chữ ký, kiểm tra tương thích, xử lý lỗi truy cập/exception và thu hẹp nơi gọi bằng reflection.
5. **Phải mở private member chỉ để “cho tiện”?** Xem lại ranh giới API hoặc thiết kế trước khi sử dụng deep reflection.
6. **Có nghi ngờ vấn đề hiệu năng/đóng gói/module?** Viết kiểm thử/benchmark ở đúng runtime mục tiêu rồi chọn mức động tối thiểu.

### Tự kiểm tra cách chọn

- Gọi `orderService.submit(order)` trong service đã biết kiểu: **gọi trực tiếp**.
- Chọn `PaymentProcessor` theo provider có sẵn: **interface + factory/DI**, không cần `Method.invoke`.
- Viết thư viện kiểm tra annotation trên những class của ứng dụng mà thư viện chưa biết khi biên dịch: **reflection hợp lý**.
- Nạp implementation được cài thêm sau khi build: dùng **`ServiceLoader` hoặc khởi tạo động có kiểm soát**, rồi gọi qua interface.
- Muốn sửa private field của dependency để tránh tạo API đúng nghĩa: **tránh reflection**, ưu tiên thiết kế/test seam phù hợp.

**Kết luận:** Reflection là công cụ giải quyết yêu cầu động tại runtime. Gọi trực tiếp và đa hình vẫn phù hợp cho phần lớn business logic; reflection nên nằm ở một ranh giới nhỏ, có kiểm tra và xử lý lỗi rõ ràng.
