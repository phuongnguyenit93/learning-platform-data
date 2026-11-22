# Kiến thức tiên quyết, phạm vi Java Core và trình tự học Reflection

## 1. Mục đích của lộ trình

Reflection cho phép Java khám phá metadata của một kiểu khi chương trình đang chạy và, khi được phép, tìm constructor, method hoặc field để thao tác động. Chủ đề này nằm ở giao điểm giữa **kiểu dữ liệu**, **cơ chế gọi phương thức**, **quyền truy cập** và **metadata**. Học theo thứ tự hợp lý giúp bạn phân biệt được lúc nào chỉ quan sát cấu trúc, lúc nào chương trình thật sự thực thi hoặc thay đổi trạng thái.

Bài này đóng vai trò **bản đồ học tập**: xác định nền tảng cần có, ranh giới của Reflection trong Java Core, chuỗi bài thực hành và tiêu chí tự đánh giá. Các bài chuyên đề trong chương sẽ giải thích chi tiết từng API, cơ chế generic, annotation và những lựa chọn thiết kế liên quan.

Sau bài này, bạn nên tự trả lời được: “Tôi đã đủ kiến thức bắt đầu chưa?”, “Tôi cần học gì trước khi thử gọi method bằng Reflection?” và “Một bài thực hành thế nào mới chứng minh tôi đã hiểu thay vì chỉ chép mã chạy được?”.

## 2. Kiến thức nên có trước khi bắt đầu

| Nền tảng | Bạn cần làm được | Liên hệ với Reflection |
| --- | --- | --- |
| Class và instance | Tạo object, phân biệt biến tham chiếu với đối tượng thật | `Class<?>` đại diện kiểu; object chứa trạng thái |
| Constructor, field, method | Viết constructor có tham số và method có giá trị trả về | Có các đối tượng metadata `Constructor`, `Field`, `Method` tương ứng |
| Kế thừa và interface | Phân biệt override với overload, hiểu phương thức kế thừa | Kết quả tìm member phụ thuộc kiểu, chữ ký và quy tắc kế thừa |
| Phạm vi truy cập | Hiểu `public`, `protected`, package-private, `private`, `static` | Tìm được metadata không đồng nghĩa được phép truy cập |
| Package, JDK và classpath | Biên dịch/chạy file Java, biết tên lớp đầy đủ | `Class.forName` cần tên nhị phân và class loader phù hợp |
| Primitive, wrapper, array | Phân biệt `int` với `Integer` và kiểu mảng | Tra cứu constructor/method dùng kiểu tham số chính xác |
| Exception | Đọc stack trace, nhận biết checked và unchecked exception | Lỗi tra cứu, khởi tạo và gọi động xuất hiện ở các bước khác nhau |
| Generic và annotation | Biết `List<String>`, wildcard, cú pháp `@Annotation` | Chuẩn bị cho type erasure, `Type` và runtime retention |

**Mức tối thiểu:** Bạn có thể bắt đầu phần quan sát metadata nếu biết viết một class, tạo instance và gọi method thông thường. Trước khi đi sâu vào generic/annotation, hãy ôn thêm các khái niệm tương ứng; không nhất thiết thành thạo hai chủ đề này ngay từ bài đầu.

### Bài tự kiểm tra trong 10 phút

Tự viết một lớp `Student` có field `private String name`, constructor `public Student(String name)` và method `public String greet()`. Sau đó, không dùng Reflection, hãy:

1. Tạo hai đối tượng có tên khác nhau và giải thích vì sao chúng cùng kiểu nhưng có trạng thái riêng.
2. Thêm subclass `GraduateStudent` ghi đè `greet()`. Dự đoán kết quả khi gọi qua biến kiểu `Student`.
3. Thêm overload `greet(String prefix)` và giải thích cách compiler phân biệt hai chữ ký.
4. Thử đổi method thành `private` rồi quan sát lỗi khi gọi từ bên ngoài lớp.

Nếu các bước này còn khó, hãy củng cố class/object, đa hình, phạm vi truy cập và exception trước. Đây là nền tảng để hiểu vì sao một `Method` có thể được tìm thấy nhưng lời gọi `invoke` vẫn thất bại.

## 3. Phạm vi Reflection trong Java Core

Chương này tập trung vào các API có sẵn trong JDK:

- **`java.lang.Class`:** nhận dạng kiểu lúc chạy, tên kiểu, superclass, interface và cách khám phá các member.
- **`java.lang.reflect`:** `Constructor`, `Method`, `Field`, `Modifier` và `Type` để đọc metadata; chỉ tạo đối tượng, gọi method, đọc/ghi field khi có mục đích và quyền hợp lệ.
- **Annotation runtime:** đọc annotation theo retention và vị trí khai báo, phân biệt metadata với logic xử lý của framework.
- **Ranh giới của Reflection:** declared/inherited, access control, Java Platform Module System (JPMS), type erasure, ngoại lệ, hiệu năng và khả năng bảo trì.

