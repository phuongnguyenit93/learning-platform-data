# `--illegal-final-field-mutation` cho kiểm tra, chẩn đoán theo JDK đích

Từ JDK 26, khi một thư viện dùng deep reflection để thay đổi giá trị của field `final` sau khi object đã được khởi tạo, JVM phát cảnh báo theo mặc định. Thay đổi này thuộc JEP 500 — Prepare to Make Final Mean Final. Mục tiêu là giúp ứng dụng phát hiện những dependency đang phá vỡ tính bất biến mà Java hứa hẹn với `final`, trước khi một JDK tương lai từ chối các thao tác đó mặc định.

Tùy chọn `--illegal-final-field-mutation` giúp kiểm tra hành vi này theo chính sách của runtime. Với JDK 26 và JDK 27, chế độ mặc định là `warn`: thao tác bất hợp lệ vẫn được phép tiếp tục nhưng JVM phát cảnh báo lần đầu theo từng module gọi. Có thể chạy `debug` để tìm stack trace, hoặc `deny` để thử trước hành vi nghiêm ngặt hơn của JDK tương lai. Tùy chọn này là công cụ chuyển đổi tạm thời; tài liệu JDK ghi rõ nó sẽ bị loại bỏ trong một release tương lai.

## Mục tiêu học tập

Sau bài này, bạn có thể:

- Giải thích vì sao sửa field `final` sau khởi tạo làm suy yếu tính toàn vẹn, an toàn và khả năng tối ưu của JVM.
- Phân biệt quyền truy cập reflection với quyền được phép thay đổi field `final`.
- Dùng `--illegal-final-field-mutation=warn`, `debug`, `deny` và hiểu vai trò tạm thời của `allow`.
- Phân biệt `--illegal-final-field-mutation` với `--enable-final-field-mutation` và `--add-opens`.
- Kiểm tra ứng dụng bằng JDK 26/27 theo runtime đích, thu thập warning, stack trace và JFR event.
- Xác định dependency gây mutation và chọn cách sửa tương thích lâu dài.

## 1. Vì sao Java siết việc thay đổi field `final`?

Một field `final` được gán trong khai báo, initializer hoặc constructor. Sau khi object được tạo, chương trình có thể dựa vào giả định giá trị đó không thay đổi. Giả định này giúp mã nguồn dễ suy luận hơn, hỗ trợ an toàn khi chia sẻ object giữa các thread và cho phép JVM tối ưu việc đọc field.

Deep reflection từng cho phép thư viện bỏ qua một phần đóng gói để đọc và ghi field private. Ví dụ, một thư viện có thể gọi `setAccessible(true)` rồi dùng `Field.set(...)` để sửa field `final` sau constructor. Điều đó tạo ra các rủi ro:

- **Phá vỡ bất biến của object:** constructor có thể đã kiểm tra dữ liệu và xây dựng trạng thái nhất quán, nhưng thư viện khác sửa một field sau đó mà không chạy lại các kiểm tra.
- **Khó suy luận về đồng thời:** code khác có thể đã đọc hoặc chia sẻ object với giả định field không đổi. Việc sửa sau khi công bố object có thể khiến các phần của chương trình quan sát trạng thái không nhất quán.
- **Làm suy yếu tối ưu hóa:** JIT có thể tối ưu dựa trên giả định final field không bị thay đổi. Nếu giả định bị phá vỡ, JVM phải thận trọng hơn với các tối ưu như constant folding và việc giữ giá trị đã đọc.
- **Tăng bề mặt tấn công:** một dependency có quyền deep reflection có thể thay đổi cấu hình, danh tính hoặc trạng thái mà ứng dụng kỳ vọng là bất biến.

JEP 500 triển khai cách tiếp cận “integrity by default”: ứng dụng phải chủ động cho phép module nào được sửa final field qua deep reflection. JDK 26 bắt đầu bằng cảnh báo để nhóm phát triển tìm dependency cần nâng cấp hoặc thay thế; một JDK tương lai sẽ chuyển mặc định sang từ chối.

## 2. Thao tác nào được kiểm soát?

JEP 500 tập trung vào việc thay đổi **final instance field sau khi object đã được khởi tạo** thông qua deep reflection và các mutation method liên quan. Những API quan trọng gồm:

- `Field.set(Object, Object)`.
- Các phương thức kiểu nguyên thủy như `Field.setInt`, `setLong`, `setBoolean`, `setByte`, `setChar`, `setShort`, `setFloat` và `setDouble`.
- `MethodHandles.Lookup.unreflectSetter(Field)` để tạo MethodHandle có quyền ghi field.

Ví dụ một thư viện thay đổi cấu hình sau khi object đã được tạo:

```java
final class ServiceConfig {
    private final String endpoint;

    ServiceConfig(String endpoint) {
        this.endpoint = endpoint;
    }

    String endpoint() {
        return endpoint;
    }
}

public class FinalFieldMutationDemo {
    public static void main(String[] args) throws Exception {
        ServiceConfig config = new ServiceConfig("https://prod.example");

        var field = ServiceConfig.class.getDeclaredField("endpoint");
        if (!field.trySetAccessible()) {
            throw new IllegalStateException("Không thể mở quyền truy cập field");
        }

        field.set(config, "https://test.example");
        System.out.println(config.endpoint());
    }
}
```

Trên JDK 26 hoặc JDK 27 với cấu hình mặc định, thao tác trong ví dụ được phép tiếp tục nhưng tạo warning vì module gọi chưa được cấp quyền final-field mutation. Nếu chạy với `--illegal-final-field-mutation=deny`, `Field.set` thất bại bằng `IllegalAccessException`.

Không phải mọi cách gán field `final` đều bị ảnh hưởng. Gán giá trị trong khai báo field, instance initializer hoặc constructor là cách khởi tạo bình thường của Java. Thay đổi này nhắm vào việc dùng reflection sau khởi tạo để sửa field.

Một số loại field vốn không thể được sửa bằng các mutation method này:

- `static final` field.
- Final field của record class.
- Final field của hidden class.

`--enable-final-field-mutation` không biến các loại field này thành field có thể sửa. Nó chỉ cấp quyền cho các trường hợp final instance field được hỗ trợ và thỏa các điều kiện truy cập khác.

## 3. Hai cổng kiểm tra: truy cập được và được phép mutation

`setAccessible(true)` thành công không còn đồng nghĩa rằng có thể sửa field `final`. Cần phân biệt hai câu hỏi:

1. **Reflection có được phép truy cập member không?** Điều này phụ thuộc access control, module và package openness. Nếu không thể bật quyền truy cập, `trySetAccessible()` trả `false` hoặc `setAccessible(true)` có thể ném `InaccessibleObjectException`.
2. **Module đang gọi có được cấp quyền sửa final field không?** Từ JDK 26, module gọi cần được cấp final-field mutation capability. Nếu không, thao tác bị xem là illegal và `--illegal-final-field-mutation` quyết định JVM cảnh báo, cho phép hoặc từ chối.

Với một final instance field thông thường, các điều kiện liên quan gồm:

- `setAccessible(true)` đã thành công cho `Field` đó.
- Module của code thực hiện mutation được bật final-field mutation.
- Field thuộc class thông thường, không phải record hoặc hidden class.
- Field không phải `static`.
- Quy tắc module/package access cho phép caller truy cập: cùng module, trường hợp public/export phù hợp, hoặc package được mở cho module gọi theo điều kiện của API.

Do đó, `--add-opens` và `--enable-final-field-mutation` không thay thế nhau:

| Cấu hình | Vai trò | Có tự cấp quyền sửa `final` không? |
|---|---|---|
| `--add-opens=module/package=caller` | Mở package cho deep reflection | Không |
| `--enable-final-field-mutation=caller` | Cấp capability final-field mutation cho module gọi | Không tự mở package |
| Cả hai cùng phù hợp | Thỏa điều kiện module/package và capability | Có thể cho phép sửa final instance field được hỗ trợ |
| `--illegal-final-field-mutation=deny` | Từ chối các mutation bị xem là illegal | Không cấp quyền; chỉ chọn cách xử lý khi thiếu quyền |

Trong ứng dụng classpath, caller thuộc unnamed module; giá trị thường dùng để cấp capability là `ALL-UNNAMED`. Với ứng dụng module path, chỉ định chính xác tên module chứa code thực hiện mutation. Không cấp quyền cho module khai báo field nếu thư viện khác mới là caller thực hiện `Field.set`.

## 4. Các chế độ của `--illegal-final-field-mutation`

