# Chế độ mặc định warn trên Java 26 và phạm vi cảnh báo

> **Mốc cập nhật: 27-11-2026.** JEP 500 (Prepare to Make Final Mean Final) bắt đầu phát cảnh báo từ JDK 26. Trong JDK 27, chế độ mặc định vẫn là **--illegal-final-field-mutation=warn**. Đây là thay đổi hành vi của runtime, không phải preview hay incubator feature. Mục tiêu là phát hiện code dùng deep reflection để thay đổi final field trước khi một JDK tương lai mặc định từ chối thao tác đó.

## 1. Vì sao JDK cảnh báo khi sửa final field?

Trong Java, final biểu thị một field chỉ được gán trong quá trình khởi tạo hợp lệ của object hoặc class. Sau khi khởi tạo, chương trình có thể dựa vào giả định rằng giá trị đó không đổi. Giả định này hỗ trợ tính đúng đắn, an toàn khi chia sẻ object giữa các thread và tối ưu hóa của JVM.

Tuy nhiên, một số API reflection có thể vượt qua kiểm tra truy cập thông thường. Code có thể lấy một Field, bật quyền truy cập sâu rồi gọi Field.set(...) để thay đổi một final instance field sau khi constructor đã chạy.

Ví dụ:

~~~java
import java.lang.reflect.Field;

final class RuntimeConfig {
    private final String endpoint;

    RuntimeConfig(String endpoint) {
        this.endpoint = endpoint;
    }

    String endpoint() {
        return endpoint;
    }
}

public class FinalFieldMutationDemo {
    public static void main(String[] args) throws Exception {
        RuntimeConfig config =
                new RuntimeConfig("https://api.initial.example");

        Field field =
                RuntimeConfig.class.getDeclaredField("endpoint");

        if (!field.trySetAccessible()) {
            throw new IllegalStateException(
                    "Cannot access RuntimeConfig.endpoint"
            );
        }

        field.set(config, "https://api.changed.example");

        System.out.println(config.endpoint());
    }
}
~~~

Trên JDK 26/27 với cấu hình mặc định, nếu các điều kiện cho phép mutation được thỏa mãn, chương trình vẫn thực hiện phép gán nhưng JVM phát cảnh báo tương tự:

~~~text
WARNING: Final field endpoint in class RuntimeConfig
has been mutated reflectively by class FinalFieldMutationDemo
in unnamed module @...
WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release
unless final field mutation is enabled
~~~

Giá trị được in ra có thể là endpoint mới. Chế độ warn cho phép thao tác tiếp tục để ứng dụng có thời gian phát hiện và sửa dependency. Cảnh báo cho biết field bị thay đổi và class/module thực hiện thay đổi.

**Cảnh báo xuất hiện khi thực sự ghi final field**, không phải chỉ vì gọi getDeclaredField(), setAccessible(true) hoặc trySetAccessible(). Đọc field bằng reflection cũng không phải hành vi bị JEP 500 cảnh báo.

## 2. Phạm vi chính xác của cảnh báo

JEP 500 tập trung vào việc dùng **deep reflection để ghi final instance field** thông qua các mutation methods của Java Platform, bao gồm:

- Field.set(Object, Object).
- Các biến thể như Field.setInt, setLong, setBoolean, setFloat, setDouble và các phương thức set primitive khác.
- MethodHandles.Lookup.unreflectSetter(Field) để lấy MethodHandle có quyền ghi reflected final field.

Cảnh báo không có nghĩa mọi thao tác reflection đều sai. Cần phân biệt:

| Thao tác | Phạm vi JEP 500 |
|---|---|
| Đọc private/final field bằng Field.get(...) | Không phải mutation; không tạo cảnh báo final-field mutation. |
| Gọi setAccessible(true) hoặc trySetAccessible() | Chỉ bật khả năng bỏ qua kiểm tra truy cập nếu module/package cho phép; bản thân thao tác này không ghi field. |
| Ghi field không có modifier final | Không thuộc cảnh báo này. |
| Gán final field trong constructor hoặc initializer theo Java language rules | Không thuộc deep-reflection mutation. |
| Ghi final instance field của class thường sau khởi tạo bằng reflection | Thuộc phạm vi; mặc định warn trong JDK 26/27 nếu phép ghi được phép. |
| Dùng unreflectSetter để tạo quyền ghi final field | Thuộc nhóm mutation method; JFR có thể ghi nhận. |
| Ghi static final, final field của record hoặc hidden class | Không được phép qua Field.set, kể cả khi bật quyền mutation. |

