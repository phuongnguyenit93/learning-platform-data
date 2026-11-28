# Cảnh báo sửa final bằng deep reflection từ Java 26

## Mục tiêu

Sau bài học này, bạn có thể:

- Giải thích vì sao sửa một field `final` sau khi đối tượng được khởi tạo làm suy yếu tính toàn vẹn của chương trình.
- Nhận biết những thao tác reflection có thể ghi vào final instance field.
- Hiểu cảnh báo mới của JDK 26 theo JEP 500 và phạm vi field bị ảnh hưởng.
- Phân biệt quyền truy cập deep reflection với quyền được phép mutate final field.
- Dùng `--illegal-final-field-mutation` để phát hiện thư viện còn sửa final field.
- Chỉ bật `--enable-final-field-mutation` cho module thật sự cần thiết trong giai đoạn chuyển đổi.
- Kiểm thử ứng dụng với chế độ `deny` và thay thế các cách sửa final bằng thiết kế phù hợp.

## 1. Vì sao final field cần được bảo vệ?

Trong Java, `final` biểu thị rằng một field chỉ được gán trong quá trình khởi tạo hợp lệ. Với field instance, giá trị thường được thiết lập trong khai báo field hoặc constructor rồi giữ nguyên trong suốt vòng đời đối tượng.

~~~java
final class ServerConfig {
    private final String host;
    private final int port;

    ServerConfig(String host, int port) {
        this.host = host;
        this.port = port;
    }

    String host() {
        return host;
    }

    int port() {
        return port;
    }
}
~~~

Khi một đối tượng đã được tạo, các phần khác của chương trình có thể dựa vào giả định rằng `host` và `port` không thay đổi. Điều này hỗ trợ:

- **Tính đúng đắn:** trạng thái cấu hình không bất ngờ thay đổi sau khi được kiểm tra.
- **An toàn luồng:** final field được hưởng các bảo đảm về khởi tạo và công bố an toàn theo Java Memory Model nếu đối tượng được tạo đúng cách.
- **Tối ưu JVM:** compiler và JIT có thể dựa vào tính ổn định của final field để tối ưu đọc và sử dụng giá trị.
- **An toàn:** thư viện hoặc mã không đáng tin cậy khó sửa các bất biến nội bộ của đối tượng sau khi nó đã được tạo.

Tuy nhiên, trong nhiều năm, deep reflection có thể vượt qua giới hạn này. Mã có quyền truy cập sâu vào field có thể gọi `setAccessible(true)`, rồi dùng `Field.set(...)` để sửa một số final instance field sau constructor. Cách này làm suy yếu ý nghĩa của `final` và khiến runtime khó dựa vào các bất biến mà ngôn ngữ và JMM cung cấp.

## 2. Deep reflection có thể sửa final field như thế nào?

Deep reflection cho phép mã truy cập thành viên private hoặc thành viên nằm trong package không được export, nếu điều kiện mở package và quyền truy cập được đáp ứng.

Ví dụ dưới đây minh họa cách cũ dùng reflection để sửa một final instance field:

~~~java
import java.lang.reflect.Field;

final class UserConfig {
    private final String role;

    UserConfig(String role) {
        this.role = role;
    }

    String role() {
        return role;
    }
}

public class FinalFieldMutationDemo {
    public static void main(String[] args) throws Exception {
        UserConfig config = new UserConfig("reader");

        Field role = UserConfig.class.getDeclaredField("role");
        role.setAccessible(true);
        role.set(config, "administrator");

        System.out.println(config.role());
    }
}
~~~

Trên JDK 26, nếu quyền mutate final field chưa được cấp cho module gọi reflection, thao tác trên vẫn được phép trong chế độ mặc định nhưng JVM phát cảnh báo. Với ví dụ chạy trên class path, module gọi là unnamed module; cảnh báo xuất hiện tối đa một lần cho module đó.

Không nên xem ví dụ này là kỹ thuật cấu hình đối tượng được khuyến nghị. Nó chỉ minh họa hành vi mà JEP 500 đang đưa vào lộ trình hạn chế.

## 3. JEP 500 thay đổi điều gì trong JDK 26?

