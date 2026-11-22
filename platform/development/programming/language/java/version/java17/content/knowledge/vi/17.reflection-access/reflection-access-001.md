# `Class.isSealed()` và `Class.getPermittedSubclasses()` trong Java 17

## 1. Reflection có thể cho biết điều gì về một kiểu `sealed`?

Java 17 đưa hai phương thức vào `java.lang.Class` để chương trình có thể kiểm tra thông tin của **sealed class** và **sealed interface** tại runtime:

- `Class.isSealed()` cho biết kiểu được đại diện bởi đối tượng `Class` có phải là kiểu `sealed` hay không.
- `Class.getPermittedSubclasses()` trả về các đối tượng `Class<?>` đại diện cho những lớp con hoặc interface con **trực tiếp được phép** kế thừa/triển khai kiểu đó.

Hai phương thức này hữu ích khi xây dựng công cụ kiểm tra cấu trúc kiểu, framework, bộ kiểm thử, bộ chuyển đổi dữ liệu hoặc tiện ích hiển thị cây kế thừa. Thay vì tự đọc tên các kiểu trong mã nguồn, chương trình có thể hỏi JVM về metadata của kiểu đã được nạp.

Ví dụ đơn giản:

~~~java
Class<?> type = PaymentResult.class;

System.out.println(type.isSealed());

Class<?>[] permitted = type.getPermittedSubclasses();
for (Class<?> child : permitted) {
    System.out.println(child.getName());
}
~~~

Nếu `PaymentResult` là một interface `sealed` hợp lệ, chương trình có thể biết các kiểu con trực tiếp được phép của nó. Kết quả là các đối tượng `Class<?>`, vì vậy bạn có thể tiếp tục kiểm tra tên, package, module, superclass, interfaces và trạng thái `sealed` của từng kiểu con.

**Lưu ý phiên bản:** cả hai API này có từ Java 17 và đã là API ổn định. Chúng không yêu cầu `--enable-preview`. Bài viết chỉ dùng các API hiện hành trong Java SE 17.

## 2. Đối tượng `Class<?>` là gì?

Reflection trong Java làm việc với đối tượng `Class` đại diện cho một kiểu đang tồn tại trong ứng dụng. Có thể lấy đối tượng đó từ class literal:

~~~java
Class<String> stringType = String.class;
Class<Integer> integerType = Integer.class;
Class<?> unknownType = String.class;
~~~

`Class<?>` thường được dùng khi kiểu cụ thể chỉ được biết tại runtime. Dấu `?` nói rằng ta biết đây là một đối tượng `Class` nhưng không khẳng định type parameter cụ thể của nó.

Một số cách lấy class token:

| Cách viết | Ý nghĩa |
|---|---|
| `PaymentResult.class` | Lấy class token từ tên kiểu đã biết lúc biên dịch. |
| `object.getClass()` | Lấy kiểu thực tế của một đối tượng đang tồn tại. |
| `Class.forName(name)` | Tìm và nạp kiểu theo tên; overload này có thể khởi tạo lớp. |
| `Class.forName(name, false, loader)` | Nạp kiểu bằng class loader chỉ định mà không yêu cầu khởi tạo lớp. |

Khi biết kiểu muốn kiểm tra, ưu tiên class literal vì ngắn gọn, an toàn kiểu và không phải tự xử lý tên. Ví dụ, để kiểm tra contract `PaymentResult`, dùng `PaymentResult.class` thay vì gọi `getClass()` trên một instance cụ thể.

### 2.1. Kiểu khai báo và kiểu runtime của đối tượng có thể khác nhau

~~~java
PaymentResult result = new Approved("TX-17");

System.out.println(PaymentResult.class.isSealed());
System.out.println(result.getClass().isSealed());
~~~

Dòng đầu kiểm tra **interface gốc** `PaymentResult`. Dòng sau kiểm tra **lớp thực tế** `Approved`. Nếu `Approved` là record, nó mặc nhiên `final`, không phải kiểu `sealed`; do đó hai kết quả có thể khác nhau.

Khi mục tiêu là xem một hierarchy cho phép những kiểu nào, hãy bắt đầu từ class token của kiểu cha `sealed`. Nếu chỉ gọi `object.getClass()`, bạn có thể đang kiểm tra một kiểu lá `final` và nhận `false` dù interface mà nó triển khai là `sealed`.