JEP 500 không thay đổi cách gán field thông thường trong constructor. Ví dụ dưới đây vẫn là cách tạo object immutable hợp lệ:

~~~java
final class User {
    private final String id;
    private final String displayName;

    User(String id, String displayName) {
        this.id = id;
        this.displayName = displayName;
    }
}
~~~

Mục tiêu là bảo vệ cam kết bất biến sau khi object đã được khởi tạo và công bố cho phần còn lại của chương trình.

## 3. Phạm vi cảnh báo: tối đa một lần cho mỗi module

Trong chế độ warn, JVM phát cảnh báo ở lần đầu tiên code trong một module thực hiện final-field mutation bất hợp pháp. Tối đa một warning được phát cho mỗi module, không phải một warning cho từng field và cũng không phải một warning cho từng lần ghi.

Ví dụ:

- Nếu toàn bộ ứng dụng và thư viện chạy trên classpath, chúng thường thuộc unnamed module. Các mutation bất hợp pháp trong module này chỉ tạo tối đa một warning ở chế độ warn.
- Nếu ứng dụng dùng module path, hai module khác nhau cùng thực hiện mutation có thể tạo hai warning riêng.
- Sau warning đầu tiên, các mutation tiếp theo trong cùng module vẫn có thể tiếp tục nhưng không tạo thêm warning ở chế độ warn.

Điều này giúp cảnh báo mặc định không lặp quá nhiều trong log. Tuy nhiên, nó cũng có nghĩa một warning không liệt kê toàn bộ field hoặc call site đang gây vấn đề. Dùng chế độ debug hoặc JFR khi cần tìm tất cả vị trí.

## 4. Bốn chế độ của --illegal-final-field-mutation

JDK 26/27 cung cấp option:

~~~text
--illegal-final-field-mutation=allow|warn|debug|deny
~~~

| Chế độ | Hành vi | Mục đích |
|---|---|---|
| allow | Cho phép illegal final-field mutation, không phát warning. | Chế độ chuyển tiếp tạm thời; không nên giữ lâu dài. |
| warn | Cho phép mutation và phát warning lần đầu trong mỗi module. | Mặc định của JDK 26/27. |
| debug | Cho phép mutation; phát warning và stack trace cho mỗi mutation. | Tìm class, thư viện và call site gây mutation. |
| deny | Từ chối illegal mutation; Field.set(...) ném IllegalAccessException. | Kiểm tra mức sẵn sàng cho default nghiêm ngặt trong JDK tương lai. |

Ví dụ chạy ứng dụng ở chế độ mặc định:

~~~text
java Application
~~~

Chạy để tìm từng call site:

~~~text
java --illegal-final-field-mutation=debug Application
~~~

Chạy để phát hiện dependency không còn tương thích với chính sách tương lai:

~~~text
java --illegal-final-field-mutation=deny Application
~~~

deny hiện chưa phải chế độ mặc định của JDK 27. Tài liệu Oracle cho biết đây là chế độ dự kiến trở thành mặc định trong một release tương lai. Option --illegal-final-field-mutation được thiết kế phục vụ giai đoạn chuyển đổi và dự kiến sẽ bị loại bỏ sau khi default chuyển sang deny.

### 4.1. --enable-final-field-mutation là quyền cho phép có chọn lọc

Option này cấp quyền mutation cho các module được chỉ định:

~~~text
--enable-final-field-mutation=module[,module...]
~~~

Với code chạy trên classpath:

~~~text
java --enable-final-field-mutation=ALL-UNNAMED Application
~~~

Với code chạy trên module path:

~~~text
java --enable-final-field-mutation=app.module,legacy.mapper Application
~~~

Ý nghĩa:

- Chỉ code thuộc module được liệt kê mới được cấp quyền final-field mutation.
- ALL-UNNAMED đại diện cho code thuộc unnamed module, thường là code trên classpath.
- Các module khác vẫn bị xử lý theo --illegal-final-field-mutation.
- Khi module được cấp quyền, các mutation hợp lệ của module đó không còn là illegal mutation và không phát warning tương ứng.
- Option này không làm static final, record final hoặc hidden-class final trở thành field có thể sửa.

