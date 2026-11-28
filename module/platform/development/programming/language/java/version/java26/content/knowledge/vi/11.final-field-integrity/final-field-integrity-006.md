# Nhận diện framework hoặc thư viện còn sửa trường final

Từ JDK 26, JVM cảnh báo khi code dùng deep reflection để ghi lại một trường final của đối tượng sau khi constructor đã chạy. Thay đổi này nằm trong JEP 500: Prepare to Make Final Mean Final. Mục tiêu là giúp ứng dụng dựa được vào ý nghĩa của final, tăng tính đúng đắn và mở đường cho JVM tối ưu hóa an toàn hơn.

Lỗi thường xuất hiện từ thư viện hoặc framework chứ không nhất thiết từ code nghiệp vụ. Các nhóm cần kiểm tra gồm dependency injection dùng field injection, thư viện ánh xạ JSON/XML, ORM/hydration, serializer tự triển khai, thư viện clone đối tượng, công cụ mock/test và thư viện dựng object bằng reflection. Không nên kết luận một framework cụ thể có vấn đề chỉ vì nó dùng reflection; cần xác định đúng phiên bản, cấu hình và đường gọi thực tế.

JDK 26 và JDK 27 đều phát cảnh báo theo mặc định cho thao tác deep reflection không được cấp quyền. Trong một bản phát hành tương lai, hành vi mặc định sẽ chuyển sang từ chối thao tác. Bài học này hướng dẫn cách tìm dependency gây mutation, phân biệt quyền truy cập package với quyền sửa final field, thử chế độ deny và thay thế các cách khởi tạo đối tượng không còn phù hợp.

## 1. JEP 500 thay đổi điều gì?

Trong Java, trường final được kỳ vọng chỉ nhận giá trị trong quá trình khởi tạo đối tượng. Tuy nhiên, trước JDK 26, code có thể dùng reflection để mở quyền truy cập rồi ghi vào một trường final không-static:

~~~java
Field field = Config.class.getDeclaredField("timeout");
field.setAccessible(true);
field.set(config, 30);
~~~

Cách làm này phá vỡ hợp đồng mà class đã công bố. Code khác có thể dựa vào giả định rằng giá trị final không đổi sau khi constructor kết thúc. JVM cũng có thể tối ưu việc đọc final field dựa trên giả định đó. Khi một thư viện âm thầm thay đổi trường final, kết quả quan sát được có thể không nhất quán giữa truy cập reflection và truy cập thông thường.

JEP 500 bắt đầu quá trình siết quyền ghi final field qua deep reflection:

| Phiên bản | Hành vi chính |
|---|---|
| JDK 25 trở về trước | Deep reflection có thể ghi một số non-static final field nếu các điều kiện truy cập cho phép; không có cảnh báo JEP 500 |
| JDK 26 | Mặc định vẫn cho phép mutation trái phép nhưng cảnh báo lần đầu theo caller module |
| JDK 27 | Tiếp tục cảnh báo theo chính sách JEP 500; có thể dùng debug hoặc deny để tìm và chặn |
| Bản phát hành tương lai | Dự kiến chuyển mặc định sang deny; JDK sẽ từ chối mutation không được cấp quyền |

JEP 500 không phải preview feature. Đây là thay đổi hành vi runtime trong JDK 26; không cần bật cờ preview để sử dụng hoặc kiểm tra.

## 2. Phân biệt truy cập sâu và quyền sửa final field

Hai quyền sau độc lập với nhau:

- **Deep reflection access** cho phép code truy cập thành viên không public qua reflection, thường bằng setAccessible(true) hoặc trySetAccessible().
- **Final field mutation permission** cho phép module của code gọi thực hiện thao tác ghi lên non-static final field trong những điều kiện được JDK quy định.

Vì vậy, mở package không tự động cấp quyền sửa final field. Ngược lại, cấp quyền final field mutation cũng không tự mở package private cho một module khác.

Với một trường private final trong module khác, thông thường cần cả hai điều kiện:

1. Package chứa class khai báo trường được mở cho module của thư viện.
2. Module gọi được cấp final field mutation permission.

Ví dụ khi thư viện chạy trên classpath và class đích nằm trong named module:

~~~sh
java \
  --add-opens=app.model/com.example.model=ALL-UNNAMED \
  --enable-final-field-mutation=ALL-UNNAMED \
  -jar application.jar
~~~

Nếu thư viện chạy trong named module, thay ALL-UNNAMED bằng tên module gọi tương ứng:

~~~sh
java \
  --add-opens=app.model/com.example.model=framework.module \
  --enable-final-field-mutation=framework.module \
  -m app.main/com.example.Main
~~~

Các tùy chọn này chỉ minh họa cách cấp quyền trong trường hợp cần thiết. Khi module gọi nằm trên classpath, ALL-UNNAMED áp dụng cho toàn bộ code thuộc unnamed module, không giới hạn được tới một JAR riêng lẻ. Nếu muốn cấp quyền hẹp hơn, cần cân nhắc đóng gói thư viện thành named module và chỉ cấp cho module đó.

### 2.1. Điều kiện để Field.set ghi được final field

Trong JDK 26, thao tác ghi final field qua Field mutation methods chỉ có thể thành công khi các điều kiện phù hợp được đáp ứng:

- Field object đã được phép truy cập bằng setAccessible(true).
- Module của code gọi được cấp quyền final field mutation.
- Quy tắc truy cập module cho phép thao tác: cùng module, hoặc field/class public trong package được export phù hợp, hoặc package được open cho caller.
- Trường là non-static.
- Class khai báo trường không phải record và không phải hidden class.

Một số trường luôn không thể sửa bằng Field.set, kể cả khi setAccessible(true) thành công:

- static final field trong bất kỳ class hoặc interface nào.
- final field khai báo trong record.
- final field khai báo trong hidden class.

Các phương thức mutation được JDK ghi nhận gồm Field.set và các setter primitive tương ứng, cùng MethodHandles.Lookup.unreflectSetter(Field). Việc lấy được Field object hoặc gọi setAccessible(true) không chứng minh rằng quyền ghi final field đã được cấp.

### 2.2. Vì sao --add-opens không đủ?

Ví dụ một thư viện đã có quyền mở package:

~~~sh
java --add-opens=app.model/com.example.model=ALL-UNNAMED -jar application.jar
~~~

Tùy chọn trên giải quyết quyền truy cập sâu vào package. Nếu caller chưa được cấp quyền final field mutation, JDK 26 vẫn xem thao tác ghi final field là trái phép và phát cảnh báo. Khi chạy với deny, thao tác bị từ chối.

Không thêm --add-opens hàng loạt để dập cảnh báo. Hãy đọc warning để xác định caller và package đích, sau đó quyết định xem thư viện có thực sự cần truy cập sâu hay không.

## 3. Nhận diện các nhóm thư viện có thể ghi final field

Một framework có thể dùng reflection để đọc annotation, tìm constructor, gọi factory hoặc đọc private field mà không hề ghi final field. Chỉ những đường code thực sự thực hiện mutation mới thuộc phạm vi cảnh báo của JEP 500.

| Nhóm thư viện | Mẫu triển khai có nguy cơ | Hướng thay thế nên kiểm tra |
|---|---|---|
| Dependency injection | Tạo object rỗng rồi gán dependency vào private final field | Constructor injection hoặc factory được framework gọi |
| JSON/XML/object mapper | Tạo object không qua constructor rồi ghi từng field | Creator constructor, record, factory hoặc builder |
| ORM và hydration | Khôi phục entity bằng cách gán trực tiếp final field | Constructor/factory mapping hoặc API hydration được framework hỗ trợ |
| Serializer tự triển khai | Dùng Field.set để khôi phục dữ liệu vào final field | Serialization proxy, record proxy hoặc constructor mapping |
| Mocking và test utility | Sửa final field để cài dependency hoặc tạo trạng thái test | Constructor seam, factory, interface hoặc API test được hỗ trợ |
| Clone/copy utility | Gọi clone rồi thay final field bằng bản sao mới | Copy constructor hoặc static copy factory |
| Configuration framework | Tạo bean trước rồi ghi lại final field | Constructor binding hoặc immutable configuration object |