Tùy chọn được đặt khi khởi chạy JVM:

```text
--illegal-final-field-mutation=allow
--illegal-final-field-mutation=warn
--illegal-final-field-mutation=debug
--illegal-final-field-mutation=deny
```

| Chế độ | Hành vi | Mục đích |
|---|---|---|
| `allow` | Cho phép illegal final-field mutation tiếp tục mà không warning | Chỉ dùng tạm thời để duy trì hành vi trong lúc điều tra |
| `warn` | Cho phép mutation tiếp tục và phát warning lần đầu theo từng caller module; tối đa một warning cho mỗi module | Chế độ mặc định của JDK 26 và JDK 27; phát hiện dependency có vấn đề mà chưa làm ứng dụng dừng |
| `debug` | Giống `warn`, nhưng phát warning và stack trace cho mỗi lần illegal mutation | Xác định chính xác code path và thư viện thực hiện thao tác |
| `deny` | Từ chối illegal mutation; thao tác ghi qua `Field` thất bại với `IllegalAccessException` | Kiểm tra khả năng tương thích với chính sách nghiêm ngặt trong tương lai |

Hai điểm cần nhớ:

- `warn` chỉ báo tối đa một lần cho mỗi module gọi, không phải một warning cho từng field. Nếu nhiều thư viện cùng nằm trên classpath, tất cả đều thuộc unnamed module nên warning có thể chỉ xuất hiện một lần dù có nhiều call site.
- `debug` phát stack trace cho mỗi lần illegal mutation nên log có thể rất nhiều. Dùng trong môi trường kiểm thử hoặc một lần tái hiện có kiểm soát, không nên bật bừa bãi trên hệ thống tải lớn.

`--illegal-final-field-mutation` là tùy chọn chuyển đổi tạm thời và tài liệu launcher ghi rõ sẽ bị loại bỏ trong một release tương lai. Kế hoạch của JDK là chuyển `deny` thành mặc định; không nên phụ thuộc lâu dài vào `allow` hoặc `warn` để duy trì hành vi mutation.

## 5. `--enable-final-field-mutation` là capability allowlist

Nếu đã xác định một thư viện cũ thật sự cần sửa final instance field và chưa thể thay thế ngay, ứng dụng có thể cấp quyền cho đúng module gọi:

**Code nằm trên classpath:**

```bash
java --enable-final-field-mutation=ALL-UNNAMED -jar app.jar
```

**Code nằm trên module path:**

```bash
java --enable-final-field-mutation=com.example.legacyserializer,com.example.compat -m com.example.app/com.example.Main
```

Option này là lựa chọn lâu dài hơn về mặt tương thích so với `--illegal-final-field-mutation=allow`: nó giới hạn capability theo module, thay vì thay đổi phản ứng của JVM với illegal mutation trên toàn hệ thống. Tuy nhiên, đây vẫn là ngoại lệ cho một hành vi có rủi ro. Chỉ bật cho module thực sự cần, và package của field đích vẫn phải đáp ứng quy tắc mở package/access.

Nếu ứng dụng dùng module path, ví dụ module khai báo field cần mở package cho module thư viện:

```java
module com.example.model {
    exports com.example.model.api;
    opens com.example.model.internal to com.example.legacyserializer;
}
```

Runtime có thể cần đồng thời:

```bash
java \
  --enable-final-field-mutation=com.example.legacyserializer \
  -m com.example.app/com.example.Main
```

`opens` cho phép deep reflection vào package; `--enable-final-field-mutation` cấp quyền mutation cho caller. Nếu chỉ thêm `--add-opens` mà không bật capability, warning final-field mutation vẫn có thể xuất hiện trên JDK 26/27. Nếu chỉ bật capability mà package không mở và không thỏa trường hợp truy cập hợp lệ, `setAccessible` hoặc mutation vẫn thất bại.

## 6. Kiểm tra theo JDK đích

Không dựa vào JDK cài để biên dịch khi đánh giá hành vi runtime. `--illegal-final-field-mutation` là tùy chọn của Java launcher/JVM; cần chạy ứng dụng bằng đúng `java` của JDK đích.

Kiểm tra runtime trước:

```bash
java --version
```

