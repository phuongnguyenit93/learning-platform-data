# Tính bất biến quan sát được và mảng trả về từ annotation trong Java Core

Một annotation trong Java mô tả **metadata đã được khai báo** trên chương trình, không phải một object cấu hình có thể thay đổi tùy ý khi ứng dụng đang chạy. Tuy nhiên, annotation element được phép có kiểu mảng như `String[]`, `int[]` hoặc `Rule[]`; trong Java, bản thân mảng là đối tượng **có thể sửa phần tử**. Vì thế, có một câu hỏi quan trọng: nếu gọi `annotation.roles()`, nhận được `String[]` rồi sửa phần tử của nó, liệu metadata trong annotation có bị đổi theo không?

Với những annotation instance do cơ chế Reflection chuẩn của JDK trả về, câu trả lời có thể kiểm chứng là **không**: việc sửa mảng nhận về không làm thay đổi giá trị các element được quan sát khi đọc annotation về sau. Cơ chế thực thi thông dụng bảo vệ giá trị mảng nội bộ bằng **defensive copy** khi cần thiết. Dẫu vậy, mảng mà code gọi nhận được **vẫn là một mảng Java bình thường và có thể sửa**, và người dùng API không nên phụ thuộc vào danh tính tham chiếu của mảng trả về.

Bài này giải thích chính xác khái niệm *bất biến quan sát được* (*observable immutability*), cách hoạt động của mảng annotation, ngoại lệ mảng rỗng, hợp đồng `equals`/`hashCode` và những điều cần lưu ý khi viết thư viện xử lý annotation.

## 1. Mục tiêu

Sau khi học, bạn có thể:

- Phân biệt metadata annotation có giá trị ổn định với việc **mảng trả về có thể thay đổi cục bộ**.
- Giải thích vì sao sửa `String[]`, `int[]` hoặc mảng annotation lồng nhau lấy từ annotation không nên thay đổi các lần đọc tiếp theo.
- Hiểu **defensive copy** và tại sao không được dựa vào `==` để so sánh các mảng trả về.
- Biết lý do mảng rỗng là trường hợp đặc biệt: không có phần tử để sửa, nên danh tính mảng là chi tiết không nên dùng làm hợp đồng.
- Dùng `Arrays.toString`, `Arrays.equals`, `Arrays.hashCode` đúng cách khi làm việc với các giá trị mảng.
- Phân biệt hợp đồng bằng nhau của **hai annotation** với tính bằng nhau tham chiếu của hai mảng.
- Kiểm tra giá trị mặc định bằng `Method.getDefaultValue()` mà không nhầm với giá trị hiệu lực của một annotation cụ thể.
- Nhận ra sự khác biệt giữa annotation được Java Reflection tạo ra và một implementation tùy ý do người dùng tự viết.

## 2. Annotation element có kiểu mảng trông như thế nào?

Trong Java, một annotation type được khai báo bằng `@interface`. Một element có kiểu mảng được viết giống method không tham số:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Access {
    String[] roles() default {"reader", "writer"};
    int[] ports() default {8080, 8443};
}
~~~

Đây là khai báo minh họa, chưa có `main`. Khi dùng `@Access` mà không truyền hai element, các giá trị hiệu lực của chúng lần lượt là mảng hai chuỗi và mảng hai số nguyên.

Mỗi element của annotation có kiểu được Java giới hạn: primitive, `String`, `Class`, enum, annotation type hoặc **mảng một chiều** của những loại đó. Không thể khai báo `List<String> roles()` hay `String[][] roles()` như annotation element hợp lệ. Annotation element cũng không nhận `null`.

Tại nơi sử dụng, có thể ghi đè:

~~~java
@Access(roles = {"admin"}, ports = {9000})
class AdminEndpoint {}
~~~

Nếu gọi `getAnnotation(Access.class).roles()`, bạn nhận được một đối tượng có kiểu `String[]`. Về mặt API, phần tử mảng có thể được sửa:

~~~java
Access annotation = AdminEndpoint.class.getAnnotation(Access.class);
String[] local = annotation.roles();
local[0] = "guest";  // Hợp lệ với biến local, nhưng không sửa annotation.
~~~

**Điểm cần phân biệt:** Việc phép gán trên không ném lỗi không chứng minh annotation đã bị chỉnh sửa. Nó chỉ chứng minh `local` tham chiếu tới một đối tượng mảng Java có thể thay đổi.

## 3. “Bất biến quan sát được” nghĩa là gì?

Giả sử annotation ban đầu có `roles = {"reader", "writer"}`.

~~~java
String[] snapshot = annotation.roles();
snapshot[0] = "modified";

System.out.println(Arrays.toString(snapshot));
System.out.println(Arrays.toString(annotation.roles()));
~~~

Trong thực thi Reflection chuẩn thường gặp ở JDK hiện đại, kết quả tương ứng là:

~~~text
[modified, writer]
[reader, writer]
~~~

Mảng `snapshot` là phần dữ liệu **code gọi đang giữ**. Khi bạn sửa `snapshot[0]`, chỉ snapshot bị thay đổi. Một lần gọi `annotation.roles()` khác vẫn cho thấy giá trị metadata ổn định.

**Bất biến quan sát được** ở đây nghĩa là: thông qua API Reflection bình thường, code tiêu thụ annotation không thể làm giá trị annotation đã được định nghĩa trong class file thay đổi chỉ bằng cách sửa phần tử của mảng được trả về. Nó **không** có nghĩa bản thân mảng được trả về là immutable collection.

Đừng nhầm ba khái niệm:

| Khái niệm | Điều đúng |
| --- | --- |
| Metadata annotation | Giá trị khai báo hoặc giá trị mặc định được đọc một cách ổn định trong điều kiện annotation type và môi trường không thay đổi |
| `String[]` / `int[]` nhận về | Là mảng Java bình thường, có thể gán lại phần tử của bản sao |
| Sự thay đổi ở snapshot | Không phản ánh thành một thay đổi lên giá trị annotation trong các lần đọc sau |

Ở đây nói về việc dùng API Reflection công khai theo mục đích thông thường. Các cơ chế can thiệp cấp thấp không được hỗ trợ, thay bytecode, nạp lại class hoặc tự triển khai giao diện annotation nằm ngoài bài toán và không nên dùng làm bằng chứng rằng API cho phép sửa metadata.

## 4. Defensive copy: vì sao sửa mảng không làm đổi giá trị annotation?

Một implementation annotation do JDK tạo có nhiệm vụ trả về giá trị từng element. Để bảo vệ metadata, implementation thường thực hiện ý tưởng sau đối với mảng **có phần tử**:

~~~java
// MÃ MÔ PHỎNG Ý TƯỞNG, không phải định nghĩa thật của JDK.
String[] storedRoles = {"reader", "writer"};

String[] readRoles() {
    return storedRoles.clone();
}
~~~

`clone()` tạo một đối tượng mảng mới với các phần tử được sao chép sang. Nếu code gọi sửa mảng này, `storedRoles` không bị ảnh hưởng.

Ví dụ:

~~~java
String[] a = {"reader", "writer"};
String[] b = a.clone();
b[0] = "modified";

System.out.println(Arrays.toString(a)); // [reader, writer]
System.out.println(Arrays.toString(b)); // [modified, writer]
System.out.println(a == b);             // false
~~~

`clone()` của mảng là **shallow copy**: nó sao chép các phần tử; nếu phần tử là tham chiếu, đối tượng được tham chiếu không bị sao chép sâu. Nhưng annotation element không cho phép một mảng `List<Object>` hoặc một mảng các Java object mutable tùy ý. Các kiểu phần tử hợp lệ như chuỗi, `Class`, enum, annotation instance hoặc primitive làm cho việc bảo vệ giá trị được quản lý theo hợp đồng annotation đơn giản hơn.