**Không thuộc mục tiêu chính:** tự xây dựng một DI container/ORM hoàn chỉnh, thay đổi bytecode bằng ASM/Byte Buddy, instrumentation agent, JNI, cơ chế ClassLoader phức tạp, hoặc tối ưu nâng cao với `MethodHandle`/`VarHandle`. Những chủ đề này có thể sử dụng hoặc bổ sung Reflection, nhưng không phải điều kiện để làm chủ API cơ bản.

Reflection cũng không thay thế interface, đa hình hay lời gọi trực tiếp. Nếu chương trình đã biết kiểu và hành vi lúc biên dịch, hãy ưu tiên API Java thông thường. Khi một thư viện phải quan sát kiểu do ứng dụng khác cung cấp ở runtime, Reflection mới thể hiện rõ giá trị.

## 4. Một điểm xuất phát nhỏ: chỉ đọc metadata

Thực hành đầu tiên nên **quan sát** trước khi khởi tạo hay gọi động. Tạo file `FirstMetadataCheck.java`:

~~~java
import java.lang.reflect.Method;

public class FirstMetadataCheck {
    public static void main(String[] args) throws NoSuchMethodException {
        Class<?> type = String.class;
        Method method = type.getMethod("substring", int.class);

        System.out.println(type.getName());
        System.out.println(method.getName());
        System.out.println(method.getReturnType().getSimpleName());
    }
}
~~~

Chạy với JDK 17 trở lên:

~~~bash
javac FirstMetadataCheck.java
java FirstMetadataCheck
~~~

Kết quả:

~~~text
java.lang.String
substring
String
~~~

Bạn vừa lấy một `Class<?>`, tìm metadata của phương thức public có tham số `int` và đọc kiểu trả về của nó. Chưa có đối tượng `String` nào bị sửa, cũng chưa gọi `substring`. Thử thay `int.class` bằng `Integer.class` để quan sát `NoSuchMethodException`: tra cứu chữ ký bằng Reflection không tự coi primitive và wrapper là một kiểu.

Ví dụ này chỉ giới thiệu kỹ năng đầu tiên. Khi chuyển sang gọi phương thức hoặc tạo instance, bạn sẽ dùng `Method.invoke` hoặc `Constructor.newInstance` và cần thêm kiểm tra receiver, quyền truy cập và cách xử lý lỗi.

## 5. Trình tự học: từ hiểu kiểu đến dùng API có kiểm soát

| Chặng | Trọng tâm | Bằng chứng bạn đã hiểu |
| --- | --- | --- |
| **0. Ôn Java Core** | Class/object, overload, override, constructor, access modifier và exception | Hoàn thành bài `Student` mà không dùng Reflection |
| **1. Kiểu tĩnh và kiểu runtime** | `SomeType.class`, `obj.getClass()`, `Class.forName`; phân biệt kiểu biến với lớp thực của object | Giải thích vì sao `Animal a = new Dog()` có hai góc nhìn về kiểu |
| **2. Khám phá cấu trúc** | `Class` và họ `get...` / `getDeclared...`; tên, modifier, constructor, method, field | Liệt kê được member, ghi rõ declared/public/inherited, không dựa vào thứ tự trả về |
| **3. Ranh giới quan sát và thực thi** | Metadata so với `Field.get`, `Field.set`, `Method.invoke`, `Constructor.newInstance` | Chỉ ra dòng nào đọc metadata và dòng nào có thể thay đổi trạng thái |
| **4. Metadata trong quan hệ kiểu** | Kế thừa, generic `Type`, type erasure, annotation runtime và `@Inherited` | Giải thích được metadata khai báo có thể tồn tại dù type argument của instance đã bị erasure |
| **5. Giới hạn và lỗi** | Sai tên/chữ ký, quyền truy cập, JPMS, exception do method đích ném, input không tin cậy | Chẩn đoán đúng bước hỏng thay vì thêm `setAccessible(true)` bừa bãi |
| **6. Tích hợp và lựa chọn thiết kế** | Ví dụ plugin, inspector, interface/`ServiceLoader`, đánh đổi về hiệu năng và bảo trì | Biết khi nào Reflection cần thiết và khi nào API trực tiếp đủ dùng |

Lộ trình không bắt buộc người học thuộc hàng chục tên method. Ở mỗi chặng, hãy ghi lại ba điều: **dữ liệu đầu vào là gì**, **đối tượng/API trả về diễn tả điều gì**, và **khi nào một lời gọi có thể thực thi mã hoặc ném lỗi**.

### Bốn mốc kiểm tra cần vượt qua

**Mốc A — Biết đang xét kiểu nào.** Tạo một biến kiểu cha giữ instance lớp con. So sánh kết quả của `Parent.class` và `instance.getClass()`; giải thích bằng compiler và runtime. Nếu không hiểu khác biệt này, đừng dùng `getDeclaredMethods()` để suy ra “mọi method được phép gọi”.

**Mốc B — Tách tra cứu khỏi hành động.** Từ một `Class<?>`, chỉ đọc tên, modifier và chữ ký của member; xác nhận chưa gọi method đích. Sau đó thử một lời gọi `invoke` có chủ đích, quan sát thay đổi trạng thái để thấy điểm chuyển pha.