Đây là các mẫu thiết kế cần điều tra, không phải danh sách framework chắc chắn gây cảnh báo. Hành vi thay đổi theo phiên bản và cấu hình. Một phiên bản mới có thể đã chuyển sang constructor binding, trong khi một adapter cũ vẫn dùng reflection.

Cũng cần phân biệt cảnh báo của JEP 500 với mọi cơ chế ghi final field khác. JEP 500 tập trung vào các mutation method của reflection và MethodHandles được nêu trong tài liệu. Cơ chế nội bộ, JNI hoặc Unsafe có quy tắc riêng; không thấy warning JEP 500 không chứng minh toàn bộ dependency tree không có đường ghi final field.

## 4. Đọc warning để tìm đúng dependency

JDK 26 mặc định dùng chế độ warn. Khi một module thực hiện mutation final field trái phép lần đầu, JVM phát warning tương tự:

~~~text
WARNING: Final field timeout in class com.example.Config
has been mutated reflectively by class com.vendor.mapper.FieldWriter
in unnamed module @... (file:/.../mapper.jar)
WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release unless
final field mutation is enabled
~~~

Warning cho biết:

- Tên trường final bị ghi.
- Class khai báo trường.
- Class thực hiện mutation.
- Module của caller.
- Vị trí code được nạp, thường giúp nhận ra JAR chứa thư viện.

Trong một module, chế độ warn chỉ phát tối đa một warning. Một warning không có nghĩa chỉ có một trường hoặc một lời gọi bị ảnh hưởng. Nếu muốn xem mọi mutation cùng stack trace, dùng chế độ debug.

### 4.1. Bật debug để lấy stack trace

~~~sh
java --illegal-final-field-mutation=debug -jar application.jar
~~~

debug cho phép mutation tiếp tục nhưng in warning và stack trace cho từng lần mutation trái phép. Dùng stack trace để tìm phương thức của thư viện thực hiện Field.set hoặc unreflectSetter, sau đó ghi lại dependency và phiên bản trong báo cáo migration.

Khi chạy test suite, hãy chạy các luồng nghiệp vụ quan trọng: khởi động ứng dụng, tạo bean, đọc cấu hình, deserialize payload, hydrate entity, clone object và chạy test. Một thư viện chỉ ghi final field trong một nhánh code hiếm có thể không xuất hiện khi chạy một smoke test ngắn.

## 5. Dùng JFR để lập hồ sơ final field mutation

JDK 26 có JFR event tên jdk.FinalFieldMutation. Event ghi nhận mutation final instance field qua deep reflection hoặc việc tạo MethodHandle ghi trường bằng Lookup.unreflectSetter. Event có thể cung cấp class khai báo, tên trường, thread và stack trace.

Bắt đầu ứng dụng với JFR:

~~~sh
java \
  -XX:StartFlightRecording=filename=final-field-audit.jfr \
  --illegal-final-field-mutation=warn \
  -jar application.jar
~~~

Sau khi chạy các luồng nghiệp vụ cần kiểm tra, xem event:

~~~sh
jfr print --events jdk.FinalFieldMutation final-field-audit.jfr
~~~

JFR hữu ích khi cần thu thập bằng chứng trong một phiên chạy dài hoặc môi trường staging. Event phản ánh mutation được thực hiện; một thao tác bị deny và không xảy ra mutation không tạo event mutation tương ứng. Để xem các lần thử trái phép bị chặn hoặc cần stack trace cho từng lần thử, dùng debug hoặc deny trong test riêng.

JFR và debug phục vụ hai mục tiêu khác nhau:

| Công cụ | Phù hợp khi |
|---|---|
| warn | Muốn phát hiện nhanh trong quá trình chạy bình thường với ít log |
| debug | Muốn stack trace cho từng mutation trái phép |
| JFR | Muốn thu thập event có cấu trúc trong workload dài và phân tích sau |
| deny | Muốn kiểm tra ứng dụng có còn phụ thuộc mutation trái phép hay không |

## 6. Tạo chương trình nhỏ để tái hiện cảnh báo

Tạo file FinalMutationProbe.java:

~~~java
import java.lang.reflect.Field;

public class FinalMutationProbe {

    static final class Config {
        private final int timeout = 10;

        int timeout() {
            return timeout;
        }
    }

    public static void main(String[] args) throws Exception {
        Config config = new Config();

        Field field = Config.class.getDeclaredField("timeout");
        field.setAccessible(true);

        field.setInt(config, 30);

        System.out.println("Reflection read: " + field.getInt(config));
        System.out.println("Normal read: " + config.timeout());
    }
}
~~~

Biên dịch:

~~~sh
javac FinalMutationProbe.java
~~~

Chạy theo các chế độ:

~~~sh
java FinalMutationProbe
java --illegal-final-field-mutation=debug FinalMutationProbe
java --illegal-final-field-mutation=deny FinalMutationProbe
~~~

Ở chế độ mặc định của JDK 26, mutation trái phép được phép tiếp tục nhưng phát warning lần đầu cho unnamed module. Ở chế độ debug, warning kèm stack trace được phát cho mỗi lần. Ở chế độ deny, Field.setInt ném IllegalAccessException cho mutation trái phép.

Không dựa vào kết quả đọc trường sau khi đã mutate để viết logic ứng dụng. Field API cảnh báo rằng việc sửa final field ngoài quá trình khôi phục instance trước khi object được chia sẻ có thể gây kết quả không dự đoán được; một phần code có thể vẫn đọc giá trị cũ do tối ưu hóa hoặc cách JVM xử lý final field.

## 7. Chạy kiểm thử strict bằng deny

Đây là bước quan trọng để biết ứng dụng có còn phụ thuộc vào mutation trái phép hay không:

~~~sh
java --illegal-final-field-mutation=deny -jar application.jar
~~~

Trong CI hoặc test profile, chạy toàn bộ integration test bằng deny. Không thêm --enable-final-field-mutation cho module đang muốn kiểm tra; nếu caller đã được cấp quyền thì mutation đó không còn bị xem là illegal và sẽ không bị deny.

Nếu dự án đang có flag cấp quyền rộng, hãy tạo một profile kiểm thử không có flag đó. Với code trên classpath, kiểm tra cả cấu hình khởi chạy và manifest của executable JAR nếu dự án có khai báo Enable-Final-Field-Mutation.

Kết quả mong muốn là các luồng khởi tạo, binding và deserialization hoạt động mà không cần ghi final field trái phép. Nếu deny làm test thất bại, dùng stack trace của exception để xác định thư viện cần nâng cấp hoặc thay thế.

## 8. Phân biệt platform serialization với serializer thông thường

JEP 500 điều chỉnh deep reflection mutation thông thường. Cơ chế mặc định của Java platform serialization có đường khôi phục trường riêng cho đối tượng Serializable. Cơ chế này được duy trì riêng và không đồng nghĩa mọi thư viện JSON, XML hoặc mapper đều được miễn quy tắc JEP 500. Nếu một phương thức readObject do ứng dụng tự viết gọi Field.set để gán transient final field, lời gọi Field.set đó vẫn là deep reflection mutation thông thường và chịu quy tắc JEP 500.

Một số thư viện serialization có thể dùng ReflectionFactory hoặc cơ chế platform serialization dành cho Serializable. Đây là critical internal API, có phạm vi sử dụng đặc biệt và không nên được xem là cách thay thế tổng quát cho constructor. Việc thêm Serializable vào class chỉ để tránh warning có thể kéo theo giao thức phức tạp, rủi ro dữ liệu không hợp lệ và ràng buộc tương thích lâu dài.