Không dùng ALL-UNNAMED một cách mặc định cho ứng dụng production chỉ để làm log sạch. Hãy xác định module nào thực sự cần quyền và vì sao.

## 5. Phân biệt --enable-final-field-mutation với --add-opens

Đây là hai quyền khác nhau:

- --add-opens cho phép code của module khác truy cập sâu vào package, tức là có thể bật setAccessible(true) trong trường hợp phù hợp.
- --enable-final-field-mutation cấp quyền cho module gọi mutation method được phép thay đổi final instance field.

Chỉ thêm --add-opens **không cấp quyền ghi final field**. JEP 500 cố ý tách quyền bỏ qua encapsulation khỏi quyền thay đổi final field.

Với một class trong module khác, ứng dụng có thể cần cả hai điều kiện:

~~~text
java ^
  --add-opens=library.module/com.example.model=app.module ^
  --enable-final-field-mutation=app.module ^
  -m app.module/com.example.Main
~~~

Trong đó:

- library.module/com.example.model là package chứa class khai báo field.
- app.module là module thực hiện deep reflection và mutation.
- --add-opens mở package cho module ứng dụng.
- --enable-final-field-mutation cấp quyền mutation cho module ứng dụng.

Nếu package đã mở hợp lệ hoặc caller và declaring class cùng module, có thể không cần --add-opens. Nhưng quyền mutation vẫn phải được cấp nếu thao tác thuộc phạm vi cần opt-in.

## 6. Điều kiện Field.set có thể ghi final instance field

Trong JDK 27, Field.set(...) chỉ có write access đối với một final field khi **tất cả** điều kiện bắt buộc được thỏa mãn:

1. setAccessible(true) đã thành công trên Field.
2. Final-field mutation đã được bật cho module của code gọi.
3. Có một điều kiện truy cập phù hợp:
   - Declaring class và caller nằm trong cùng module; hoặc
   - Field là public, declaring class là public và package được export tới caller module; hoặc
   - Package khai báo field được open cho caller module.
4. Declaring class không phải record.
5. Declaring class không phải hidden class.
6. Field không phải static.

Nếu thiếu điều kiện, Field.set(...) ném IllegalAccessException. Điều kiện này chặt hơn điều kiện chỉ bật quyền truy cập sâu. Mở package hoặc export package không tự cấp mutation capability.

Ngay cả với final instance field của class thường, Javadoc khuyến nghị việc ghi chỉ có ý nghĩa trong lúc deserialize hoặc tái tạo instance có blank final field, trước khi object được công bố cho phần còn lại của chương trình. Sửa field sau khi object đã được sử dụng có thể tạo hành vi khó dự đoán; một số code có thể tiếp tục quan sát giá trị ban đầu.

### 6.1. Các final field không thể sửa bằng Field.set

| Loại field | Có thể ghi qua Field.set sau setAccessible? | Lý do |
|---|---|---|
| static final trong class hoặc interface | Không | Là non-modifiable final field. |
| Final field khai báo trong record | Không | Record được thiết kế với trạng thái dữ liệu bất biến. |
| Final field khai báo trong hidden class | Không | Không cho phép deep-reflection mutation. |
| Final instance field của class thường | Có điều kiện | Cần setAccessible, module capability và package/module access phù hợp. |
| Non-final instance field | Theo quy tắc reflection/access thông thường | Không thuộc JEP 500 final-field mutation. |

Ngay cả khi dùng --enable-final-field-mutation=ALL-UNNAMED, các loại non-modifiable final field trên vẫn không thể được ghi bằng Field.set.

### 6.2. Ví dụ minh họa phạm vi

~~~java
import java.lang.reflect.Field;

final class OrdinaryConfig {
    private final String endpoint = "https://initial.example";
}

record UserRecord(String id) {}

final class Constants {
    static final String NAME = "fixed";
}

static void tryMutation(Field field, Object target, Object value)
        throws ReflectiveOperationException {

    if (!field.trySetAccessible()) {
        System.out.println("Deep access is not available");
        return;
    }

    field.set(target, value);
}
~~~