Trên Windows PowerShell, dùng `where.exe java` để xem các launcher trong `PATH`; trên macOS/Linux dùng `which java`. Nếu ứng dụng chạy trong container, service wrapper, IDE hoặc script triển khai, kiểm tra chính lệnh `java` mà môi trường đó thật sự khởi chạy. `javac --version` không chứng minh JVM chạy ứng dụng là cùng JDK.

Tại thời điểm 27-11-2026:

| Runtime | Hành vi liên quan JEP 500 |
|---|---|
| JDK 25 trở xuống | Chưa có chính sách warning JEP 500 của JDK 26; không dùng kết quả chạy JDK cũ để kết luận đã sẵn sàng |
| JDK 26 | `warn` là mặc định; hỗ trợ `allow`, `warn`, `debug`, `deny` và `--enable-final-field-mutation` |
| JDK 27 | Tiếp tục phát warning về deep reflection mutation; `warn` vẫn là mặc định theo tài liệu launcher JDK 27 |
| JDK tương lai | Kế hoạch là chuyển mặc định sang `deny` và loại bỏ option chuyển đổi; kiểm tra tài liệu đúng release trước khi nâng cấp |

Đối với JDK đích khác, xác minh `java --help` và tài liệu `java` command của đúng phiên bản. Không giả định một runtime tương lai vẫn giữ mọi chế độ tạm thời hoặc cùng default.

## 7. Quy trình chẩn đoán thực tế

Một quy trình hiệu quả có thể chia thành bốn lần chạy.

### Bước 1: Chạy với mặc định `warn`

```bash
java -jar app.jar
```

Trên JDK 26/27, theo dõi standard error để tìm thông báo dạng:

```text
WARNING: Final field endpoint in class com.example.ServiceConfig
has been mutated reflectively by class com.example.LegacyMapper
in unnamed module @... (file:/.../legacy-mapper.jar)
WARNING: Use --enable-final-field-mutation=ALL-UNNAMED to avoid a warning
WARNING: Mutating final fields will be blocked in a future release unless
final field mutation is enabled
```

Thông báo chỉ ra field bị sửa, class thực hiện mutation, module gọi và vị trí thư viện nếu có. Ghi lại dependency/version và luồng nghiệp vụ làm warning xuất hiện. Do warning chỉ xuất hiện một lần cho mỗi module, không dùng số warning để ước lượng số field bị sửa.

### Bước 2: Chạy `debug` để tìm call site

```bash
java --illegal-final-field-mutation=debug -jar app.jar
```

`debug` in warning kèm stack trace cho từng lần illegal mutation. Dùng stack trace để tìm class và phương thức của dependency, sau đó kiểm tra phiên bản mới có loại bỏ thao tác này chưa. Nếu lỗi chỉ xảy ra khi deserialize, khởi tạo ORM, bind cấu hình hoặc chạy test framework, hãy tái hiện đúng luồng đó.

### Bước 3: Thu thập bằng JFR

JDK Flight Recorder có event `jdk.FinalFieldMutation` để ghi nhận final instance field mutation qua deep reflection hoặc việc tạo setter MethodHandle từ reflected field. Có thể chạy:

```bash
java -XX:StartFlightRecording:filename=final-field-audit.jfr -jar app.jar
jfr print --events jdk.FinalFieldMutation final-field-audit.jfr
```

Event có thể cung cấp class khai báo field, tên field, thread và stack trace. JFR hữu ích khi cần quan sát một lần chạy tích hợp hoặc môi trường kiểm thử dài hơn. Không gửi file recording ra ngoài nếu nó chứa thông tin nhạy cảm về classpath, đường dẫn hoặc hoạt động nội bộ của ứng dụng.

### Bước 4: Chạy `deny` như một kiểm tra tương thích

```bash
java --illegal-final-field-mutation=deny -jar app.jar
```

Nếu ứng dụng hoặc dependency còn dựa vào illegal mutation, thao tác đó sẽ thất bại với `IllegalAccessException`. Đây là phép thử quan trọng trước khi nâng JDK. Nếu một module đã được cho phép mutation bằng `--enable-final-field-mutation`, giữ đúng allowlist cần thiết trong bài test; nếu không, bài test có thể thất bại vì capability bị thiếu dù môi trường production hiện tại đang chủ động cấp quyền.

Không dùng `--illegal-final-field-mutation=allow` làm kết quả kiểm tra cuối cùng: chế độ này che warning và giữ hành vi cần được loại bỏ.