Trong các bản OpenJDK, cơ chế gọi element trên annotation proxy xử lý việc nhân bản mảng **không rỗng** khi trả về. Đây là một **chi tiết thực thi hữu ích để hiểu và tự kiểm chứng**, không phải lý do để xây dựng logic phụ thuộc vào object identity cụ thể của lần gọi `roles()`.

### Mảng một phần tử hoặc nhiều phần tử

Đối với một array element có dữ liệu, việc sao chép giúp tránh lỗi “external code sửa phần tử rồi giá trị annotation thay đổi”. Chương trình hoàn chỉnh ở phần 6 kiểm tra điều này cho `String[]`, `int[]` và `Note[]`.

### Mảng rỗng

Với `String[] empty() default {}`, độ dài mảng là `0`. Không có `empty()[0]` để gán vì sẽ ném `ArrayIndexOutOfBoundsException`. Do đó, một implementation có thể **tái sử dụng mảng rỗng** thay vì nhân bản nó mà không tạo cơ hội sửa phần tử.

Không dựa vào:

~~~java
// KHÔNG dùng như một điều kiện nghiệp vụ.
boolean same = annotation.empty() == annotation.empty();
~~~

Giá trị `same` không phải tiêu chí xác định annotation có bất biến hay không. API của bạn nên quan tâm đến `annotation.empty().length == 0` và nội dung mảng, không phải đồng nhất đối tượng của mảng.

## 5. Mảng annotation lồng nhau cũng được bảo vệ

Annotation element không chỉ có `String[]`, `int[]`; nó còn có thể trả về **mảng các annotation khác**:

~~~java
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;