Với OrdinaryConfig.endpoint, mutation có thể được cho phép khi caller được cấp quyền và package/module access hợp lệ; ở chế độ warn, JVM phát cảnh báo rồi tiếp tục.

Với UserRecord.id hoặc Constants.NAME, việc bật quyền mutation không biến các field đó thành writable. Field.set vẫn ném IllegalAccessException.

## 7. Cảnh báo xuất hiện ở đâu và đọc thế nào?

Thông báo cảnh báo cho biết:

- Tên final field.
- Class khai báo field.
- Class thực hiện mutation.
- Module của code thực hiện mutation.
- Vị trí hoặc nguồn code của module, thường là tên JAR hoặc module location.

Ví dụ:

~~~text
WARNING: Final field maxCapacity in class com.example.Storage
has been mutated reflectively by class com.example.ResourceLibrary
in unnamed module @...
WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release
unless final field mutation is enabled
~~~

Đừng vội sửa class khai báo field chỉ vì tên field xuất hiện trong warning. Class thực hiện mutation thường là một thư viện mapping, serializer, dependency injection, ORM hoặc framework. Cần xác định call site và phiên bản thư viện trước.

## 8. Tìm code gây mutation bằng debug và JFR

### 8.1. Dùng chế độ debug

Chạy ứng dụng:

~~~text
java --illegal-final-field-mutation=debug Application
~~~

Ở chế độ này, mỗi final-field mutation bất hợp pháp được phép sẽ tạo warning cùng stack trace. Stack trace cho thấy:

- Framework/library nào gọi mutation method.
- Method nào trong library thực hiện ghi.
- Đường gọi từ code ứng dụng tới library.
- Field nào bị thay đổi.

Chế độ này hữu ích trong integration test hoặc staging. Log có thể nhiều nếu framework thực hiện mutation lặp lại.

### 8.2. Dùng Java Flight Recorder

JDK có JFR event jdk.FinalFieldMutation để ghi nhận việc mutation final instance field thông qua deep reflection hoặc việc lấy MethodHandle có write access bằng Lookup.unreflectSetter.

Có thể bật recording khi chạy ứng dụng:

~~~text
java -XX:StartFlightRecording=filename=final-field-mutation.jfr Application
~~~

Sau đó đọc event:

~~~text
jfr print --events jdk.FinalFieldMutation final-field-mutation.jfr
~~~

Event có thể cung cấp:

- Class khai báo field.
- Tên field.
- Thread thực hiện.
- Stack trace của mutation.

JFR phù hợp khi muốn thu thập dữ liệu từ một lần chạy integration hoặc staging mà không cần giữ log debug rất lớn. Kiểm tra cấu hình recording để bảo đảm event được ghi trong profile đang sử dụng.

## 9. Vì sao mutation sau khởi tạo nguy hiểm?

### 9.1. Phá vỡ giả định bất biến

Code nhận một object có final field có thể tin rằng giá trị đó không đổi sau constructor. Nếu một framework thay đổi giá trị sau khi object đã được truyền sang component khác, các component có thể nhìn thấy trạng thái không đồng nhất.

### 9.2. Tối ưu hóa của JVM

JVM có thể tận dụng tính bất biến của final field để tối ưu đọc dữ liệu. Thay đổi field bằng deep reflection sau khi object đã được sử dụng có thể dẫn tới hành vi khó dự đoán, ví dụ một số code tiếp tục quan sát giá trị cũ trong khi code khác đọc giá trị mới.

Không dùng reflection mutation để triển khai hot reload cấu hình. Với cấu hình có thể thay đổi, dùng object snapshot mới và thay thế reference qua cơ chế đồng bộ phù hợp.

### 9.3. An toàn khi chia sẻ giữa các thread

Final-field semantics là một phần của Java Memory Model. Constructor hoàn tất đúng cách có các bảo đảm về khả năng nhìn thấy giá trị final khi object được chia sẻ. Mutation sau constructor không tương đương một lần gán hợp lệ trong constructor và không nên được xem như cách cập nhật trạng thái thread-safe.

## 10. Cách thay thế final-field mutation