JEP 500 có tên **Prepare to Make Final Mean Final**. JDK 26 bắt đầu cảnh báo khi mã dùng deep reflection để mutate final field mà module gọi chưa được cấp quyền rõ ràng.

Ví dụ cảnh báo có dạng:

~~~text
WARNING: Final field role in class com.example.UserConfig
has been mutated reflectively by class com.example.LegacyMapper
in unnamed module @...

WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release
unless final field mutation is enabled
~~~

Thông báo giúp xác định:

- Field nào bị sửa.
- Class nào khai báo field đó.
- Class/module nào thực hiện thao tác mutate.
- Tùy chọn dùng để cấp quyền tường minh nếu trường hợp đó thật sự cần thiết.

JDK 26 mặc định dùng chế độ `warn`: thao tác mutate trái phép vẫn được thực hiện, nhưng warning được phát ra ở lần đầu tiên một module thực hiện hành vi này. Tối đa một warning được phát ra cho mỗi module gọi, không phải một warning cho từng field.

Đây là giai đoạn chuẩn bị. Trong một release tương lai, hành vi mặc định sẽ chuyển sang từ chối mutate final field nếu module gọi chưa được cấp quyền. JEP 500 hướng tới bảo đảm tính toàn vẹn của final field theo mặc định.

## 4. Phạm vi: thao tác và loại field nào bị ảnh hưởng?

Các mutation methods trong Java SE có thể ghi vào non-static final field gồm:

- `Field.set(Object, Object)`
- `Field.setBoolean(Object, boolean)`
- `Field.setByte(Object, byte)`
- `Field.setChar(Object, char)`
- `Field.setInt(Object, int)`
- `Field.setLong(Object, long)`
- `Field.setFloat(Object, float)`
- `Field.setDouble(Object, double)`
- `MethodHandles.Lookup.unreflectSetter(Field)`

JEP 500 tập trung vào khả năng mutate **final instance field** sau khi đối tượng đã được khởi tạo. Các trường hợp cần phân biệt:

| Trường hợp | Khả năng mutate qua các mutation methods |
|---|---|
| Final instance field của class thông thường | Có thể được phép nếu đáp ứng các điều kiện truy cập và quyền mutate |
| Static final field | Không được phép mutate theo cơ chế này |
| Final field của record | Không được phép mutate theo cơ chế này |
| Final field của hidden class | Không được phép mutate theo cơ chế này |
| Đọc final field bằng reflection | Không phải hành vi mutate mà JEP 500 đang cảnh báo |
| Gọi `Field.set` trên field không final | Không thuộc hạn chế final field mutation này |

`setAccessible(true)` không làm cho mọi final field đều có thể ghi. Các giới hạn hiện có đối với static final field, record và hidden class vẫn được áp dụng.

JEP 500 cũng không biến mọi truy cập reflection thành lỗi. Việc đọc field, gọi method hoặc truy cập thành viên không final vẫn chịu các quy tắc reflection và strong encapsulation hiện hành.

## 5. Hai điều kiện độc lập: mở package và cấp quyền mutate

Đây là điểm quan trọng nhất khi xử lý cảnh báo.

Để một module dùng deep reflection mutate final instance field trong JDK 26, cần phân biệt hai lớp quyền:

1. **Quyền truy cập sâu:** package chứa class khai báo field phải được mở cho module thực hiện reflection. Với named module, điều này có thể cần `opens` trong module descriptor hoặc `--add-opens` khi chạy.
2. **Quyền mutate final field:** module thực hiện thao tác phải được cấp quyền bằng `--enable-final-field-mutation`.

Hai quyền này không thay thế cho nhau.

- `--add-opens` cho phép deep reflection tiếp cận thành viên trong package; nó không tự cấp quyền mutate final field theo JEP 500.
- `--enable-final-field-mutation` cấp quyền cho module gọi mutate final instance field trong package đã mở; nó không tự mở package và không vượt qua strong encapsulation.
- Chỉ gọi `setAccessible(true)` không có nghĩa module đã được cấp quyền mutate final field.

Ví dụ, ứng dụng có named module `legacy.mapper` cần sửa final instance field thuộc package `com.example.model` trong module `domain.model`:

~~~bash
java \
  --add-opens=domain.model/com.example.model=legacy.mapper \
  --enable-final-field-mutation=legacy.mapper \
  -m app.main/com.example.Main