## 3. `Class.isSealed()`

Chữ ký:

~~~java
public boolean isSealed()
~~~

Phương thức trả về:

- `true` nếu đối tượng `Class` đại diện cho một class hoặc interface được khai báo `sealed`.
- `false` nếu kiểu đó không phải sealed.

Theo API Java SE 17, kết quả cũng là `false` với kiểu nguyên thủy, `void` và kiểu mảng.

Ví dụ:

~~~java
System.out.println(String.class.isSealed());      // false
System.out.println(int.class.isSealed());         // false
System.out.println(void.class.isSealed());        // false
System.out.println(String[].class.isSealed());    // false
~~~

Với một hierarchy:

~~~java
sealed interface PaymentResult
        permits Approved, Declined, Pending {
}

record Approved(String reference) implements PaymentResult {
}

record Declined(String reason) implements PaymentResult {
}

record Pending(int queuePosition) implements PaymentResult {
}
~~~

`PaymentResult.class.isSealed()` trả về `true`. Các record `Approved`, `Declined` và `Pending` là những kiểu con trực tiếp được phép, nhưng bản thân chúng không phải kiểu `sealed`; record mặc nhiên `final`.

### 3.1. `sealed` khác `final`

`isSealed()` không trả về `true` chỉ vì một class không thể bị kế thừa. Ví dụ:

~~~java
final class Token {
}

sealed class Credential permits ApiCredential {
}

final class ApiCredential extends Credential {
}
~~~

| Kiểu | `isSealed()` | Giải thích |
|---|---:|---|
| `Token` | `false` | `final` chặn mọi lớp con; nó không có danh sách kiểu con được phép. |
| `Credential` | `true` | `sealed` và có một kiểu con trực tiếp được phép. |
| `ApiCredential` | `false` | Kiểu con là `final`, không phải `sealed`. |

Một class `non-sealed` cũng có `isSealed() == false`. Nó mở nhánh kế thừa để các kiểu khác tiếp tục mở rộng theo quy tắc Java thông thường.

### 3.2. Không kiểm tra `sealed` bằng `Modifier.isSealed()`

`java.lang.reflect.Modifier` có các hàm kiểm tra những modifier như `public`, `abstract`, `final`, `static`, `native` và một số modifier khác. Java 17 **không có** `Modifier.isSealed()` hay cờ `Modifier.SEALED` để kiểm tra kiểu sealed.

Hãy gọi trực tiếp:

~~~java
boolean sealed = PaymentResult.class.isSealed();
~~~

Không nên cố suy luận trạng thái sealed bằng cách phân tích chuỗi trả về từ `Modifier.toString(type.getModifiers())`. API chuyên dụng `Class.isSealed()` là cách đúng và rõ ràng.

## 4. `Class.getPermittedSubclasses()`

Chữ ký:

~~~java
public Class<?>[] getPermittedSubclasses()
~~~

Phương thức trả về mảng `Class<?>[]` đại diện cho các **direct subclasses** hoặc **direct subinterfaces** được phép kế thừa/triển khai class hoặc interface hiện tại.

Có ba điểm quan trọng:

1. Chỉ trả về kiểu con **trực tiếp**, không trả về toàn bộ hậu duệ ở các cấp sâu hơn.
2. Thứ tự các phần tử trong mảng **không được bảo đảm**.
3. Nếu kiểu không phải `sealed`, phương thức trả về `null`; nếu kiểu `sealed` nhưng không có kiểu con được phép, phương thức trả về mảng rỗng.

Ví dụ:

~~~java
Class<?>[] children = PaymentResult.class.getPermittedSubclasses();

for (Class<?> child : children) {
    System.out.println(child.getSimpleName());
}
~~~

Với hierarchy `PaymentResult` ở trên, mảng chứa các class token tương ứng với `Approved`, `Declined` và `Pending`. Không có cam kết rằng thứ tự sẽ luôn là Approved, Declined, Pending.

### 4.1. Phân biệt `null` và mảng rỗng

Đây là khác biệt cần xử lý chính xác:

| Kiểu được kiểm tra | `isSealed()` | `getPermittedSubclasses()` |
|---|---:|---|
| Một class thông thường | `false` | `null` |
| Một interface thông thường | `false` | `null` |
| Một class/interface `sealed` có các kiểu con được phép | `true` | Mảng các class token. |
| Một class/interface `sealed` có danh sách được phép rỗng trong metadata | `true` | Mảng rỗng. |
| Kiểu nguyên thủy, `void` hoặc mảng | `false` | `null` |