## 8. Ma trận kiểm tra trong CI và môi trường triển khai

Nên có một profile kiểm tra riêng để phát hiện dependency regression:

| Giai đoạn | Cấu hình đề xuất | Mục tiêu |
|---|---|---|
| Developer local | JDK đích, mặc định `warn` | Nhận biết warning trong quá trình phát triển |
| CI diagnostic | `--illegal-final-field-mutation=debug` trên test suite được chọn | Thu stack trace để gán trách nhiệm cho dependency/call site |
| CI compatibility | `--illegal-final-field-mutation=deny` | Làm lộ thao tác illegal trước khi release |
| Production | Không bật mutation nếu không cần; nếu bất khả kháng thì allowlist module tối thiểu | Hạn chế quyền và tránh phụ thuộc vào chế độ chuyển đổi toàn cục |

Không nhất thiết chạy toàn bộ test hai lần với `debug` và `deny` trong mọi build nếu chi phí cao. Có thể chạy một bộ integration test đại diện cho các luồng deserialize, dependency injection, ORM, serialization và cấu hình. Quan trọng là test được chạy bằng cùng major JDK và gần với cấu hình launcher thực tế.

Khi kiểm tra nhiều JDK, ghi rõ từng lệnh dùng runtime nào. Ví dụ:

```bash
# JDK 26
"$JDK26_HOME/bin/java" --illegal-final-field-mutation=deny -jar app.jar

# JDK 27
"$JDK27_HOME/bin/java" --illegal-final-field-mutation=deny -jar app.jar
```

Trên Windows PowerShell, dùng đường dẫn `& "$env:JDK26_HOME\bin\java.exe" ...` và `& "$env:JDK27_HOME\bin\java.exe" ...`. Biến môi trường chỉ là ví dụ; thay bằng đường dẫn JDK mà CI thực sự cài.

## 9. Cách xử lý dependency gây mutation

Khi tìm được thư viện gây warning, ưu tiên theo thứ tự:

1. **Nâng cấp thư viện:** tìm phiên bản hỗ trợ JDK 26/27 và không sửa final field sau constructor.
2. **Dùng API cấu hình/constructor/factory chính thức:** thay reflective mutation bằng constructor, builder, setter không-final có chủ đích hoặc hook được thư viện cung cấp.
3. **Dùng cơ chế serialization phù hợp:** nếu thư viện cần tái tạo object, chọn cơ chế deserialization có hỗ trợ constructor/factory hoặc serialization proxy thay vì ghi tùy tiện vào final field đã được công bố.
4. **Sửa hoặc thay dependency:** nếu thư viện không còn được duy trì, cân nhắc fork có bản sửa hoặc thay thế bằng thư viện khác.
5. **Ngoại lệ tạm thời:** chỉ khi không thể loại bỏ ngay, bật `--enable-final-field-mutation` cho đúng caller module và mở đúng package cần thiết; ghi lại lý do, owner và kế hoạch gỡ bỏ.

Không sửa field `final` của object đã được chia sẻ giữa các thread để thay đổi cấu hình runtime. Nếu cấu hình cần thay đổi, mô hình hóa nó bằng object mới bất biến và thay reference ở điểm đồng bộ phù hợp, hoặc dùng một loại trạng thái mutable có đồng bộ hóa rõ ràng.

## 10. Những hiểu lầm thường gặp

| Hiểu lầm | Thực tế |
|---|---|
| `setAccessible(true)` thành công thì `Field.set` chắc chắn sửa được final field | Không. Từ JDK 26 còn có kiểm tra final-field mutation capability và điều kiện field/module khác |
| `--add-opens` sẽ loại bỏ warning JEP 500 | Không. `opens` xử lý deep reflection access; `--enable-final-field-mutation` cấp capability riêng |
| `--illegal-final-field-mutation=deny` làm mọi phép ghi final field trong Java bị lỗi | Không. Nó nhắm vào illegal reflective final-field mutation; gán trong constructor/initializer vẫn bình thường |
| `--enable-final-field-mutation=ALL-UNNAMED` cho phép sửa mọi final field | Không. Chỉ cấp capability cho caller thuộc unnamed module; field vẫn phải là loại được hỗ trợ và thỏa điều kiện truy cập |
| `warn` phát một warning cho mỗi lần sửa field | Không. `warn` giới hạn tối đa một warning cho mỗi caller module |
| Không có warning nghĩa là không có final-field mutation | Chưa chắc. Có thể code đã được enable; hãy dùng JFR để quan sát mutation được cho phép |
| Chạy tốt trên JDK 25 chứng minh dependency tương thích JDK 26+ | Không. JDK 25 chưa áp dụng chính sách warning của JEP 500 |
| Có thể giữ `allow` làm cấu hình dài hạn | Không nên. Đây là chế độ chuyển đổi sẽ bị loại bỏ; ưu tiên loại bỏ dependency mutation |

