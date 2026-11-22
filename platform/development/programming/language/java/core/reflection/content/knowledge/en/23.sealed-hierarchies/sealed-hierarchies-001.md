# isSealed và getPermittedSubclasses trong Java Reflection

## 1. Quan sát ranh giới kế thừa khi chỉ biết Class lúc chạy

Một kiểu `sealed` giới hạn những kiểu được phép kế thừa hoặc triển khai nó **trực tiếp**. Điều này giúp tác giả mô hình kiểm soát các nhánh đầu tiên của phân cấp, thay vì cho bất kỳ lớp nào tự bổ sung một nhánh trực tiếp mới.

Khi viết công cụ xem cấu trúc kiểu, tạo tài liệu hoặc kiểm tra mô hình lúc chạy, ta có thể chỉ nhận một `Class<?>`. Từ Java 17, hai API của `Class` hỗ trợ nhu cầu này:

- `isSealed()`: lớp hoặc interface đang xét có phải kiểu sealed hay không?
- `getPermittedSubclasses()`: những lớp hoặc interface con trực tiếp nào được phép, và có thể thu được dưới dạng đối tượng `Class` ở môi trường chạy?

Hai câu hỏi này mô tả **cấu trúc kiểu**. Chúng không tạo đối tượng, không gọi constructor và không tự tìm mọi đối tượng hoặc mọi lớp triển khai đang tồn tại.

## 2. Hợp đồng của hai phương thức

| API | Kết quả |
| --- | --- |
| `type.isSealed()` | `true` khi type là lớp hoặc interface sealed |
| `type.getPermittedSubclasses()` | `Class<?>[]` cho kiểu sealed; `null` nếu type không sealed |

Cần giữ các trường hợp khác nhau:

- **Không sealed:** `isSealed()` là `false`, `getPermittedSubclasses()` là `null`.
- **Sealed:** `isSealed()` là `true`, kết quả danh sách khác `null`.
- **Sealed với kết quả rỗng:** có thể nhận một mảng độ dài 0 theo hợp đồng API; không dùng độ dài lớn hơn 0 làm điều kiện nhận diện sealed.

Đối với kiểu nguyên thủy, `void` và kiểu mảng, `isSealed()` trả `false`, còn `getPermittedSubclasses()` trả `null`.

Tên `getPermittedSubclasses` không có nghĩa API chỉ dùng cho lớp. Khi nhận một sealed interface, nó có thể trả cả lớp triển khai trực tiếp và interface con trực tiếp.

Thứ tự các phần tử trong mảng không được quy định. Nếu cần đầu ra ổn định để in, hiển thị hoặc so sánh, hãy tự sắp xếp.

## 3. Ví dụ hoàn chỉnh: sealed interface, interface con và nhánh mở