Vì vậy, không được giả định `getPermittedSubclasses()` luôn trả một mảng không null:

~~~java
Class<?>[] children = String.class.getPermittedSubclasses();

// Lỗi: children là null vì String không phải sealed.
// System.out.println(children.length);
~~~

Cách an toàn là kiểm tra `isSealed()` trước, hoặc kiểm tra trực tiếp kết quả `null`:

~~~java
static void printPermitted(Class<?> type) {
    if (!type.isSealed()) {
        System.out.println(type.getName() + " is not sealed");
        return;
    }

    Class<?>[] permitted = type.getPermittedSubclasses();
    System.out.println(type.getName()
            + " has " + permitted.length + " permitted direct type(s)");
}
~~~

Theo hợp đồng API, nếu `isSealed()` trả `true` thì `getPermittedSubclasses()` trả mảng không null, có thể rỗng.

### 4.2. Chỉ có kiểu con trực tiếp

Xét cây kế thừa:

~~~java
sealed class Document
        permits TextDocument, MediaDocument {
}

final class TextDocument extends Document {
}

sealed class MediaDocument extends Document
        permits ImageDocument {
}

final class ImageDocument extends MediaDocument {
}
~~~

Khi gọi:

~~~java
Document.class.getPermittedSubclasses()
~~~

kết quả chỉ gồm `TextDocument` và `MediaDocument`. `ImageDocument` không phải kiểu con trực tiếp của `Document`; nó trực tiếp kế thừa `MediaDocument`.

Muốn xem cấp tiếp theo, phải tiếp tục kiểm tra `MediaDocument.class`:

~~~java
MediaDocument.class.getPermittedSubclasses()
~~~

kết quả gồm `ImageDocument`. API không tự làm phẳng toàn bộ cây kế thừa.

## 5. Ví dụ hoàn chỉnh: kiểm tra và in cây sealed

Ta xây dựng một chương trình có:

- `Shape` là sealed interface gốc.
- `Circle` là record, do đó final.
- `Polygon` là nhánh non-sealed, có thể mở rộng tiếp.
- `Rectangle` là một nhánh sealed khác, có kiểu con `FilledRectangle`.

Tạo file `SealedReflectionDemo.java`:

~~~java
import java.util.Arrays;

public final class SealedReflectionDemo {
    private SealedReflectionDemo() {
    }

    public sealed interface Shape
            permits Circle, Polygon, Rectangle {
    }

    public record Circle(double radius) implements Shape {
    }

    public non-sealed static class Polygon implements Shape {
    }

    public sealed static class Rectangle implements Shape
            permits FilledRectangle {
    }

    public static final class FilledRectangle extends Rectangle {
    }

    private static void printSealedTree(
            Class<?> type, String indentation) {

        System.out.println(indentation + type.getSimpleName()
                + (type.isSealed() ? " [sealed]" : ""));

        Class<?>[] permitted = type.getPermittedSubclasses();
        if (permitted == null) {
            return;
        }

        Arrays.stream(permitted)
                .sorted((left, right) ->
                        left.getName().compareTo(right.getName()))
                .forEach(child ->
                        printSealedTree(child, indentation + "  "));
    }

    public static void main(String[] args) {
        System.out.println("Shape is sealed: "
                + Shape.class.isSealed());
        System.out.println();

        printSealedTree(Shape.class, "");
        System.out.println();

        System.out.println("Polygon is sealed: "
                + Polygon.class.isSealed());
        System.out.println("Circle is sealed: "
                + Circle.class.isSealed());
        System.out.println("Rectangle is sealed: "
                + Rectangle.class.isSealed());
    }
}
~~~

Biên dịch và chạy bằng JDK 17:

~~~text
javac --release 17 -encoding UTF-8 SealedReflectionDemo.java
java SealedReflectionDemo
~~~

Đầu ra có dạng:

~~~text
Shape is sealed: true

Shape [sealed]
  Circle
  Polygon
  Rectangle [sealed]
    FilledRectangle

Polygon is sealed: false
Circle is sealed: false
Rectangle is sealed: true
~~~