~~~

Cú pháp minh họa trên cần điều chỉnh theo module name, package và main module thật của ứng dụng. Chỉ mở đúng package cho đúng module gọi. Không mở rộng thành `ALL-UNNAMED` hoặc `ALL-MODULE-PATH` nếu không có lý do cụ thể.

## 6. Các chế độ của --illegal-final-field-mutation

Tùy chọn này quyết định JVM xử lý các lần mutate final field không có quyền tường minh như thế nào:

| Giá trị | Hành vi |
|---|---|
| `allow` | Cho phép mutate mà không cảnh báo |
| `warn` | Cho phép mutate và cảnh báo ở lần đầu tiên mỗi module thực hiện |
| `debug` | Cho phép mutate, phát warning và stack trace cho từng lần mutate |
| `deny` | Từ chối mutate; `Field.set` ném `IllegalAccessException` |

Trong JDK 26:

- `warn` là mặc định.
- `allow`, `warn` và `debug` phục vụ giai đoạn chuyển đổi.
- `deny` có thể được bật sớm để phát hiện lỗi tương thích trước khi hành vi này trở thành mặc định trong release tương lai.
- Tùy chọn `--illegal-final-field-mutation` là cơ chế chuyển tiếp và sẽ bị loại bỏ trong một release tương lai.

Ví dụ chạy chế độ mặc định tường minh:

~~~bash
java --illegal-final-field-mutation=warn -jar app.jar
~~~

Để tìm mọi nơi đang mutate và lấy stack trace:

~~~bash
java --illegal-final-field-mutation=debug -jar app.jar
~~~

Để kiểm tra khả năng chạy khi final field mutation bị từ chối:

~~~bash
java --illegal-final-field-mutation=deny -jar app.jar
~~~

Chế độ `allow` chỉ nên là biện pháp tạm thời khi cần giữ ứng dụng hoạt động trong lúc xác định dependency cần thay thế. Không nên đưa nó thành cấu hình lâu dài.

## 7. Cấp quyền có chọn lọc bằng --enable-final-field-mutation

Nếu một thư viện cũ chưa thể thay thế và thực sự cần mutate final instance field, ứng dụng có thể cấp quyền rõ ràng cho module gọi.

### Mã chạy trên class path

Các class trên class path thuộc unnamed module. Có thể cấp quyền cho toàn bộ code class path:

~~~bash
java --enable-final-field-mutation=ALL-UNNAMED -jar app.jar
~~~

Tùy chọn này có phạm vi rộng: mọi code trên class path đều được cấp quyền mutate final instance field khi package đích đã mở cho nó. Chỉ dùng nếu đã xác định dependency cần thiết và không thể giới hạn module hẹp hơn.

### Mã chạy trên module path

Chỉ định module thực hiện mutation:

~~~bash
java --enable-final-field-mutation=legacy.mapper,legacy.serializer \
     -m app.main/com.example.Main
~~~

Các module không nằm trong danh sách vẫn bị xem là không được cấp quyền. Cần nhớ rằng package khai báo field cũng phải mở cho module tương ứng.

### Kết hợp quyền với chế độ deny

Có thể bật chế độ nghiêm ngặt cho toàn hệ thống nhưng cho phép một số module đã được duyệt:

~~~bash
java \
  --enable-final-field-mutation=legacy.mapper \
  --illegal-final-field-mutation=deny \
  -m app.main/com.example.Main
~~~

Trong cấu hình này, module `legacy.mapper` vẫn có thể mutate final instance field nếu package đích đã mở cho nó. Những module khác không có quyền sẽ bị từ chối.

Mục tiêu của `--enable-final-field-mutation` là tạo một ngoại lệ có chủ đích và có thể kiểm tra. Nó không phải cách thay thế cho việc cập nhật thư viện.

## 8. Tìm thư viện nào đang mutate final field

Cảnh báo thường xuất phát từ thư viện framework, serializer, mapper, dependency injection hoặc công cụ test chứ không nhất thiết từ code nghiệp vụ trực tiếp.

Quy trình tìm nguyên nhân:

1. Chạy ứng dụng bằng JDK 26 với cấu hình mặc định hoặc `--illegal-final-field-mutation=debug`.
2. Thu thập warning và stack trace trong các luồng nghiệp vụ quan trọng.
3. Xác định module gọi, JAR, phiên bản thư viện, class và field bị sửa.
4. Tìm phiên bản thư viện mới đã bỏ cách mutate final field.
5. Nếu chưa có bản sửa, báo upstream hoặc thay thế thư viện; chỉ cấp quyền tạm thời khi có đánh giá rõ ràng.
6. Chạy lại với `--illegal-final-field-mutation=deny` để xác nhận các đường chạy đã được xử lý.

### Dùng JDK Flight Recorder

Khi JFR được bật, JDK ghi sự kiện `jdk.FinalFieldMutation` cho thao tác mutate final instance field qua deep reflection và trường hợp tạo MethodHandle setter bằng `Lookup.unreflectSetter(Field)`. Sự kiện ghi class khai báo field, tên field, thread và stack trace.

Bắt đầu ứng dụng với JFR:

~~~bash
java -XX:StartFlightRecording:filename=final-field-audit.jfr \
     -jar app.jar
~~~

Sau khi ứng dụng chạy qua các luồng cần kiểm tra, đọc sự kiện:

~~~bash
jfr print --events jdk.FinalFieldMutation final-field-audit.jfr
~~~

Có thể kết hợp JFR với `--enable-final-field-mutation` nếu cần quan sát các mutation đã được cấp quyền. Đừng dùng `deny` cho cùng một lần đo nếu mục tiêu là ghi nhận mutation thành công, vì thao tác bị từ chối không tạo ra một lần mutate thành công.

## 9. Thay deep reflection mutation bằng thiết kế phù hợp

Cách sửa bền vững là loại bỏ nhu cầu thay đổi final field sau khi constructor đã chạy.

| Nhu cầu trước đây | Hướng thay thế |
|---|---|
| Deserialize bằng cách tạo object rỗng rồi ghi vào final field | Dùng constructor/canonical constructor hoặc factory được framework hỗ trợ |
| Dependency injection ghi trực tiếp private final field | Dùng constructor injection |
| Mapper ghi vào final field của domain object | Tạo object qua constructor, builder hoặc factory |
| Test thay final field để ép trạng thái | Tạo fixture qua constructor/factory hoặc inject dependency giả |
| Cập nhật cấu hình sau khi object đã tạo | Tạo immutable config instance mới rồi thay reference ở component quản lý |
| Framework cần khôi phục object từ dữ liệu | Dùng API serialization/deserialization chính thức và phiên bản framework tương thích JDK |

### Constructor injection

Thay vì để framework tạo object rồi mutate field:

~~~java
final class PaymentService {
    private final PaymentGateway gateway;

    PaymentService(PaymentGateway gateway) {
        this.gateway = Objects.requireNonNull(gateway);
    }
}
~~~

Framework nên gọi constructor với dependency cần thiết. Field vẫn final và trạng thái hoàn chỉnh ngay khi object được tạo.

### Tạo immutable configuration mới

Nếu cấu hình cần thay đổi theo thời gian, đừng mutate final field của object hiện tại. Hãy tạo một giá trị mới:

~~~java
record AppConfig(String endpoint, Duration timeout) {}

final class ConfigHolder {
    private volatile AppConfig current;

    ConfigHolder(AppConfig initial) {
        this.current = initial;
    }

    AppConfig current() {
        return current;
    }

    void reload(AppConfig next) {
        current = Objects.requireNonNull(next);
    }
}
~~~

Ở đây object `AppConfig` vẫn immutable; holder thay reference tới cấu hình mới. Đây là một thiết kế khác với việc sửa field final bên trong object đã tồn tại.

## 10. Các hiểu nhầm thường gặp