Cần phân loại đường xử lý cụ thể:

- ObjectInputStream và cơ chế serialization của nền tảng có xử lý riêng cho Serializable.
- Serializer tự viết dùng Field.set trên private final field đi theo đường deep reflection và chịu quy tắc JEP 500.
- Một thư viện dùng ReflectionFactory cho Serializable có thể đi theo cơ chế đặc biệt, không phát warning JEP 500.
- Record được khôi phục qua canonical constructor theo giao thức serialization của record; final component field không thể bị sửa bằng Field.set.

Do đó, kiểm tra warning là cần thiết nhưng chưa phải bằng chứng đầy đủ cho mọi cách thư viện khôi phục đối tượng. Hãy đọc tài liệu của serializer, xem stack trace và kiểm thử class model thực tế.

## 9. Cách thay thế mutation trong framework và thư viện

### 9.1. Dependency injection: ưu tiên constructor injection

Không nên tạo object rồi ghi dependency vào final field. Hãy để constructor nhận đủ dependency:

~~~java
final class PaymentService {
    private final PaymentRepository repository;
    private final Clock clock;

    PaymentService(PaymentRepository repository, Clock clock) {
        this.repository = repository;
        this.clock = clock;
    }
}
~~~

Container có thể tìm constructor phù hợp, resolve dependency rồi gọi constructor. Trường final được gán trong quá trình khởi tạo hợp lệ; không cần Field.set.

### 9.2. Object mapper: dùng creator, record hoặc factory

Với model dữ liệu, có thể dùng record để dữ liệu được truyền qua canonical constructor:

~~~java
record Customer(String id, String displayName, int level) { }
~~~

Nếu cần class thông thường, serializer nên hỗ trợ constructor hoặc static factory được chỉ định bằng annotation/cấu hình. Với class có invariant, constructor/factory có thể kiểm tra dữ liệu trước khi tạo object.

Không nên tạo object rỗng, sau đó ghi hàng loạt field private final. Cách đó bỏ qua validation và có thể tạo instance ở trạng thái không hợp lệ.

### 9.3. Serializer: dùng serialization proxy hoặc dữ liệu trung gian

Một cách phổ biến là chuyển object thành một representation riêng, sau đó dựng lại object qua constructor hoặc factory. Serialization proxy pattern dùng representation trung gian để không phải sửa trực tiếp trạng thái final của object đích.

Với định dạng JSON/YAML/Protobuf, có thể dùng record hoặc DTO trung gian rồi chuyển sang domain object qua constructor. Cách này cũng giúp kiểm soát versioning và validation.

### 9.4. Clone/copy: dùng copy constructor hoặc static factory

Nếu clone yêu cầu thay final collection bằng bản sao mới, cân nhắc copy constructor:

~~~java
final class UserProfile {
    private final List<String> roles;

    UserProfile(List<String> roles) {
        this.roles = List.copyOf(roles);
    }

    UserProfile copy() {
        return new UserProfile(roles);
    }
}
~~~

Không cần gọi Object.clone rồi dùng reflection để thay trường final. Copy constructor hoặc static factory có thể chuẩn bị dữ liệu trước khi gán trường trong constructor.

### 9.5. Test và mocking: tạo seam thay vì sửa final field

Nếu test cần thay dependency hoặc giá trị cấu hình, dùng constructor injection, factory, interface hoặc test fixture. Với class không thể thay đổi, ưu tiên API test được framework hỗ trợ và nâng cấp mocking library. Không nên thêm quyền mutation toàn JVM chỉ để một test utility sửa một final field.

## 10. Khi nào mới cân nhắc bật quyền mutation?

Mục tiêu dài hạn là không phụ thuộc vào deep reflection để sửa final field. Tuy nhiên, có thể có một thư viện thiết yếu chưa có phiên bản thay thế và chưa thể sửa ngay. Khi đó, application owner có thể cấp quyền rõ ràng cho module caller.

Ví dụ cho code trên classpath:

~~~sh
java --enable-final-field-mutation=ALL-UNNAMED -jar application.jar
~~~

Ví dụ cho một named module:

~~~sh
java --enable-final-field-mutation=framework.module -m app.main/com.example.Main
~~~

Nếu package đích private trong một module khác, vẫn phải mở package cho caller theo quy tắc module. Flag enable không thay thế --add-opens.

Các nguyên tắc khi dùng tạm:

- Cấp quyền cho đúng module gọi; tránh ALL-UNNAMED nếu thư viện có thể chạy trong named module.
- Ghi rõ dependency, phiên bản, class/field bị mutate và lý do chưa thể thay thế.
- Có issue hoặc kế hoạch nâng cấp để loại bỏ flag.
- Giữ test strict bằng deny ở một pipeline khác để phát hiện regression.
- Không dùng --illegal-final-field-mutation=allow như cấu hình production lâu dài; đây là chế độ chuyển tiếp và sẽ bị loại bỏ.
- Không thêm flag vào mọi môi trường chỉ để che warning.

Lưu ý: --illegal-final-field-mutation điều khiển cách xử lý mutation không được cấp quyền trên toàn hệ thống; --enable-final-field-mutation cấp quyền cho caller module cụ thể. Hai tùy chọn có mục đích khác nhau.

## 11. Quy trình kiểm tra dependency trước khi nâng cấp JDK

Có thể áp dụng quy trình sau cho một ứng dụng lớn:

1. **Lập danh sách dependency**: ghi nhận framework, serializer, ORM, DI container, mocking library và plugin test cùng phiên bản thực tế được resolve.
2. **Kiểm tra tài liệu release**: tìm ghi chú tương thích JDK 26/27, issue về final-field mutation, constructor binding và hỗ trợ record.
3. **Chạy với mặc định JDK 26**: lưu stderr để thu warning. Ghi nhận caller module, class, field và code source.
4. **Chạy debug trong staging/test**: thu stack trace của từng mutation để định vị method và JAR.
5. **Ghi JFR nếu workload dài**: phân tích event jdk.FinalFieldMutation theo class, field và stack trace.
6. **Chạy strict deny**: không bật quyền mutation cho module đang audit; chạy integration test và luồng nghiệp vụ quan trọng.
7. **Nâng cấp hoặc thay thế thư viện**: ưu tiên bản đã dùng constructor/factory, record hoặc cơ chế deserialization phù hợp.
8. **Kiểm thử lại**: giữ deny trong CI để tránh dependency mới đưa mutation trở lại.
9. **Thu hẹp quyền tạm thời**: chỉ nếu thật sự chưa thể thay thế, cấp cho caller module cần thiết và ghi rõ thời hạn xử lý.

Không chỉ kiểm tra unit test. Những thư viện có thể chỉ ghi final field khi khởi tạo application context, deserialize payload đặc biệt, tạo proxy, clone object hoặc chạy một nhánh kiểm thử cụ thể. Hãy chạy cả các kịch bản production quan trọng.

## 12. Bảng chẩn đoán

| Hiện tượng | Nguyên nhân có thể | Cách xử lý |
|---|---|---|
| JDK 26 xuất warning khi khởi động | Một dependency dùng deep reflection để ghi final field | Dùng debug hoặc JFR để tìm caller |
| Chỉ có một warning dù có nhiều class | Warn giới hạn tối đa một warning cho mỗi caller module | Chạy debug để thấy từng mutation |
| --add-opens không dập warning | Package đã mở nhưng caller chưa được cấp final field mutation permission | Xác định module caller; ưu tiên sửa dependency |
| deny gây IllegalAccessException | Có mutation trái phép chưa được cấp quyền | Dùng stack trace để nâng cấp/thay thế thư viện |
| Mutation vẫn chạy khi dùng deny | Caller đã được cấp quyền bằng --enable-final-field-mutation hoặc cơ chế tương đương | Kiểm tra toàn bộ JVM flags và manifest; bỏ quyền trong audit |
| Không có JEP 500 warning nhưng object vẫn bị thay đổi | Thư viện có thể dùng cơ chế khác như platform serialization hoặc internal/native path | Kiểm tra implementation, tài liệu và các công cụ chẩn đoán tương ứng |
| Framework tạo object nhưng không cần sửa final field | Framework dùng constructor/factory hoặc API khác | Không cần bật quyền; giữ test deny |
| Lỗi chỉ xảy ra với named module | Package chưa open hoặc caller module chưa được enable | Phân biệt --add-opens với --enable-final-field-mutation |
| Record không thể được ghi final component | Final field của record là non-modifiable | Dùng canonical constructor hoặc tạo record mới |