Ví dụ dùng `Arrays.stream` và sắp xếp theo tên để kết quả hiển thị ổn định. Việc sắp xếp chỉ dành cho output dễ đọc; API gốc không cam kết thứ tự mảng.

### 5.1. Vì sao cây không hiển thị mọi lớp con?

`Polygon` được khai báo `non-sealed`. Khi chương trình kiểm tra `Polygon.class`:

- `isSealed()` trả `false`.
- `getPermittedSubclasses()` trả `null`.
- Hàm đệ quy dừng tại đó.

Điều này đúng với thiết kế: nhánh `Polygon` mở cho các kiểu kế thừa khác, nên API không thể đưa ra một danh sách đóng gồm mọi lớp con tương lai.

`Rectangle` lại là sealed, nên chương trình có thể tiếp tục lấy `FilledRectangle`. `Circle` là final record nên cũng không có cây con để duyệt.

## 6. Duyệt đệ quy một hierarchy nhiều cấp

Một hàm duyệt cây thường có cấu trúc:

1. In kiểu hiện tại.
2. Kiểm tra `isSealed()`.
3. Nếu không sealed, dừng nhánh.
4. Nếu sealed, lấy `getPermittedSubclasses()`.
5. Duyệt tiếp từng kiểu con trực tiếp.

Có thể viết theo cách tường minh:

~~~java
static void inspect(Class<?> type) {
    System.out.println("Type: " + type.getName());

    if (!type.isSealed()) {
        System.out.println("  No permitted-subclass list");
        return;
    }

    Class<?>[] children = type.getPermittedSubclasses();

    if (children.length == 0) {
        System.out.println("  No permitted direct subclasses");
        return;
    }

    for (Class<?> child : children) {
        System.out.println("  Permitted: " + child.getName());
    }
}
~~~

Nếu muốn dựng cây nhiều cấp, hãy gọi lại hàm cho từng phần tử. Với hierarchy hợp lệ, các cạnh kế thừa không tạo chu trình; tuy nhiên, công cụ tổng quát vẫn có thể dùng một tập `Set<Class<?>>` để tránh xử lý lặp khi cùng một interface xuất hiện qua nhiều nhánh hoặc khi kết hợp nhiều gốc.

### 6.1. Dừng tại nhánh `non-sealed`

Reflection chỉ liệt kê được tập đóng của kiểu sealed. Khi gặp một permitted subclass được khai báo `non-sealed`, nhánh đó có thể mở rộng bởi những kiểu khác mà không cần cập nhật danh sách `permits` của tổ tiên.

Ví dụ:

~~~java
sealed interface Event permits Completed, Retryable {
}

record Completed() implements Event {
}

non-sealed class Retryable implements Event {
}

final class NetworkRetry extends Retryable {
}

final class DatabaseRetry extends Retryable {
}
~~~

`Event.class.getPermittedSubclasses()` trả `Completed` và `Retryable`. Nó không trả `NetworkRetry` hoặc `DatabaseRetry`, vì hai lớp này là hậu duệ của nhánh mở `Retryable` chứ không phải kiểu con trực tiếp của `Event`.

`Retryable.class.isSealed()` là `false`, và `Retryable.class.getPermittedSubclasses()` là `null`. Không có cách dùng hai API này để liệt kê mọi lớp có thể xuất hiện trong nhánh non-sealed.

## 7. Metadata trong bytecode: thuộc tính `PermittedSubclasses`

Hai API reflection lấy thông tin từ metadata của class file. Theo JVM Specification, một class file của sealed class/interface chứa thuộc tính:

~~~text
PermittedSubclasses
~~~

Thuộc tính này ghi lại các tên kiểu được phép **trực tiếp** kế thừa hoặc triển khai kiểu hiện tại. JVM dùng metadata này khi tạo/nạp một kiểu có quan hệ kế thừa tương ứng để kiểm tra nó có nằm trong tập được phép hay không.

Điểm đáng chú ý:

- Trong class file không có một cờ access riêng tên `ACC_SEALED` tương đương `ACC_FINAL`.
- Sự hiện diện của thuộc tính `PermittedSubclasses` thể hiện kiểu sealed ở cấp class file.
- Một class `final` có cờ `ACC_FINAL` và không có thuộc tính `PermittedSubclasses`.
- Reflection `Class.isSealed()` và `Class.getPermittedSubclasses()` cung cấp cách đọc metadata này qua API Java cấp cao.