**Mốc C — Hiểu metadata có giới hạn.** Đọc generic signature của một field `List<String>` và so sánh với `getClass()` của đối tượng `ArrayList`; thử annotation có `RetentionPolicy.RUNTIME`. Giải thích vì sao metadata khai báo không bảo đảm giá trị runtime thỏa mọi ràng buộc generic.

**Mốc D — Thiết kế có hợp đồng.** Nạp một implementation theo cấu hình, kiểm tra nó thực sự triển khai interface đã công bố, rồi gọi nghiệp vụ qua interface. Đánh giá liệu factory/registry hoặc `ServiceLoader` có giải quyết yêu cầu đơn giản hơn không.

## 6. Bài thực hành tổng hợp: xây ClassInspector

Sau khi đã học các chặng, hãy viết `ClassInspector` nhận một `Class<?>` và tạo báo cáo về kiểu. Mục tiêu đầu tiên là một **công cụ chỉ đọc**, vì nhiệm vụ khám phá không cần tự động thực thi code nghiệp vụ.

Phiên bản đầu cần in tên nhị phân và tên đơn giản, superclass, interface trực tiếp, constructor, method và field cùng modifier. Hãy thử trên ba kiểu: lớp đơn giản, lớp con có method override, và lớp có annotation runtime.

Nâng cấp theo từng vòng:

1. Cho phép người dùng chọn **chỉ thành viên khai báo** hoặc **thành viên public có thể kế thừa**; ghi rõ lựa chọn cạnh kết quả.
2. Sắp xếp tên member trước khi hiển thị, vì Reflection không bảo đảm thứ tự mảng mà API trả về.
3. Đánh dấu method bridge/synthetic khi gặp generic override; không coi mọi phần tử `getDeclaredMethods()` đều là method được gõ trong source.
4. Chỉ đọc annotation còn hiệu lực ở runtime, phân biệt annotation của class với annotation nằm trên type argument hoặc method.
5. Nếu cần thêm chế độ thực thi, chỉ cho phép method public đã được duyệt; tách luồng xác thực, tạo đối tượng và gọi method ra khỏi luồng inspector chỉ đọc.

Khi kiểm thử, cố tình tạo ba lỗi: tên method sai, chữ ký tham số sai và method đích tự ném exception. Trình bày **lỗi ở bước tra cứu** khác **lỗi được bọc khi method chạy**. Đối với member private thuộc module khác, ưu tiên thiết kế quyền truy cập rõ ràng thay vì mặc định có thể mở bằng Reflection.

### Tiêu chí hoàn thành bài tổng hợp

- Báo cáo không thay đổi trạng thái object khi chỉ ở chế độ khám phá.
- Có thể dự đoán đúng member nào xuất hiện trong chế độ declared và public/inherited.
- Kết quả ổn định sau khi sắp xếp, kể cả khi thứ tự Reflection trả về thay đổi.
- Nhận diện được giới hạn của annotation và generic metadata.
- Lỗi được mô tả bằng **class + member + chữ ký + bước thất bại**, có nguyên nhân gốc khi thực thi.
- Bạn có thể giải thích quyết định giữ Reflection ở ranh giới công cụ và dùng lời gọi thông thường ở phần nghiệp vụ.

## 7. Cách tự đánh giá và học tiếp

Không nên chỉ kiểm tra “chạy ra đúng vài dòng console”. Bạn đã nắm một chặng khi có thể **dự đoán kết quả trước khi chạy**, giải thích kết quả sau khi chạy, và sửa một biến thể cố tình sai mà vẫn giữ được ranh giới quyền truy cập.

Các dấu hiệu nên ôn lại:

- Bạn cho rằng `Class<?>` là instance dữ liệu của lớp được mô tả.
- Bạn nghĩ `getDeclaredMethod` vừa tìm vừa gọi method hoặc luôn bỏ qua kiểm tra truy cập.
- Bạn mong `getClass()` khôi phục mọi tham số generic từng có trong biến nguồn.
- Bạn không phân biệt lỗi `NoSuchMethodException` với nguyên nhân nằm trong `InvocationTargetException.getCause()`.
- Bạn dùng Reflection cho mọi lời gọi chỉ vì muốn chọn một implementation khác khi chương trình đã có interface chung.

Trình tự đọc phù hợp với chương này là: **Reflection là gì và vấn đề cần giải quyết → thông tin kiểu biên dịch/runtime → metadata khác thực thi/trạng thái → vai trò của Class và java.lang.reflect → kế thừa/generic/annotation → Reflection hay gọi trực tiếp → ví dụ xuyên suốt**. Có thể quay lại bài này để tự đánh dấu mốc học tập.

Nếu hoàn thành `ClassInspector` và giải thích được các giới hạn trên, bạn đã có nền tảng để tìm hiểu ứng dụng Reflection trong test runner, serializer, dependency injection hoặc plugin loader thực tế. Các framework có thể dùng thêm kỹ thuật khác; hãy xác minh cách chúng xử lý metadata và quyền truy cập thay vì mặc định mọi framework đều hoạt động theo đúng ví dụ nhập môn.