- **“Có setAccessible(true) là sửa được final.”** Không đúng. Deep reflection access và quyền mutate final field là hai điều kiện riêng; JDK 26 thêm cơ chế cấp quyền mutate.
- **“Thêm --add-opens là hết warning.”** Không đúng. Mở package cho phép truy cập sâu, nhưng không cấp quyền mutate final field theo JEP 500.
- **“JDK 26 đã chặn hoàn toàn việc sửa final.”** Không đúng. Mặc định JDK 26 cảnh báo và vẫn cho phép thao tác trái phép; chế độ `deny` mới từ chối.
- **“Cấp quyền cho module là mở mọi package.”** Không đúng. Package khai báo field vẫn phải mở cho module gọi.
- **“ALL-UNNAMED chỉ cho một thư viện.”** Không đúng. Nó cấp quyền cho code thuộc mọi unnamed module, thường bao gồm toàn bộ class path.
- **“Mọi final field đều có thể mutate nếu được cấp quyền.”** Không đúng. Static final, record final field và hidden class final field không nằm trong phạm vi mutate được hỗ trợ.
- **“Warning chỉ là log có thể bỏ qua.”** Không nên. Đây là tín hiệu dependency đang dựa vào hành vi sẽ bị hạn chế trong release tương lai.

## 11. Checklist nâng cấp ứng dụng lên JDK 26

- [ ] Chạy test và các luồng nghiệp vụ đại diện trên JDK 26.
- [ ] Thu thập warning mặc định về final field mutation.
- [ ] Dùng `--illegal-final-field-mutation=debug` để lấy stack trace khi cần.
- [ ] Dùng JFR và lọc sự kiện `jdk.FinalFieldMutation` để kiểm tra mutation trong các luồng chạy dài.
- [ ] Xác định module gọi và phiên bản thư viện chịu trách nhiệm.
- [ ] Nâng cấp, thay thế hoặc sửa thư viện để không mutate final field.
- [ ] Không coi `--add-opens` là cách xử lý cảnh báo.
- [ ] Chỉ dùng `--enable-final-field-mutation` cho module thật sự cần và đã được đánh giá.
- [ ] Chạy với `--illegal-final-field-mutation=deny` cùng các quyền ngoại lệ đã được phê duyệt.
- [ ] Loại bỏ dần các tùy chọn chuyển tiếp trước khi nâng cấp lên release có mặc định nghiêm ngặt hơn.

## 12. Trạng thái và tác động tới ứng dụng

JEP 500 được triển khai trong JDK 26. Đây là thay đổi về hành vi runtime đối với deep reflection mutate final field, không phải preview feature và không cần `--enable-preview`.

Các tùy chọn liên quan là cờ JVM:

- `--illegal-final-field-mutation` dùng để điều khiển cách xử lý các lần mutate không được cấp quyền trong giai đoạn chuyển đổi.
- `--enable-final-field-mutation` dùng để cấp quyền rõ ràng cho module gọi trong trường hợp ngoại lệ.
- `--add-opens` vẫn là cơ chế riêng để mở package cho deep reflection theo module system.

JDK 26 mặc định cảnh báo; một release tương lai sẽ chuyển mặc định sang từ chối mutation không được cấp quyền. Không nên gắn mã ứng dụng với các cờ chuyển tiếp này như một hợp đồng lâu dài. Hãy nâng cấp thư viện và loại bỏ hành vi mutate final field trước khi nâng cấp JDK tiếp theo.

## Kết luận

Từ JDK 26, deep reflection mutate final instance field không còn là hành vi âm thầm: JVM phát warning cho lần đầu một module thực hiện mutation trái phép. JEP 500 tách quyền mở package cho deep reflection khỏi quyền mutate final field được cấp bằng `--enable-final-field-mutation`. Dùng `--illegal-final-field-mutation=debug` hoặc JFR để tìm thư viện gây ra mutation, rồi ưu tiên nâng cấp hoặc thay thế thư viện. Kiểm thử với `deny` giúp chuẩn bị cho release tương lai khi từ chối mutation sẽ trở thành mặc định. Giữ final field bất biến từ lúc khởi tạo là hướng thiết kế an toàn và phù hợp với mục tiêu của Java 26.

## Tài liệu tham khảo

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
- [Oracle JDK 26 Migration Guide – Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
- [Java SE 26 API – Mutation methods](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html)
- [Java 26 java Command – --enable-final-field-mutation and --illegal-final-field-mutation](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html)
- [JEP 500 – Quality Outreach Heads-up: JDK 26 warnings](https://inside.java/2026/05/15/quality-heads-up/)
- [Avoiding Final Field Mutation – Inside Java](https://inside.java/2026/04/27/avoiding-final-field-mutation/)