Lưu thành `SealedInspectionDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.stream.Collectors;

public class SealedInspectionDemo {
    sealed interface Event
            permits DataEvent, Command, Extension {
    }

    record DataEvent(String text) implements Event {
    }

    sealed interface Command extends Event permits Start, Stop {
    }

    record Start() implements Command {
    }

    record Stop() implements Command {
    }

    non-sealed interface Extension extends Event {
    }

    static final class PluginEvent implements Extension {
    }

    private static void show(Class<?> type) {
        Class<?>[] permitted = type.getPermittedSubclasses();

        System.out.println(type.getSimpleName()
                + ".isSealed=" + type.isSealed());

        String names = permitted == null
                ? "null"
                : Arrays.stream(permitted)
                      .map(Class::getSimpleName)
                      .sorted()
                      .collect(Collectors.joining(","));

        System.out.println(type.getSimpleName()
                + ".permitted=" + names);
    }

    public static void main(String[] args) {
        show(Event.class);
        show(Command.class);
        show(Extension.class);
        show(DataEvent.class);

        System.out.println("Event.directHasStart="
                + Arrays.asList(Event.class.getPermittedSubclasses())
                      .contains(Start.class));
        System.out.println("Event.assignableFromStart="
                + Event.class.isAssignableFrom(Start.class));
        System.out.println("Extension.assignableFromPluginEvent="
                + Extension.class.isAssignableFrom(PluginEvent.class));
        System.out.println("DataEvent.final="
                + Modifier.isFinal(DataEvent.class.getModifiers()));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên; không cần bật preview:

~~~bash
javac --release 17 SealedInspectionDemo.java
java SealedInspectionDemo
~~~

Kết quả:

~~~text
Event.isSealed=true
Event.permitted=Command,DataEvent,Extension
Command.isSealed=true
Command.permitted=Start,Stop
Extension.isSealed=false
Extension.permitted=null
DataEvent.isSealed=false
DataEvent.permitted=null
Event.directHasStart=false
Event.assignableFromStart=true
Extension.assignableFromPluginEvent=true
DataEvent.final=true
~~~

Ví dụ cho thấy:

1. `Event` cho phép trực tiếp ba nhánh: `DataEvent`, `Command`, `Extension`.
2. `Command` lại là sealed interface với hai kiểu con trực tiếp riêng.
3. `Start` là một loại `Event`, nhưng nó đi qua `Command`, nên không nằm trong danh sách trực tiếp của `Event`.
4. `Extension` là `non-sealed`. Nó vẫn có thể có lớp triển khai như `PluginEvent`, dù `getPermittedSubclasses()` của nó trả `null`.
5. `DataEvent` là record, có tính `final` ngầm định. Nó không sealed, và không cho kế thừa tiếp.

Các khai báo được đặt trong cùng một lớp ngoài để có thể biên dịch gọn trong một tệp. Trong dự án có module/package, các quy tắc về nơi khai báo kiểu con trực tiếp vẫn phải được thỏa mãn.

## 4. Danh sách trực tiếp khác toàn bộ phân cấp

`getPermittedSubclasses()` đọc ranh giới trực tiếp của đúng kiểu đang xét. Nó không tự trả về toàn bộ các kiểu ở mọi độ sâu.

Với ví dụ trên, có thể đọc các quan hệ như sau:

~~~text
Event [sealed]
  Command [sealed]
    Start [final record]
    Stop [final record]
  DataEvent [final record]
  Extension [non-sealed]
    PluginEvent [một ví dụ triển khai]
~~~

Các nhánh ngay dưới một nút sealed là nơi ta có thể tiếp tục dùng `getPermittedSubclasses()`. Quan hệ từ `Extension` đến `PluginEvent` không được khám phá bằng API này; chương trình ví dụ biết nó vì lớp đó có trong mã nguồn.

Nếu cần khảo sát sâu hơn, phải gọi lại API trên từng nút sealed. Khi gặp một nhánh không sealed và không final, phải ghi nhận rằng nhánh ấy có thể tiếp tục mở rộng. Không biến nó thành một “lá cuối cùng” chỉ vì API không trả danh sách con.

`isAssignableFrom` trả lời một câu hỏi khác: kiểu đích có nhận giá trị thuộc kiểu nguồn theo quan hệ kiểu hay không? Nó bao gồm quan hệ gián tiếp. Vì vậy, `Event.class.isAssignableFrom(Start.class)` là `true` trong khi `Start.class` không có trong mảng permitted trực tiếp của `Event`.

Cũng không dùng `getSuperclass()` để tìm ngược mọi quan hệ của interface. Một lớp chỉ có một lớp cha trực tiếp, nhưng có thể triển khai nhiều interface. Cấu trúc quan hệ kiểu cần được đọc theo đúng loại quan hệ.

## 5. final, sealed và non-sealed không có cùng ý nghĩa

| Loại khai báo | Ý nghĩa đối với việc mở rộng |
| --- | --- |
| `final class` | Không có lớp con |
| `sealed class/interface` | Chỉ các kiểu con trực tiếp được phép |
| `non-sealed class/interface` | Mở lại quyền mở rộng ở nhánh ấy |
| Lớp/interface thông thường không sealed | Không mang ràng buộc sealed của chính kiểu đó |

`isSealed() == false` không chứng minh mã nguồn đã dùng từ khóa `non-sealed`. Một lớp final, một lớp thông thường hoặc một interface thông thường cũng có thể cho kết quả ấy.

Trên Java 17, không có phương thức `Class.isNonSealed()`. Nếu đang đứng ở một kiểu con trực tiếp đã biết của một sealed type, có thể dùng thêm loại kiểu và cờ final để giải thích tình trạng của nhánh theo mô hình. Nhưng không đặt nhãn “được khai báo non-sealed” cho mọi lớp không sealed và không final trên toàn hệ thống.

Cũng không nhận diện sealed bằng cách tìm chuỗi `sealed` trong kết quả `Modifier.toString`. Dùng `Class.isSealed()` cho câu hỏi sealed và `Modifier.isFinal` cho câu hỏi final tương ứng.

Một lớp sealed không bắt buộc là abstract. Việc được phép xuất hiện trong danh sách permitted cũng không bảo đảm kiểu đó khởi tạo trực tiếp được: nó có thể là interface hoặc lớp abstract, hoặc cần các đối số constructor cụ thể.

## 6. Ví dụ duyệt các nhánh sealed và đánh dấu điểm mở

Lưu thành `SealedBranchWalkDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;
import java.util.Comparator;