Có thể xem bytecode bằng công cụ `javap` trong JDK:

~~~text
javap -v -classpath out SealedReflectionDemo$Shape
~~~

Khi chạy trong shell, hãy đặt tên class có dấu `$` trong dấu nháy phù hợp với shell để tránh biến môi trường bị mở rộng. Trong output verbose, tìm phần `PermittedSubclasses:`.

Không cần tự parse file class trong ứng dụng thông thường. Dùng `Class` reflection để đọc thông tin; `javap -v` phù hợp khi học bytecode hoặc điều tra metadata.

## 8. Reflection không đồng nghĩa với quyền truy cập thành viên

`getPermittedSubclasses()` trả về các đối tượng `Class<?>` để mô tả kiểu con được phép. Nó **không**:

- Tạo instance của kiểu con.
- Gọi constructor.
- Đọc/ghi field private.
- Mở quyền truy cập vào method private.
- Bỏ qua ranh giới module hoặc package.

Ví dụ, sau khi có:

~~~java
Class<?>[] permitted = PaymentResult.class.getPermittedSubclasses();
~~~

bạn có thể gọi các phương thức mô tả kiểu như:

~~~java
for (Class<?> child : permitted) {
    System.out.println(child.getName());
    System.out.println(child.getPackageName());
    System.out.println(child.getModule().getName());
    System.out.println(child.isInterface());
    System.out.println(child.isRecord());
}
~~~

Những thao tác trên chỉ đọc thông tin mô tả kiểu. Nếu muốn gọi constructor hoặc truy cập thành viên phản chiếu, phải tuân thủ quy tắc truy cập Java và ranh giới module tương ứng. Không cần dùng `setAccessible(true)` chỉ để xem danh sách permitted subclasses.

### 8.1. `getPermittedSubclasses()` không thay thế `getDeclaredClasses()`

Hai phương thức trả lời hai câu hỏi khác nhau:

| API | Câu hỏi |
|---|---|
| `getPermittedSubclasses()` | Những kiểu con/interface con trực tiếp nào được phép kế thừa/triển khai kiểu sealed này? |
| `getDeclaredClasses()` | Những class/interface nào được khai báo như member type bên trong class/interface này? |

Kiểu con được phép có thể là top-level class ở cùng package hoặc module, không nhất thiết là nested class. Ngược lại, một nested class có thể không liên quan tới danh sách `permits`.

Vì vậy, không dùng `getDeclaredClasses()` để thay thế `getPermittedSubclasses()` khi mục tiêu là kiểm tra hierarchy sealed.

## 9. Tên kiểu, class loader và module

`getPermittedSubclasses()` trả về class token đã được nạp, không trả danh sách chuỗi tên thuần túy. Điều này có một số hệ quả khi làm việc với ứng dụng nhiều module hoặc class loader.

### 9.1. Dùng class token thay vì so sánh tên chuỗi

Ưu tiên:

~~~java
if (child == Approved.class) {
    // Đúng cùng một đối tượng Class.
}
~~~

Không nên chỉ dựa vào:

~~~java
if (child.getName().equals("example.Approved")) {
    // Chỉ so sánh tên.
}
~~~

Hai class có cùng binary name nhưng được định nghĩa bởi hai class loader khác nhau vẫn có thể là hai kiểu runtime khác nhau. So sánh đối tượng `Class` giúp giữ đúng identity của kiểu.

### 9.2. Class loader dùng để lấy các kiểu con

Khi gọi `getPermittedSubclasses()`, Java cố gắng lấy class token cho từng kiểu được ghi trong metadata bằng **defining class loader của class/interface hiện tại**.

Nếu một permitted type không thể được lấy thành đối tượng `Class`, API quy định kiểu đó được bỏ qua khỏi mảng trả về. Vì vậy, trong môi trường triển khai động hoặc class loader tùy chỉnh, mảng trả về có thể không chứa mọi tên được ghi trong metadata.

Đây là lý do nên xem kết quả reflection như **các kiểu con mà runtime có thể lấy được**, đồng thời chú ý cấu hình class loader khi xây dựng plugin system hoặc framework.

### 9.3. Ràng buộc package và module của hierarchy sealed

Ở cấp ngôn ngữ Java:

- Nếu kiểu sealed nằm trong một **named module**, các kiểu con trực tiếp được phép phải nằm trong cùng module.
- Nếu kiểu sealed nằm trong **unnamed module**, các kiểu con trực tiếp được phép phải nằm trong cùng package.

Các ràng buộc này giúp hierarchy sealed được quản lý trong cùng ranh giới module hoặc package. Khi reflection hiển thị kiểu con, bạn có thể kiểm tra:

~~~java
System.out.println(type.getModule());
System.out.println(child.getModule());
System.out.println(type.getPackageName());
System.out.println(child.getPackageName());
~~~

Các thông tin trên hữu ích để chẩn đoán cấu hình module/package. Trong ứng dụng module hóa, hãy kiểm tra module descriptor và cách đóng gói class thay vì chỉ dựa vào tên package.

## 10. Phân biệt kiểu con trực tiếp bằng các API reflection khác

`getPermittedSubclasses()` đã trả về các kiểu con trực tiếp theo hợp đồng API. Để hiểu sự khác nhau giữa quan hệ trực tiếp và gián tiếp, có thể xem:

- `getSuperclass()`: lớp cha trực tiếp của một class.
- `getInterfaces()`: các interface được class hoặc interface triển khai/mở rộng trực tiếp.

Ví dụ:

~~~java
sealed interface Result permits Success, Failure {
}

sealed interface Success extends Result permits CachedSuccess {
}

record CachedSuccess(String value) implements Success {
}

record Failure(String message) implements Result {
}
~~~

Với `Result.class.getPermittedSubclasses()`, kết quả là `Success` và `Failure`. `CachedSuccess` không nằm trong mảng này vì nó trực tiếp triển khai `Success`.

Có thể kiểm tra trực tiếp:

~~~java
System.out.println(CachedSuccess.class.getInterfaces()[0].getName());
~~~

Kết quả cho thấy interface trực tiếp của `CachedSuccess` là `Success`. Với class, `getSuperclass()` cho biết lớp cha trực tiếp. Không nên dùng `isAssignableFrom()` để thay cho kiểm tra direct relationship, vì phương thức đó cũng trả `true` với quan hệ kế thừa gián tiếp.

## 11. Xây dựng tiện ích kiểm tra một sealed type

Một tiện ích nhỏ có thể trả về danh sách kiểu con trực tiếp theo thứ tự tên ổn định:

~~~java
import java.util.Arrays;
import java.util.Comparator;
import java.util.List;

static List<Class<?>> permittedTypesOf(Class<?> type) {
    if (!type.isSealed()) {
        throw new IllegalArgumentException(
                type.getName() + " is not sealed");
    }

    return Arrays.stream(type.getPermittedSubclasses())
            .sorted(Comparator.comparing(Class::getName))
            .toList();
}
~~~

`List.copyOf` hoặc `Stream.toList()` có thể được dùng để tạo collection chỉ đọc tùy phiên bản Java. Ở Java 17, `Stream.toList()` đã có sẵn và trả về danh sách không sửa được.

Một cách dùng:

~~~java
permittedTypesOf(PaymentResult.class)
        .forEach(type ->
                System.out.println(type.getSimpleName()));
~~~

Nếu cần kiểm tra một kiểu cụ thể có thuộc danh sách được phép:

~~~java
static boolean isPermittedDirectly(
        Class<?> sealedType, Class<?> candidate) {

    if (!sealedType.isSealed()) {
        return false;
    }

    return Arrays.stream(sealedType.getPermittedSubclasses())
            .anyMatch(permitted -> permitted == candidate);
}
~~~

Đoạn mã này kiểm tra identity của class token và chỉ xét các kiểu con trực tiếp. Nó không trả `true` cho một hậu duệ ở cấp sâu hơn.

## 12. Các giới hạn và trường hợp biên

### 12.1. Mảng trả về không được sắp xếp

Không viết test giả định phần tử đầu tiên luôn là kiểu A, phần tử thứ hai luôn là kiểu B. Nếu cần kết quả ổn định cho log, UI hoặc snapshot test, hãy sắp xếp theo `getName()` hoặc `getCanonicalName()`.

### 12.2. Không phải mọi permitted class đều xuất hiện trong mảng