## 11. Bài tập thực hành

Tạo class `ServiceConfig` có field `private final String endpoint`, constructor gán giá trị ban đầu và getter đọc giá trị. Tạo một class khác dùng reflection để gọi `setAccessible(true)` và `Field.set(...)` sau khi object được tạo.

**Yêu cầu:**

1. Biên dịch ví dụ và chạy bằng JDK 26 với cấu hình mặc định.
2. Chạy lại với `--illegal-final-field-mutation=warn`, ghi nhận warning và xác định module gọi.
3. Chạy với `--illegal-final-field-mutation=debug`, tìm stack trace dẫn tới dòng `Field.set`.
4. Chạy với `--illegal-final-field-mutation=deny`, xác nhận `IllegalAccessException` và giải thích vì sao object không được thay đổi.
5. Chạy với `--enable-final-field-mutation=ALL-UNNAMED` để quan sát khác biệt khi caller thuộc classpath và package đã truy cập được.
6. Bật JFR, tạo recording rồi dùng `jfr print --events jdk.FinalFieldMutation` để tìm event.
7. Chuyển ví dụ sang hai named module; chỉ mở package cần thiết và chỉ cấp capability cho module thực hiện mutation.
8. Đề xuất cách thay reflective mutation bằng constructor hoặc factory để không cần bất kỳ cờ final-field mutation nào.

**Kết quả mong đợi:**

- Người học phân biệt được lỗi mở package với lỗi thiếu mutation capability.
- `warn` cho phép thao tác tiếp tục nhưng báo một lần theo module; `debug` cho stack trace từng lần; `deny` từ chối illegal mutation.
- `--enable-final-field-mutation` và `--add-opens` có vai trò riêng và phải cùng thỏa khi cần deep reflection vào package khác module.
- JFR có thể tìm mutation ngay cả khi thao tác được cho phép, nhờ đó không chỉ dựa vào warning để kiểm kê.
- Giải pháp cuối cùng loại bỏ nhu cầu sửa final field sau khi object đã được khởi tạo.

## Tài liệu tham khảo

- [JEP 500: Prepare to Make Final Mean Final](https://openjdk.org/jeps/500): mục tiêu, lộ trình cảnh báo và giới hạn mutation final field.
- [Preparing for final Field Mutation Restrictions — JDK 26 Migration Guide](https://docs.oracle.com/en/java/javase/26/migrate/preparing-final-field-mutation-restrictions.html): hướng dẫn `warn`, `debug`, `deny`, `--enable-final-field-mutation` và chẩn đoán bằng JFR.
- [The `java` Command — Java SE 26](https://docs.oracle.com/en/java/javase/26/docs/specs/man/java.html): cú pháp và hành vi các tùy chọn launcher.
- [The `java` Command — Java SE 27](https://docs.oracle.com/en/java/javase/27/docs/specs/man/java.html): xác nhận các chế độ và default trong JDK 27.
- [Field — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/Field.html): điều kiện để `Field.set` có write access tới final instance field.
- [Mutation methods — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/reflect/doc-files/MutationMethods.html): các mutation method và điều kiện cấp capability.
- [MethodHandles.Lookup — Java SE 26 API](https://docs.oracle.com/en/java/javase/26/docs/api/java.base/java/lang/invoke/MethodHandles.Lookup.html): hành vi `unreflectSetter` với final field.
- [JDK 27 Migration Guide: Significant Changes](https://docs.oracle.com/en/java/javase/27/migrate/significant-changes-jdk-27-release.html): cập nhật warning final-field mutation trong JDK 27.
- [Avoiding Final Field Mutation — Inside Java](https://inside.java/2026/04/27/avoiding-final-field-mutation/): các cách thay thế reflective mutation trong framework và thư viện.