public class SealedBranchWalkDemo {
    static abstract sealed class Result
            permits Success, Failure, Extensible {
    }

    static final class Success extends Result {
    }

    static abstract sealed class Failure extends Result
            permits Invalid, Timeout {
    }

    static final class Invalid extends Failure {
    }

    static final class Timeout extends Failure {
    }

    static non-sealed class Extensible extends Result {
    }

    static final class Custom extends Extensible {
    }

    private static void showBranch(Class<?> type, int depth) {
        String state = type.isSealed()
                ? "sealed"
                : Modifier.isFinal(type.getModifiers()) ? "final" : "open";

        System.out.println("  ".repeat(depth)
                + type.getSimpleName() + " [" + state + "]");

        if (!type.isSealed()) {
            return;
        }

        Class<?>[] children = type.getPermittedSubclasses();
        Arrays.sort(children, Comparator.comparing(Class::getName));
        for (Class<?> child : children) {
            showBranch(child, depth + 1);
        }
    }

    public static void main(String[] args) {
        showBranch(Result.class, 0);
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 SealedBranchWalkDemo.java
java SealedBranchWalkDemo
~~~

Kết quả:

~~~text
Result [sealed]
  Extensible [open]
  Failure [sealed]
    Invalid [final]
    Timeout [final]
  Success [final]
~~~

Từ `open` ở đây là nhãn hiển thị của công cụ cho nút không sealed và không final. Trong mô hình cụ thể, `Extensible` được khai báo `non-sealed`.

`Custom` không được in. Nó vẫn tồn tại trong ví dụ, nhưng không thể được liệt kê bằng `Extensible.class.getPermittedSubclasses()`. Bản in phải được hiểu là **các nhánh đi được bằng metadata sealed**, không phải bản quét đầy đủ mọi lớp của ứng dụng.

Ví dụ dùng kế thừa lớp đơn để tập trung vào API. Nếu mở rộng công cụ cho đồ thị interface, cùng một kiểu có thể xuất hiện theo nhiều đường; cần quyết định có hiển thị lại theo đường hay dùng tập `Class` đã thăm để tránh xử lý lặp.

## 7. Những giới hạn của kết quả lúc chạy

API cố gắng lấy các đối tượng `Class` cho các kiểu được ghi nhận là permitted trực tiếp, sử dụng bộ nạp định nghĩa của kiểu đang xét. Nếu không lấy được một đối tượng `Class`, mục tương ứng có thể bị bỏ qua âm thầm theo hợp đồng API.

Vì vậy:

- Không coi mảng kết quả như một bản chép chắc chắn đầy đủ của mọi tên đã ghi trong class file ở mọi môi trường.
- Một mảng rỗng không đồng nghĩa với `isSealed() == false`.
- Nếu công cụ kiểm toán cần đối chiếu mọi tên trong metadata nhị phân, phải có quy trình kiểm tra class file và môi trường nạp phù hợp; riêng hai API này không cung cấp báo cáo từng mục đã bị bỏ qua.
- Những kiểm tra quyền truy cập được API quy định vẫn có thể gây lỗi, chẳng hạn `SecurityException` trong môi trường có chính sách tương ứng.

Ví dụ có đầy đủ các lớp đã biên dịch trong cùng thư mục nên thu được các kiểu như bản in. Khi triển khai, không nên chữa một kết quả thiếu bằng cách tự đoán tên lớp hoặc bỏ qua việc đóng gói sai.

Lời gọi lấy metadata cũng không phải tuyên bố rằng JVM không làm việc gì: nó có thể liên quan đến việc nạp các kiểu cần thiết. Hai API không tạo instance hay thực hiện constructor của các kiểu được liệt kê. Không cần khởi tạo thử từng kiểu chỉ để hiển thị tên và quan hệ permitted.

## 8. Ứng dụng và ranh giới suy luận

**Trình xem mô hình:** hiển thị các nhánh trực tiếp, đánh dấu nút sealed, nút final và điểm mở. Nếu gặp mảng rỗng hoặc lỗi nạp, cần diễn tả đúng mức độ thông tin có được.

**Kiểm tra kiến trúc:** xác nhận những kiểu trực tiếp mong đợi có mặt, hoặc phát hiện thay đổi của mô hình đã triển khai. So sánh theo một tập/khóa có quy tắc, không phụ thuộc thứ tự mảng API.

**Công cụ tài liệu:** liên kết từng kiểu với mô tả của nó. Khi có nhánh non-sealed, ghi nhận rằng các lớp con sâu hơn có thể đến từ nơi khác.

**Công cụ tạo đối tượng:** danh sách permitted chỉ là bước khám phá cấu trúc. Nó không thay thế việc chọn kiểu nghiệp vụ, kiểm tra quyền dùng kiểu ấy, chuẩn bị dữ liệu hay tìm constructor hợp lệ.

Không tự suy ra rằng một root sealed luôn tạo thành một tập hữu hạn các lớp cụ thể ở mọi độ sâu. Nhánh non-sealed có thể tiếp tục mở rộng. Ngay cả một cây không có điểm mở cũng cần được đọc đúng với lớp abstract, kiểu có thể khởi tạo và mức độ đầy đủ của metadata đang thu được.

Danh sách permitted cũng không phải danh sách các đối tượng đang sống, các bean đã đăng ký hoặc các plugin đã kích hoạt. Những hệ thống đó có vòng đời và nguồn đăng ký riêng.

## 9. Những lỗi thường gặp

| Sai lầm | Cách hiểu hoặc xử lý đúng |
| --- | --- |
| Duyệt ngay `getPermittedSubclasses()` với mọi Class | Kiểm tra sealed hoặc xử lý trường hợp `null` |
| Dùng độ dài mảng lớn hơn 0 để nhận diện sealed | Dùng `isSealed()`; mảng sealed có thể rỗng |
| Cho rằng API trả mọi kiểu con gián tiếp | Chỉ gồm các kiểu con trực tiếp thu được |
| Cho rằng mọi phần tử là lớp cụ thể | Có thể có interface hoặc lớp abstract |
| Gọi `getPermittedSubclasses()` trên non-sealed để tìm triển khai | API trả `null`; cần nguồn khám phá khác nếu thực sự có nhu cầu |
| Dùng thứ tự mảng làm thứ tự nguồn | Tự sắp xếp đầu ra; thứ tự API không được quy định |
| Đồng nhất không sealed với từ khóa non-sealed | Phân biệt final, kiểu thông thường và nhánh được mở lại |
| Coi mảng trả về là bằng chứng đủ về mọi mục trong class file | Xét việc API có thể bỏ qua mục không lấy được Class |
| Tạo thử instance của mọi kiểu được phép | Metadata permitted không cung cấp hợp đồng khởi tạo đối tượng |

Khi viết một hàm tiện ích, hãy quyết định có cần giữ sự khác nhau giữa “không sealed” và “sealed nhưng kết quả rỗng” hay không. Trả một danh sách rỗng cho cả hai có thể tiện cho vòng lặp, nhưng làm mất thông tin nếu phía gọi cần phân loại mô hình.

## 10. Tự kiểm tra

1. Vì sao `Start` không có trong permitted trực tiếp của `Event`, dù `Start` là một loại `Event`?
2. `Extension.class.getPermittedSubclasses()` trả `null` có nghĩa là không thể có `PluginEvent` không?
3. `isSealed() == false` có đủ để khẳng định kiểu được khai báo `non-sealed` không?
4. API có bảo đảm thứ tự giống danh sách `permits` trong nguồn không?
5. Với một Class không sealed, có nên gọi trực tiếp `getPermittedSubclasses().length` không?
6. Một phần tử trong mảng permitted có nhất thiết tạo được bằng constructor không tham số không?

Đáp án:

1. `Start` triển khai trực tiếp `Command`; quan hệ với `Event` là gián tiếp.
2. Không. `null` ở đây có nghĩa kiểu đang xét không sealed; nó không phải bản liệt kê triển khai.
3. Không; kiểu final hoặc thông thường cũng có thể không sealed.
4. Không. Nếu cần ổn định, phải sắp xếp theo quy tắc của công cụ.
5. Không; kết quả là `null`, nên truy cập độ dài sẽ gây `NullPointerException`.
6. Không. Nó có thể là interface, lớp abstract hoặc lớp có yêu cầu constructor khác.

## Tài liệu đối chiếu

- [Java 17 — Class.isSealed](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#isSealed()).
- [Java 17 — Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()).
- [JLS 17 — sealed, non-sealed và final class](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.1.2).
- [JLS 17 — sealed và non-sealed interface](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.1.4).