## 13. Trạng thái và phạm vi áp dụng trong JDK 26/27

JEP 500 là thay đổi hành vi runtime đã được đưa vào JDK 26. JDK 27 tiếp tục cảnh báo các trường hợp deep reflection mutation; đây không phải preview hoặc incubator API.

| Thành phần | Trạng thái |
|---|---|
| JEP 500 trong JDK 26 | Đã triển khai; mặc định warn |
| JEP 500 trong JDK 27 | Tiếp tục warn; có thể dùng debug và deny |
| --enable-final-field-mutation | Cơ chế cấp quyền rõ ràng cho caller module khi thật sự cần |
| --illegal-final-field-mutation | Tùy chọn chuyển tiếp với allow, warn, debug, deny; dự kiến bị loại bỏ trong tương lai |
| Default deny | Là định hướng cho bản phát hành tương lai; không nên tự gán một số phiên bản nếu chưa có thông báo chính thức |

JEP 500 áp dụng cho deep reflection mutation final field qua các mutation method được tài liệu chỉ rõ. Không nhầm thay đổi này với việc mọi trường final đều bị cấm đọc bằng reflection, hoặc mọi thao tác deserialization đều bị chặn.

## 14. Checklist nhận diện thư viện còn sửa final field

- [ ] Đã chạy ứng dụng trên JDK 26 hoặc JDK 27 và lưu warning.
- [ ] Đã chạy --illegal-final-field-mutation=debug để lấy stack trace.
- [ ] Đã xác định caller class, module, JAR và phiên bản dependency.
- [ ] Đã kiểm tra DI, ORM, serializer, mapper, clone utility và test framework.
- [ ] Đã phân biệt deep reflection với cơ chế serialization đặc biệt.
- [ ] Đã kiểm tra trường đích có phải static final, record field hoặc hidden-class field hay không.
- [ ] Đã hiểu --add-opens không tự cấp final field mutation permission.
- [ ] Đã chạy test với --illegal-final-field-mutation=deny và bỏ các quyền enable trong profile audit.
- [ ] Đã nâng cấp hoặc thay thư viện dùng constructor/factory/record khi có thể.
- [ ] Nếu còn cần quyền tạm, đã giới hạn module caller và ghi kế hoạch loại bỏ.
- [ ] Đã giữ strict test trong CI để phát hiện dependency mới tái sử dụng mutation.

## Tài liệu tham khảo

- [JEP 500 — Prepare to Make Final Mean Final](https://openjdk.org/jeps/500): mục tiêu, phạm vi và lộ trình siết final field mutation.
- [Preparing for final Field Mutation Restrictions — Java SE 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html): warning, hai tùy chọn runtime, debug, deny và JFR.
- [JDK 27 Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): xác nhận JDK 27 tiếp tục cảnh báo deep reflection mutation.
- [Java SE 26 Field API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html): điều kiện truy cập và các trường non-modifiable.
- [Java SE 26 Mutation Methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html): các mutation method và quyền final field mutation.
- [Avoiding Final Field Mutation — Inside Java](https://inside.java/2026/04/27/avoiding-final-field-mutation/): các mẫu thay thế cho DI, serialization, cloning và constructor-based initialization.
- [Java SE 26 ObjectInputStream API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/io/ObjectInputStream.html): cơ chế platform serialization và xử lý record.