API cố gắng lấy từng kiểu con bằng defining class loader của kiểu gốc. Nếu không lấy được một class token, kiểu đó bị bỏ qua. Vì vậy, mảng trả về phản ánh những kiểu có thể được lấy tại runtime; trong hệ thống class loader phức tạp, đừng xem nó là phép đọc nguyên văn mọi tên metadata.

### 12.3. `null` không có nghĩa là "sealed nhưng không có con"

`null` có nghĩa kiểu không sealed (bao gồm primitive, void và array). Mảng rỗng mới là giá trị không null nhưng không có phần tử. Hãy giữ hai trường hợp riêng trong logic.

### 12.4. Không thể liệt kê toàn bộ nhánh `non-sealed`

Khi một permitted subclass là `non-sealed`, các kiểu khác có thể kế thừa nó mà không được liệt kê ở gốc sealed. Hai API này chỉ có thể tiếp tục duyệt khi node hiện tại cũng là sealed.

### 12.5. Không có API `isNonSealed()`

Java 17 cung cấp `isSealed()`, nhưng không có `Class.isNonSealed()`. `false` có thể là class/interface thông thường, kiểu `final` hoặc kiểu `non-sealed`. Nếu kiểu đó đã được xác định là một direct permitted subclass hợp lệ, có thể kết hợp `isSealed()` với `Modifier.isFinal()` để hiểu nhánh cuối cùng:

- `isSealed() == true`: nhánh tiếp tục có danh sách permitted.
- `isSealed() == false` và modifier final: nhánh kết thúc.
- `isSealed() == false` và không final: với một direct permitted subtype hợp lệ, đây là nhánh `non-sealed`.

Đó là suy luận dựa trên ngữ cảnh hierarchy hợp lệ, không phải một cờ `non-sealed` riêng được reflection trả về.

## 13. Ứng dụng thực tế

### 13.1. Công cụ hiển thị hierarchy

IDE, tài liệu nội bộ hoặc công cụ phân tích có thể dùng hai API để trình bày các lựa chọn trực tiếp của một kiểu sealed. Việc sắp xếp kết quả theo tên giúp giao diện ổn định.

### 13.2. Kiểm tra model khi khởi động

Một framework có thể xác nhận rằng một interface plugin chỉ có những hiện thực trực tiếp được cho phép. Việc kiểm tra cần dựa vào class token đã nạp và không nên coi reflection là cơ chế xác thực đầu vào hoặc ranh giới bảo mật duy nhất.

### 13.3. Sinh test case theo từng biến thể

Khi kiểm thử một hàm nhận kiểu sealed, có thể lấy permitted direct types để nhắc nhóm phát triển bổ sung fixture cho từng nhánh. Nếu có nhánh sealed lồng nhau, duyệt đệ quy; nếu có nhánh non-sealed, phải kiểm thử theo hợp đồng của nhánh mở vì không thể liệt kê mọi hậu duệ.

### 13.4. Kiểm tra tính đầy đủ của bộ chuyển đổi

Ví dụ một bộ chuyển đổi nhận `PaymentResult` và cần ánh xạ từng biến thể sang DTO. Reflection có thể giúp phát hiện khi danh sách kiểu con trực tiếp thay đổi giữa các phiên bản. Tuy nhiên, reflection không tự chứng minh từng nhánh chuyển đổi đúng; vẫn cần test hành vi và expected output.

## 14. Bài tập thực hành

### Bài tập 1 — Kiểm tra kiểu sealed

Tạo ba kiểu:

~~~java
sealed interface Message permits TextMessage, BinaryMessage {
}

record TextMessage(String text) implements Message {
}

record BinaryMessage(byte[] data) implements Message {
}
~~~

Viết chương trình in kết quả `isSealed()` cho `Message.class`, `TextMessage.class`, `String.class` và `int[].class`. Giải thích từng kết quả.

### Bài tập 2 — Đọc danh sách permitted trực tiếp

Dùng `Message.class.getPermittedSubclasses()` để in tên đầy đủ của từng kiểu. Sắp xếp theo tên trước khi in. Thử đổi thứ tự các kiểu trong `permits` và quan sát vì sao không nên dựa vào thứ tự mảng.

### Bài tập 3 — Phân biệt direct và indirect

~~~java
sealed interface Root permits Branch, Leaf {
}

sealed interface Branch extends Root permits Twig {
}

record Twig() implements Branch {
}