| Nhu cầu hiện tại | Cách thiết kế phù hợp |
|---|---|
| Cần thiết lập giá trị khi tạo object | Constructor hoặc static factory. |
| Cần tạo object từ nhiều trường cấu hình | Builder mutable ở giai đoạn xây dựng, sau đó tạo object immutable. |
| Cần dependency injection | Constructor injection; setter chỉ cho dependency thực sự mutable và được thiết kế như vậy. |
| Cần deserialize object | Dùng serialization/deserialization API hoặc constructor/factory được hỗ trợ; không tự ghi final field sau khi object được công bố. |
| Cần thay đổi cấu hình khi runtime | Tạo immutable configuration snapshot mới rồi atomically thay reference. |
| Framework cần hydrate model | Nâng cấp framework hoặc chọn cơ chế construction/hydration được hỗ trợ. |

Ví dụ dùng builder để tạo immutable object:

~~~java
final class ServiceConfig {
    private final String endpoint;
    private final int timeoutSeconds;

    private ServiceConfig(Builder builder) {
        this.endpoint = builder.endpoint;
        this.timeoutSeconds = builder.timeoutSeconds;
    }

    String endpoint() {
        return endpoint;
    }

    int timeoutSeconds() {
        return timeoutSeconds;
    }

    static final class Builder {
        private String endpoint;
        private int timeoutSeconds = 3;

        Builder endpoint(String endpoint) {
            this.endpoint = endpoint;
            return this;
        }

        Builder timeoutSeconds(int timeoutSeconds) {
            this.timeoutSeconds = timeoutSeconds;
            return this;
        }

        ServiceConfig build() {
            if (endpoint == null || endpoint.isBlank()) {
                throw new IllegalStateException("endpoint is required");
            }
            return new ServiceConfig(this);
        }
    }
}
~~~

Builder có thể thay đổi trong giai đoạn chuẩn bị. Khi build() tạo ServiceConfig, các final field được gán trong constructor và không cần reflection mutation.

## 11. Quy trình migration trên JDK 26/27

Thực hiện theo các bước sau để xử lý warning trước khi JDK chuyển sang default deny:

1. **Chạy với cấu hình mặc định.** Dùng JDK 26 hoặc 27 và ghi lại warning trong unit, integration và staging tests.
2. **Xác định module gây warning.** Đọc field, mutator class và module trong thông báo. Kiểm tra dependency tree để tìm JAR chứa thư viện đó.
3. **Dùng debug hoặc JFR.** Nếu một module có nhiều mutation, chạy --illegal-final-field-mutation=debug hoặc thu thập jdk.FinalFieldMutation events.
4. **Nâng cấp thư viện.** Kiểm tra release của framework/ORM/serializer/dependency injection để tìm phiên bản không còn sửa final field qua deep reflection.
5. **Thay đổi mô hình khởi tạo.** Dùng constructor, factory, builder hoặc immutable snapshot. Không bỏ modifier final nếu field thực sự phải bất biến chỉ để che warning.
6. **Kiểm tra với deny.** Chạy --illegal-final-field-mutation=deny trong CI/staging. Chỉ cấp quyền cho module có ngoại lệ đã được xác định rõ và thật sự cần thiết.
7. **Thu hẹp ngoại lệ.** Nếu không thể thay thế thư viện, dùng --enable-final-field-mutation cho đúng module cần quyền; tránh cấp cho toàn bộ code trên classpath khi không cần.
8. **Loại bỏ option chuyển tiếp.** Khi dependency đã được sửa, bỏ các option --illegal-final-field-mutation=allow, debug hoặc quyền enable tạm thời khỏi cấu hình production.

### 11.1. Ma trận kiểm tra

| Cấu hình | Mutation từ module chưa được enable | Kết quả mong đợi |
|---|---|---|
| JDK 26/27, mặc định | Thực hiện nếu các điều kiện truy cập khác hợp lệ | Warning lần đầu trong module, thao tác vẫn tiếp tục. |
| --illegal-final-field-mutation=warn | Thực hiện nếu hợp lệ | Cùng hành vi mặc định. |
| --illegal-final-field-mutation=debug | Thực hiện nếu hợp lệ | Warning và stack trace cho từng mutation. |
| --illegal-final-field-mutation=allow | Thực hiện nếu hợp lệ | Không cảnh báo. |
| --illegal-final-field-mutation=deny | Bị từ chối | Field.set ném IllegalAccessException. |
| Module caller nằm trong --enable-final-field-mutation | Được cấp quyền nếu package/field đáp ứng các điều kiện còn lại | Không phải illegal mutation; không có warning tương ứng. |
| Static final / record final / hidden-class final | Không thể ghi qua Field.set | IllegalAccessException, kể cả khi enable. |