@Retention(RetentionPolicy.RUNTIME)
@interface Note {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@interface Settings {
    Note[] notes() default {
        @Note("stable"),
        @Note("audited")
    };
}
~~~

Mã trên là khai báo minh họa. Khi gọi `settings.notes()`, bạn nhận một `Note[]`. Bạn có thể viết:

~~~java
Note[] snapshots = settings.notes();
snapshots[0] = null;
~~~

Nhưng việc gán `null` ở **bản sao của mảng** không có nghĩa phần tử `Note` được khai báo trong metadata đã bị xóa. Đọc lại `settings.notes()[0].value()` vẫn trả giá trị được định nghĩa.

Đừng nhầm:

- `@Note("stable")` là **annotation instance**, có element `value()`; nó không có setter `setValue(...)`.
- `Note[]` là một **mảng tham chiếu** chứa những annotation instance đó, cho phép code gọi thay phần tử **trong mảng trả về**.
- Việc mảng được sao chép không có nghĩa có một constructor Java `new Note(...)` hay một phép copy sâu của object annotation.

Nếu annotation lồng nhau lại có element kiểu mảng, hãy đọc các element của nó qua API annotation riêng. Đừng viết thư viện dựa trên việc sửa `settings.notes()[0].values()[0]` để cập nhật metadata: đây là những snapshot có thể sửa cục bộ chứ không phải kênh thay đổi cấu hình.

## 6. Ví dụ Java 17+ chạy độc lập và kết quả chính xác

Tạo **một file duy nhất** tên `AnnotationArraySafetyDemo.java`, đặt các class/annotation phụ trong cùng file, không khai báo `package` để tiện chạy:

~~~java
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Note {
    String value();
}

@Retention(RetentionPolicy.RUNTIME)
@Target(ElementType.TYPE)
@interface Settings {
    String[] roles() default {"reader", "writer"};
    int[] ports() default {8080, 8443};
    Note[] notes() default {@Note("stable")};
    String[] empty() default {};
}

@Settings
class Service {}

@Settings
class ServiceCopy {}

public class AnnotationArraySafetyDemo {
    public static void main(String[] args)
            throws NoSuchMethodException {

        Settings settings = Service.class.getAnnotation(Settings.class);

        String[] rolesSnapshot = settings.roles();
        rolesSnapshot[0] = "modified";

        int[] portsSnapshot = settings.ports();
        portsSnapshot[0] = 0;

        Note[] notesSnapshot = settings.notes();
        notesSnapshot[0] = null;

        System.out.println("roles=" + Arrays.toString(settings.roles()));
        System.out.println("ports=" + Arrays.toString(settings.ports()));
        System.out.println("note=" + settings.notes()[0].value());
        System.out.println("firstSnapshot="
                + Arrays.toString(rolesSnapshot));
        System.out.println("sameArray="
                + (rolesSnapshot == settings.roles()));

        Settings copy =
                ServiceCopy.class.getAnnotation(Settings.class);
        System.out.println("equals=" + settings.equals(copy));
        System.out.println("hashEqual="
                + (settings.hashCode() == copy.hashCode()));
        System.out.println("emptyLength=" + settings.empty().length);

        Object defaultRoles =
                Settings.class.getMethod("roles").getDefaultValue();
        System.out.println("declaredDefault="
                + Arrays.toString((String[]) defaultRoles));
    }
}
~~~

Biên dịch và chạy bằng JDK 17 hoặc mới hơn:

~~~bash
javac -encoding UTF-8 AnnotationArraySafetyDemo.java
java AnnotationArraySafetyDemo
~~~

**Stdout:**

~~~text
roles=[reader, writer]
ports=[8080, 8443]
note=stable
firstSnapshot=[modified, writer]
sameArray=false
equals=true
hashEqual=true
emptyLength=0
declaredDefault=[reader, writer]
~~~

### Diễn giải từng dòng

1. `roles=[reader, writer]`: dù `rolesSnapshot[0]` đã bị gán `"modified"`, lần đọc mới qua `settings.roles()` vẫn nhìn thấy hai chuỗi gốc.
2. `ports=[8080, 8443]`: thay `portsSnapshot[0]` thành `0` không thay thế giá trị `int[]` của annotation.
3. `note=stable`: thay phần tử thứ nhất của `notesSnapshot` bằng `null` chỉ thay đổi snapshot. Annotation `@Note("stable")` trong dữ liệu gốc vẫn đọc được.
4. `firstSnapshot=[modified, writer]`: mảng được code gọi giữ trong biến local đúng là **mutable**. Đây là nửa còn lại của sự phân biệt quan trọng.
5. `sameArray=false`: với implementation OpenJDK thông dụng và mảng không rỗng, lần gọi sau tạo một array copy riêng. **Đây là quan sát thực nghiệm của ví dụ, không nên dùng phép `==` như hợp đồng API tổng quát.**
6. `equals=true`: `@Settings` trên `Service` và `ServiceCopy` có cùng những giá trị element, nên hai annotation tương đương **theo giá trị**, dù gắn lên hai class khác nhau.
7. `hashEqual=true`: hai annotation tương đương theo `equals` có cùng hash code. Việc code gọi sửa một snapshot bên ngoài không làm đổi nội dung annotation được dùng để tính hash.
8. `emptyLength=0`: mặc định `empty() default {}` biểu diễn mảng rỗng hợp lệ, không phải `null`.
9. `declaredDefault=[reader, writer]`: Reflection đọc **giá trị mặc định khai báo trên annotation type** bằng `Method.getDefaultValue()`; đây không phải biến chung để ghi cấu hình runtime.

Lưu ý `Settings.class.getMethod("roles")` lấy một `Method` mô tả element `roles()` của annotation type. `getDefaultValue()` trả `Object`; mã ép kiểu `String[]` vì biết đúng kiểu element được khai báo. Nếu element không có default thì API này trả `null`, không có nghĩa annotation element được phép nhận `null` làm giá trị.

Đoạn code chính không giả định định dạng cụ thể của `annotation.toString()` vì định dạng đó có phần phụ thuộc implementation. Mọi dòng stdout trong ví dụ đều được tạo bằng các phép đọc/so sánh đã chỉ rõ.

## 7. `equals` và `hashCode` của annotation có phần tử mảng

Interface `java.lang.annotation.Annotation` định nghĩa hợp đồng `equals` dựa trên **annotation type và từng giá trị của các element**. Hai annotation không cần là **cùng một object reference** để được coi là bằng nhau.

Đối với element có kiểu mảng, Java so sánh nội dung theo hàm `Arrays.equals` tương ứng, không dùng phép `==` giữa hai array references. Điều này có ý nghĩa lớn:

~~~java
String[] left = {"reader", "writer"};
String[] right = {"reader", "writer"};

System.out.println(left == right);             // false
System.out.println(Arrays.equals(left, right)); // true
~~~

Nếu cùng một annotation type có các giá trị element giống nhau, hai instance annotation phải được coi là tương đương theo hợp đồng của `Annotation.equals`. Mảng được trả về có thể là hai object khác nhau nhưng nội dung ban đầu vẫn giống nhau.

`Annotation.hashCode` cũng dựa trên **member names và member values**. Đối với giá trị mảng, dùng quy tắc hash theo nội dung tương ứng với `Arrays.hashCode`. Đối với annotation lồng nhau, quy tắc áp dụng đệ quy theo hợp đồng của annotation.

Bạn không cần tự tính hash code bằng công thức thủ công trong ứng dụng thông thường. Nhưng cần biết:

- Đừng dùng `annotationA == annotationB` để thay cho `annotationA.equals(annotationB)`.
- Đừng dùng `annotationA.roles() == annotationB.roles()` để kiểm tra hai cấu hình có cùng role.
- Khi cần so sánh **riêng mảng giá trị**, dùng `Arrays.equals(a, b)` hoặc công cụ so sánh phần tử phù hợp.
- Khi cần so sánh **toàn bộ annotation**, dùng `Annotation.equals`; nó có hợp đồng riêng cho từng element và mảng.
- Không xây dựng cache dựa trên khả năng sửa array snapshots để làm thay đổi `annotation.hashCode()`: sự sửa đó không nhằm làm biến đổi metadata gốc.

`toString()` hữu ích để debug nhưng định dạng cụ thể của annotation string có thể phụ thuộc JDK/implementation. Tránh dùng chuỗi `toString()` làm key dữ liệu bền vững hoặc kiểm tra chính xác bằng snapshot text thiếu kiểm soát phiên bản.

## 8. `getDefaultValue()` và giá trị hiệu lực: không đánh đồng

Có hai câu hỏi khác nhau khi đọc mảng annotation:

**A. “Annotation cụ thể trên một class đang có giá trị nào?”**

~~~java
Settings settings = Service.class.getAnnotation(Settings.class);
String[] effectiveRoles = settings.roles();
~~~

Kết quả ở đây là giá trị **hiệu lực**: giá trị trực tiếp được truyền ở nơi gắn annotation nếu có; nếu không có thì nhận mặc định của `Settings.roles()`.

**B. “Element `roles()` được khai báo với default nào?”**

~~~java
Object declaredDefault =
        Settings.class.getMethod("roles").getDefaultValue();
String[] defaults = (String[]) declaredDefault;
~~~

Kết quả ở đây là giá trị mặc định thuộc **annotation type**, bất kể `Service` có ghi đè `roles` hay không.

Ví dụ:

~~~java
@Settings(roles = {"admin"})
class AdminService {}
~~~

Trên `AdminService`, `settings.roles()` hiệu lực là `{"admin"}`, còn `Settings.class.getMethod("roles").getDefaultValue()` vẫn mô tả mặc định `{"reader", "writer"}`.

Với mảng do `getDefaultValue()` trả về, hãy coi nó là dữ liệu **chỉ đọc về mặt mục đích**, và tạo bản sao của riêng ứng dụng nếu cần chỉnh sửa để lập cấu hình khác. Không dùng thao tác sửa mảng Reflection trả về như một phương thức cập nhật default của annotation type.

Một đặc điểm nâng cao từ Java Language Specification: default được khai báo trên annotation type và được áp dụng **khi annotation được đọc**, không được chép thành element value tường minh vào mọi nơi dùng annotation. Việc thay đổi định nghĩa default ở phiên bản thư viện khác có thể làm giá trị hiệu lực thay đổi đối với những nơi dùng annotation đã bỏ qua element đó. Đây là chuyện **cập nhật định nghĩa annotation type**, không phải thao tác sửa snapshot mảng runtime.

## 9. Những điều không nên suy diễn

### 9.1. “Bất biến quan sát được” không có nghĩa mọi object thực thi interface annotation đều không thể viết code thay đổi

Bạn có thể có một implementation không chuẩn/tự xây dựng của annotation interface bằng Java, hoặc một proxy do ứng dụng tạo. Thậm chí có thể xây dựng một `InvocationHandler` tùy ý trả về reference mảng đang giữ rồi thay nó. Những object như vậy **không nhất thiết** có hành vi phòng vệ mảng giống annotation do Reflection chuẩn của JDK cung cấp.

Vì vậy, khi nói “annotation trả mảng copy”, cần đặt trong bối cảnh **annotation instance được tạo/đọc qua cơ chế Reflection chuẩn**. Không nên coi đây là một lời hứa về mọi object có thể được ép kiểu `Annotation` bất kể nguồn gốc.

### 9.2. Không giả định tất cả lần gọi element đều trả cùng array reference

`annotation.roles() == annotation.roles()` không phải câu hỏi nghiệp vụ đúng. Mảng không rỗng có thể được nhân bản khi trả; mảng rỗng có thể được dùng chung vì không có phần tử để sửa. Dùng nội dung và độ dài mảng, không dùng danh tính tham chiếu.

### 9.3. Không giả định defensive copy đồng nghĩa deep copy mọi thứ

Nếu `Note[]` được nhân bản, phép sao chép **mảng** không đồng nghĩa mỗi đối tượng `Note` cũng được sao chép theo. Với annotation standard, element của `Note` lại tuân theo hợp đồng annotation, vì thế bạn không dùng một setter trên `Note` để đổi metadata. Nếu xây dựng cấu trúc Java tùy ý bên ngoài annotation API, shallow copy có thể chưa đủ để bảo vệ những object mutable nằm trong mảng.

### 9.4. Không tự biến annotation thành nơi lưu trạng thái thay đổi

Nếu ứng dụng cần thêm/bớt role trong lúc chạy, giữ chúng trong một object cấu hình, collection có quản lý hoặc service state riêng. Annotation phù hợp hơn với mô tả **khai báo tĩnh** và những giá trị mà code xử lý đọc/diễn giải.

### 9.5. Không đánh đồng annotation với immutable collection

`List.of("reader", "writer")` trả một list không thể sửa; nhưng `annotation.roles()` trả `String[]`, cho phép sửa phần tử **của snapshot**. Gọi `Arrays.asList(annotation.roles())` có thể tạo một list view dựa trên mảng snapshot; sửa list view có thể thay snapshot nhưng không nhằm sửa annotation gốc. Nếu muốn sử dụng dữ liệu ở dạng không thể sửa trong code của bạn, chuyển sang cấu trúc bất biến do bạn kiểm soát, ví dụ `List.copyOf(Arrays.asList(annotation.roles()))`.

## 10. Lỗi thường gặp

**Lỗi 1 — Sửa mảng trả về rồi kỳ vọng thay đổi annotation.** `roles[0] = "admin"` chỉ sửa mảng code gọi đang giữ. Đọc lại annotation vẫn có giá trị khai báo; hãy đổi source annotation hoặc đổi hệ thống cấu hình runtime đúng cách.

**Lỗi 2 — Gọi mảng là immutable chỉ vì giá trị annotation ổn định.** `String[]` vẫn là mảng mutable. Bất biến ở đây là tính ổn định quan sát được của **metadata**, không phải việc Java cấm gán phần tử trên bản sao.

**Lỗi 3 — Dùng `==` so sánh mảng.** `String[] a = annotation.roles(); String[] b = annotation.roles();` có thể chứa giá trị bằng nhau dù `a == b` là `false`. Dùng `Arrays.equals(a, b)`.

**Lỗi 4 — Cho rằng mảng rỗng phải được clone mỗi lần.** Một mảng rỗng không có phần tử có thể bị đổi, nên implementation có thể tái sử dụng nó. Đừng viết assertion về identity của mảng rỗng.

**Lỗi 5 — Nhầm shallow copy và deep copy.** Mảng `Note[]` được copy ở cấp container không có nghĩa các Note instance cũng được tạo mới hoặc có cách sửa element value. Với annotation standard, các giá trị được đọc theo hợp đồng annotation riêng.

**Lỗi 6 — So sánh hai annotation bằng `==`.** Các proxy khác nhau có thể biểu diễn annotation tương đương. Dùng `equals` khi cần ngữ nghĩa bằng nhau của annotation.

**Lỗi 7 — Tự so `equals` bằng mảng với `Object.equals`.** Mảng Java kế thừa `Object.equals` theo identity; hợp đồng `Annotation.equals` yêu cầu so nội dung mảng. Dùng `Arrays.equals` khi tự xử lý member values.

**Lỗi 8 — Nghĩ `getDefaultValue()` là vùng cấu hình có thể sửa.** Method này dùng để **đọc default của annotation type**. Nếu cần xây cấu hình khác, clone dữ liệu sang object riêng.

**Lỗi 9 — Bỏ retention runtime.** Không có `@Retention(RUNTIME)` thì annotation type có retention mặc định `CLASS`; `Class.getAnnotation(...)` lúc chạy không nhìn thấy annotation. Demo chính đã chỉ rõ retention.

**Lỗi 10 — Nhầm `null` và mảng rỗng.** Annotation array element không được nhận `null`; `default {}` là mảng rỗng hợp lệ. `Method.getDefaultValue()` có thể trả `null` khi element **không có default**, nhưng đó là thông báo của Reflection chứ không phải một giá trị annotation hợp lệ.

**Lỗi 11 — In mảng bằng `println(array)` rồi kỳ vọng thấy danh sách.** Dùng `Arrays.toString(array)` cho mảng một chiều; với cấu trúc Java tùy ý nhiều tầng thì cân nhắc `Arrays.deepToString(...)`. Bản thân annotation element không được khai báo mảng nhiều chiều như `String[][]`.

**Lỗi 12 — Dựa vào `annotation.toString()` làm kiểm thử định dạng tuyệt đối.** Nội dung có thể hữu ích nhưng cú pháp chữ của phương thức này có phần phụ thuộc implementation. Thử nghiệm nên kiểm tra trực tiếp element values và các quan hệ `equals`/`hashCode`.

## 11. Bài tập thực hành

1. Chạy file `AnnotationArraySafetyDemo.java`. Trước khi chạy hãy dự đoán từng dòng stdout và giải thích vai trò của defensive copy.
2. Bỏ đoạn gán `rolesSnapshot[0] = "modified"`. Quan sát dòng `firstSnapshot` và `roles`, đối chiếu với phiên bản có sửa.
3. Thêm `String[] zones() default {"north", "south"};` vào `Settings`. Gọi `settings.zones()`, sửa phần tử trong snapshot rồi đọc lại để kiểm chứng.
4. Thêm `@Settings(roles = {"admin"})` lên một class khác và so sánh annotation mới với `@Settings` dùng default bằng `equals`; giải thích vì sao chúng không bằng nhau.
5. Thêm một class `@Settings(roles = {"reader", "writer"}, ports = {8080, 8443}, notes = {@Note("stable")})` nhưng không ghi `empty`. So sánh với `@Settings` chỉ sử dụng defaults. Giải thích vì sao `equals` xét **giá trị hiệu lực** chứ không đơn thuần xét liệu element có được ghi trực tiếp hay không.
6. Thử `settings.empty() == settings.empty()` trên môi trường JDK đang dùng. Ghi nhận kết quả, nhưng giải thích vì sao không được dùng đó làm logic portable.
7. Dùng `Settings.class.getMethod("ports").getDefaultValue()` để lấy mảng mặc định, ép kiểu `int[]`, in bằng `Arrays.toString` và phân biệt với việc lấy `settings.ports()`.
8. Thử `String[] a = settings.roles(); String[] b = settings.roles();` rồi so sánh `a == b` và `Arrays.equals(a, b)`. Giải thích sự khác nhau.
9. Tạo `Note[] copy = settings.notes(); copy[0] = null;`. Kiểm tra lại `settings.notes()[0].value()` và lý giải tại sao annotation value không biến mất.
10. Thiết kế một lớp `RuntimeConfig` chứa một `List<String>` có thể thay đổi theo yêu cầu nghiệp vụ, khởi tạo bằng `Arrays.asList(settings.roles())` rồi copy về cấu trúc phù hợp. Giải thích vì sao phải quản lý trạng thái này **bên ngoài** annotation.

## 12. Checklist cuối bài

| Câu hỏi | Câu trả lời cần nắm |
| --- | --- |
| Mảng trả về từ annotation có thể gán lại phần tử không? | Có, đó là mảng Java nhận về trong code gọi |
| Gán phần tử mảng có sửa annotation Reflection gốc không? | Với annotation chuẩn do JDK đọc, không |
| Defensive copy giúp gì? | Ngăn code bên ngoài sửa mảng nội bộ được dùng làm giá trị element |
| Mảng rỗng có nhất thiết tạo reference mới mỗi lần không? | Không nên dựa vào giả định đó |
| Hai mảng cùng nội dung có `==` không? | Không nhất thiết; dùng `Arrays.equals` |
| Hai annotation cùng type và cùng element values có bằng nhau không? | Có theo hợp đồng `Annotation.equals` |
| `Annotation.hashCode` có xét array contents không? | Có, theo quy tắc hash member values |
| `getDefaultValue()` đọc cái gì? | Default trên định nghĩa annotation type |
| Làm sao thực sự thay đổi cấu hình lúc chạy? | Dùng trạng thái/config riêng, không sửa snapshot annotation |

**Kết luận:** Annotation là metadata mà code có thể đọc và diễn giải. Khi element là một mảng, API vẫn trả kiểu mảng mutable, nhưng các bản sao phòng vệ của JDK giúp bảo toàn **giá trị annotation có thể quan sát ở những lần đọc sau**. Đừng nhầm sự sửa đổi của snapshot với thay đổi annotation, và hãy so sánh giá trị thay vì so sánh danh tính mảng.

### Tài liệu tham khảo

- [Java SE 17 — `java.lang.annotation.Annotation`: equals, hashCode, toString, annotationType](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/annotation/Annotation.html).
- [Java SE 17 — `java.lang.reflect.Method.getDefaultValue()`](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/reflect/Method.html#getDefaultValue()).
- [Java SE 17 — `java.util.Arrays`: toString, equals, hashCode](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/Arrays.html).
- [Java Language Specification 17 — `9.6.2`: Defaults for Annotation Interface Elements](https://docs.oracle.com/javase/specs/jls/se17/html/jls-9.html#jls-9.6.2).