record Leaf() implements Root {
}
~~~

Xác định kết quả của `Root.class.getPermittedSubclasses()` và `Branch.class.getPermittedSubclasses()`. Vì sao `Twig` không xuất hiện trong danh sách của `Root`?

### Bài tập 4 — Dừng tại non-sealed

Thêm `non-sealed class OpenBranch implements Root` và một lớp `final class Extension extends OpenBranch`. Hãy giải thích vì sao `Extension` không xuất hiện trong kết quả của `Root.class.getPermittedSubclasses()` và vì sao `OpenBranch.class.getPermittedSubclasses()` trả `null`.

### Bài tập 5 — Phân biệt null và mảng rỗng

Viết một phương thức nhận `Class<?>`, kiểm tra `isSealed()` rồi in một trong ba trạng thái: không sealed, sealed nhưng danh sách rỗng, sealed có các kiểu con. Vì sao phải kiểm tra `null` trước khi đọc `length`?

### Bài tập 6 — Duyệt cây nhiều cấp

Dùng hierarchy `Shape` ở phần 5. Viết hàm đệ quy in từng kiểu theo cấp thụt lề, sắp xếp tên con. Đảm bảo nhánh `Polygon` không gây lỗi null khi gọi `getPermittedSubclasses()`.

### Gợi ý tự đối chiếu

- Bài 1: `Message` sealed; hai record và `String` không sealed; mảng `int[]` không sealed.
- Bài 2: Lấy mảng, dùng `Arrays.stream(...).sorted(...)` rồi in `getName()`.
- Bài 3: `Root` trả `Branch` và `Leaf`; `Branch` trả `Twig`.
- Bài 4: `OpenBranch` là non-sealed nên API trả `null`; hậu duệ của nó không thuộc danh sách trực tiếp của `Root`.
- Bài 5: `null` biểu thị kiểu không sealed; mảng rỗng là trường hợp sealed nhưng không có phần tử được trả về.
- Bài 6: Kiểm tra `isSealed()` hoặc kiểm tra mảng `null` trước khi stream.

## 15. Những nguyên tắc cần ghi nhớ

- `Class.isSealed()` và `Class.getPermittedSubclasses()` có từ Java 17, dùng được mà không cần preview.
- `isSealed()` kiểm tra class/interface được đại diện bởi class token hiện tại; hãy dùng class token của kiểu cha khi muốn kiểm tra contract sealed.
- `getPermittedSubclasses()` trả về `Class<?>[]` của các kiểu con/interface con trực tiếp được phép.
- Thứ tự mảng không được bảo đảm; sắp xếp nếu cần output ổn định.
- Kiểu không sealed trả `null`; kiểu sealed có thể trả mảng rỗng hoặc mảng có các kiểu con.
- Reflection chỉ cho biết các kiểu con trực tiếp; muốn xem cây nhiều cấp phải duyệt đệ quy.
- Nhánh `non-sealed` mở rộng không giới hạn danh sách, nên hai API này không thể liệt kê mọi hậu duệ của nhánh đó.
- `Class.isSealed()` không phải `Modifier.isSealed()`; Java 17 không có modifier flag riêng cho sealed trong `Modifier`.
- Metadata class file dùng thuộc tính `PermittedSubclasses`; `javap -v` có thể giúp quan sát bytecode.
- `getPermittedSubclasses()` cố lấy các class token bằng defining class loader của kiểu gốc; kiểu không lấy được bị bỏ qua.
- Hai API chỉ đọc cấu trúc kiểu; chúng không tạo object hoặc mở quyền truy cập vào thành viên private.

### Tài liệu tham khảo

- [Java SE 17 API — Class.isSealed() và Class.getPermittedSubclasses()](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html).
- [Java SE 17 Language Specification — Section 8.1.6: Permitted Direct Subclasses](https://docs.oracle.com/javase/specs/jls/se17/html/jls-8.html#jls-8.1.6).
- [Java SE 17 Language Specification — Section 9.1.4: Permitted Direct Subclasses and Subinterfaces](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.1.4).
- [Java Virtual Machine Specification — Section 4.7.31: The PermittedSubclasses Attribute](https://docs.oracle.com/javase/specs/jvms/se17/html/jvms-4.html#jvms-4.7.31).
- [JEP 409 — Sealed Classes](https://openjdk.org/jeps/409).