## 12. Những nhầm lẫn cần tránh

- **Nhầm warn là chặn mutation.** Trong JDK 26/27, warn cho phép mutation tiếp tục sau khi phát warning.
- **Nhầm một warning là chỉ có một field bị sửa.** Warning chỉ phát tối đa một lần cho mỗi module; nhiều field/call site vẫn có thể tồn tại.
- **Nhầm setAccessible là quyền ghi final.** Nó chỉ xử lý kiểm tra truy cập. Quyền final-field mutation là điều kiện riêng.
- **Nhầm add-opens thay thế enable-final-field-mutation.** Mở package không cấp capability ghi final field.
- **Nhầm enable có thể sửa static final hoặc record component.** Các loại field này vẫn non-modifiable.
- **Nhầm mọi final field đều không thể ghi trong mọi hoàn cảnh.** JDK 26/27 vẫn cho phép có điều kiện với final instance field của class thường.
- **Nhầm --illegal-final-field-mutation=deny là default JDK 27.** Default hiện tại vẫn là warn.
- **Dùng allow như cấu hình production dài hạn.** Allow chỉ tắt cảnh báo; nó không giải quyết dependency đang phá vỡ tính toàn vẹn của final field.

## 13. Bài tập thực hành

Thực hiện trên JDK 27 với classpath hoặc module path mà bạn kiểm soát:

1. Tạo một class thường có private final instance field và một class dùng reflection để ghi field đó.
2. Chạy không có option; ghi nhận warning và xác nhận mutation vẫn được thực hiện.
3. Chạy lại với --illegal-final-field-mutation=debug; xác định stack trace của call site.
4. Chạy với --illegal-final-field-mutation=deny; xác nhận Field.set bị từ chối bằng IllegalAccessException.
5. Chạy với --enable-final-field-mutation=ALL-UNNAMED; xác nhận warning được bỏ qua khi caller thuộc unnamed module và các điều kiện khác hợp lệ.
6. Tạo một record có component final; thử mutation và xác nhận vẫn thất bại dù đã enable.
7. Tạo static final field; thử mutation và xác nhận nó không thể được ghi.
8. Chạy ứng dụng với JFR, in event jdk.FinalFieldMutation và xác định field/call stack.
9. Thay reflection mutation bằng constructor hoặc builder; chạy lại với deny và xác nhận ứng dụng vẫn hoạt động.
10. Lặp lại trên module path; phân biệt caller module, target package open và mutation capability.

## 14. Checklist trước khi phát hành

- [ ] Ứng dụng đã được chạy trên JDK 26/27 với chế độ mặc định warn.
- [ ] Mọi warning đã được quy về class, module và dependency cụ thể.
- [ ] Đã kiểm tra các thư viện serialization, ORM, dependency injection và mapping.
- [ ] Không dựa vào deep reflection để sửa final field sau khi object đã được công bố.
- [ ] Đã phân biệt package openness với quyền final-field mutation.
- [ ] Đã xác nhận static final, record final và hidden-class final không thể sửa.
- [ ] Đã chạy test với --illegal-final-field-mutation=deny.
- [ ] Mọi quyền enable còn lại được giới hạn ở module thực sự cần.
- [ ] Không dùng allow để che warning trong production.
- [ ] Có kiểm thử migration khi nâng cấp JDK tiếp theo.

## Tài liệu tham khảo chính thức

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500)
- [Significant Changes in JDK 26 Release](https://docs.oracle.com/en/java/javase/26/migrate/significant-changes-jdk-26-release.html)
- [Significant Changes in JDK 27 Release](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html)
- [Preparing for final Field Mutation Restrictions](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html)
- [The java Command — JDK 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html)
- [Field API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/Field.html)
- [AccessibleObject API — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/AccessibleObject.html)
- [Mutation methods — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html)

