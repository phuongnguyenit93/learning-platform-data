# Trường hợp không sealed và kết quả API tương ứng

## 1. False không mô tả đầy đủ khả năng kế thừa

Khi khảo sát một kiểu bằng Reflection, câu hỏi:

~~~java
type.isSealed()
~~~

chỉ xác định kiểu đó có phải lớp hoặc interface sealed hay không.

Nếu kết quả là `false`, chưa thể kết luận rằng:

- Kiểu đó được khai báo bằng từ khóa `non-sealed`.
- Kiểu đó có thể được kế thừa tự do.
- Kiểu đó không có lớp con.
- Kiểu đó là một lớp có thể tạo đối tượng.
- Có thể gọi `getPermittedSubclasses()` rồi dùng kết quả như một mảng khác `null`.

Ví dụ, một lớp `final` không sealed nhưng cũng không cho tạo lớp con. Một lớp thường không final cũng không sealed, song có thể có nhiều lớp con. Interface thường, record, mảng và token primitive lại có những đặc điểm riêng.

Để hiểu đúng, cần tách **trạng thái sealed**, **các quy tắc kế thừa khác** và **danh sách các kiểu con được cho phép trực tiếp**.

## 2. Hai API và hợp đồng false/null

Các API trên `Class<?>`:

~~~java
public boolean isSealed();
public Class<?>[] getPermittedSubclasses();
~~~

Đây là các chữ ký rút gọn để minh họa; hai phương thức có trong Java 17 trở lên.

Hợp đồng quan trọng:

| Trạng thái kiểu đang xét | `isSealed()` | `getPermittedSubclasses()` |
| --- | --- | --- |
| Lớp hoặc interface sealed | `true` | Mảng khác `null`, có thể rỗng theo hợp đồng API |
| Lớp hoặc interface không sealed | `false` | `null` |
| Mảng, primitive hoặc `void` | `false` | `null` |

Vì vậy, với kiểu không sealed, **kết quả API là `null`, không phải mảng rỗng**. Đây là hành vi bình thường, không phải lỗi tải kiểu chỉ vì giá trị trả về bằng `null`.

Tài liệu [Class.isSealed](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#isSealed()) và [Class.getPermittedSubclasses](https://docs.oracle.com/en/java/javase/21/docs/api/java.base/java/lang/Class.html#getPermittedSubclasses()) nêu sự phân biệt này.

Điểm đối chiếu cần nhớ:

~~~text
null
    -> kiểu đang xét không sealed

mảng khác null
    -> kiểu đang xét sealed
    -> đọc các phần tử để biết các kiểu con trực tiếp mà API thu được
~~~

Không dùng riêng `permitted.length == 0` làm phép kiểm tra “không sealed”. Với kết quả `null`, biểu thức đó còn gây `NullPointerException`.

## 3. “Không sealed” khác với từ khóa non-sealed

Trong cách nói thông thường, “không sealed” có nghĩa `isSealed() == false`. Đây là một nhóm rộng.

Từ khóa `non-sealed` có ý nghĩa cụ thể trong ngôn ngữ Java: nó được dùng ở một nhánh trực tiếp của phân cấp sealed để cho phép nhánh đó tiếp tục mở rộng mà không giữ danh sách `permits` ở chính nhánh đó.

Ví dụ:

~~~java
sealed interface Root permits OpenBranch, End {
}

non-sealed class OpenBranch implements Root {
}

final class End implements Root {
}
~~~

Đây là một nhóm khai báo có thể đặt cùng tệp trong cùng package.

Cả `OpenBranch.class.isSealed()` và `End.class.isSealed()` đều trả về `false`, nhưng:

- `OpenBranch` cho phép tiếp tục tạo lớp con theo các quy tắc Java thông thường.
- `End` là lớp final nên không có lớp con.

Một lớp thường độc lập cũng có thể cho `false` mà không hề khai báo `non-sealed`.

Do đó, **không đổi tên kết quả `!type.isSealed()` thành “có modifier non-sealed”** trong công cụ phân tích. Các API `Class` dùng trong Java 17/21 của bài không có một phương thức `isNonSealed()` để đọc nguyên văn từ khóa đó.

Quy tắc về lớp sealed, final và non-sealed được mô tả tại [JLS §8.1.1.2](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.1.1.2).

## 4. Chương trình đầy đủ: đối chiếu các nhóm không sealed

Lưu chương trình sau vào `NotSealedApiDemo.java`:

~~~java
import java.lang.reflect.Modifier;
import java.util.Arrays;

public class NotSealedApiDemo {
    public sealed interface Root permits OpenBranch, OpenApi, End {
    }

    public static non-sealed class OpenBranch implements Root {
    }

    public non-sealed interface OpenApi extends Root {
    }

    public static final class End implements Root {
    }

    public static class Extension extends OpenBranch {
    }

    public static class Plain {
    }

    public static final class Closed {
    }

    public interface OrdinaryInterface {
    }

    public record Point(int x, int y) {
    }

    public enum Light {
        RED, GREEN
    }

    static void inspect(String label, Class<?> type) {
        Class<?>[] permitted = type.getPermittedSubclasses();
        String result = permitted == null ? "null"
                : Arrays.stream(permitted)
                        .map(Class::getSimpleName)
                        .sorted()
                        .toList()
                        .toString();
        System.out.println(label
                + " -> sealed=" + type.isSealed()
                + "; permitted=" + result);
    }

    public static void main(String[] args) {
        inspect("sealed root", Root.class);
        inspect("non-sealed class", OpenBranch.class);
        inspect("non-sealed interface", OpenApi.class);
        inspect("permitted final leaf", End.class);
        inspect("indirect extension", Extension.class);
        inspect("ordinary class", Plain.class);
        inspect("ordinary final class", Closed.class);
        inspect("ordinary interface", OrdinaryInterface.class);
        inspect("record", Point.class);
        inspect("enum without constant bodies", Light.class);
        inspect("String array", String[].class);
        inspect("sealed-root array", Root[].class);
        inspect("primitive int", int.class);
        inspect("void", void.class);

        System.out.println("Closed is final: "
                + Modifier.isFinal(Closed.class.getModifiers()));
        System.out.println("Plain is final: "
                + Modifier.isFinal(Plain.class.getModifiers()));
        System.out.println("Root accepts Extension: "
                + Root.class.isAssignableFrom(Extension.class));
        System.out.println("Extension is directly permitted by Root: "
                + Arrays.asList(Root.class.getPermittedSubclasses())
                        .contains(Extension.class));
    }
}
~~~

Biên dịch và chạy với JDK 17 trở lên, không cần preview:

~~~bash
javac --release 17 -encoding UTF-8 NotSealedApiDemo.java
java NotSealedApiDemo
~~~

Kết quả chính xác:

~~~text
sealed root -> sealed=true; permitted=[End, OpenApi, OpenBranch]
non-sealed class -> sealed=false; permitted=null
non-sealed interface -> sealed=false; permitted=null
permitted final leaf -> sealed=false; permitted=null
indirect extension -> sealed=false; permitted=null
ordinary class -> sealed=false; permitted=null
ordinary final class -> sealed=false; permitted=null
ordinary interface -> sealed=false; permitted=null
record -> sealed=false; permitted=null
enum without constant bodies -> sealed=false; permitted=null
String array -> sealed=false; permitted=null
sealed-root array -> sealed=false; permitted=null
primitive int -> sealed=false; permitted=null
void -> sealed=false; permitted=null
Closed is final: true
Plain is final: false
Root accepts Extension: true
Extension is directly permitted by Root: false
~~~

Danh sách permitted của `Root` được sắp xếp theo tên khi in. API không cam kết thứ tự các phần tử; việc sắp xếp làm kết quả trình bày ổn định.

### 4.1. Lớp thường và lớp final cùng cho false/null

Hai dòng:

~~~text
ordinary class -> sealed=false; permitted=null
ordinary final class -> sealed=false; permitted=null
~~~

có cùng cặp kết quả sealed, dù đặc điểm kế thừa khác nhau.

Nếu công cụ muốn biết một **lớp** có modifier final hay không, phải xem thuộc tính phù hợp như `Modifier.isFinal(type.getModifiers())`. Trong chương trình, `Closed` là final còn `Plain` không final.

Không suy “không sealed nghĩa là mở cho kế thừa” từ một giá trị boolean duy nhất. Việc kế thừa còn phụ thuộc loại kiểu, final, khả năng truy cập và các quy tắc ngôn ngữ khác.

### 4.2. Interface thường và interface non-sealed đều cho false/null

`OrdinaryInterface` không thuộc một khai báo sealed nào. `OpenApi` là interface non-sealed mở rộng trực tiếp `Root`.

Hai interface có bối cảnh khai báo khác nhau, nhưng đều không sealed ở chính kiểu đang xét, nên `getPermittedSubclasses()` đều trả về `null`.

`null` không phải danh sách rỗng các lớp đang triển khai interface. API này không có nhiệm vụ quét mọi lớp triển khai một interface mở.

### 4.3. Một kiểu con của sealed không nhất thiết sealed

`Root` sealed không làm mọi hậu duệ của nó cùng sealed.

Trong chương trình:

- `Root` có `isSealed() == true`.
- `OpenBranch`, `OpenApi` và `End` đều có `isSealed() == false`.
- Mỗi lần gọi API hỏi trạng thái của đúng token lớp hoặc interface nhận lời gọi.

Nếu cần xem trạng thái của cha, hãy lấy đúng token cha. Không kỳ vọng `OpenBranch.class.getPermittedSubclasses()` trả về danh sách khai báo trong `Root`.

### 4.4. Có lớp con thực tế nhưng permitted vẫn null

`Extension` là lớp con của `OpenBranch`. Tuy nhiên `OpenBranch` không sealed nên API permitted vẫn trả về `null`.

Hai dòng cuối chương trình còn cho thấy:

~~~text
Root accepts Extension: true
Extension is directly permitted by Root: false
~~~

`Extension` là một kiểu con gián tiếp của `Root`, thông qua `OpenBranch`. Nó không phải một phần tử trong danh sách kiểu con **trực tiếp** được `Root` cho phép.

Từ `getPermittedSubclasses() == null` không thể suy ra “không có lớp con”. API không liệt kê toàn bộ hậu duệ thực tế hoặc toàn bộ các lớp đã được nạp.

## 5. Record, enum, mảng, primitive và void

### 5.1. Record không sealed

Record là lớp final một cách ngầm định. Với `Point` trong chương trình:

~~~text
record -> sealed=false; permitted=null
~~~

Đây không phải một nhánh mở của phân cấp. Record không cho tạo lớp con, nhưng đặc điểm đó đến từ tính final, không phải trạng thái sealed.

Ngay cả khi record triển khai một interface sealed và được phép làm một nhánh trực tiếp, bản thân record vẫn là final, không tự trở thành sealed.

### 5.2. Enum cần xem cấu trúc khai báo

Enum `Light` không có hằng nào kèm phần thân lớp riêng. Nó là final ngầm định và cho:

~~~text
enum without constant bodies -> sealed=false; permitted=null
~~~

Tuy nhiên, không được suy rộng rằng mọi enum đều không sealed. Nếu ít nhất một hằng có phần thân riêng, lớp enum được sealed ngầm định; các lớp vô danh của phần thân hằng là các lớp con trực tiếp được phép.

Do đó, “không thấy chữ sealed trong mã nguồn” không đủ để kết luận `isSealed() == false`.

### 5.3. Mảng không nhận trạng thái sealed của phần tử

Cả hai token sau đều biểu diễn kiểu mảng:

~~~java
String[].class
Root[].class
~~~

Ngay cả khi `Root.class.isSealed()` là `true`, `Root[].class.isSealed()` vẫn là `false` và permitted của kiểu mảng là `null`.

Quan hệ giữa một mảng và kiểu phần tử không phải quan hệ một lớp con trong danh sách `permits`. Nếu muốn khảo sát trạng thái của kiểu phần tử, hãy lấy `getComponentType()` rồi hỏi trên token đó.

### 5.4. Primitive và void cũng có token Class

`int.class` và `void.class` là các token hợp lệ để gọi hai API. Chúng cho `false` và `null`, không ném lỗi chỉ vì không phải lớp đối tượng thông thường.

Điều đó không có nghĩa primitive hoặc `void` là các lớp có thể được kế thừa. Cần dùng các truy vấn như `isPrimitive()`, `isArray()` và `isInterface()` theo mục đích phân loại.

Cũng phân biệt token `void.class` với một biến `Class<?>` có giá trị `null`. Biến tham chiếu `null` không phải token kiểu; gọi phương thức trên nó sẽ gây `NullPointerException`.

## 6. Thí nghiệm đối chiếu: enum sealed ngầm định

Để tránh phân loại chỉ theo sự có mặt của từ khóa trong mã nguồn, tạo tệp `ImplicitSealedEnumDemo.java`:

~~~java
import java.lang.reflect.Modifier;

public class ImplicitSealedEnumDemo {
    public enum Mode {
        NORMAL,
        SPECIAL {
            @Override
            public String toString() {
                return "special";
            }
        }
    }

    public static void main(String[] args) {
        Class<?>[] permitted = Mode.class.getPermittedSubclasses();
        Class<?> bodyClass = Mode.SPECIAL.getClass();

        System.out.println("enum is sealed: " + Mode.class.isSealed());
        System.out.println("permitted count: " + permitted.length);
        System.out.println("contains constant body class: "
                + java.util.Arrays.asList(permitted).contains(bodyClass));
        System.out.println("body class is final: "
                + Modifier.isFinal(bodyClass.getModifiers()));
        System.out.println("body class is sealed: " + bodyClass.isSealed());
        System.out.println("body permitted is null: "
                + (bodyClass.getPermittedSubclasses() == null));
    }
}
~~~

Biên dịch và chạy:

~~~bash
javac --release 17 -encoding UTF-8 ImplicitSealedEnumDemo.java
java ImplicitSealedEnumDemo
~~~

Kết quả:

~~~text
enum is sealed: true
permitted count: 1
contains constant body class: true
body class is final: true
body class is sealed: false
body permitted is null: true
~~~

Ở đây:

- `Mode` là sealed ngầm định vì `SPECIAL` có phần thân riêng.
- Lớp thực tế riêng của hằng `SPECIAL` là một lớp con final của `Mode`.
- Khi hỏi trên chính lớp con đó, kết quả lại là `false/null`.

Ví dụ làm rõ rằng trạng thái được quan sát trên **từng token kiểu**, không lan tự động từ enum sang lớp con của hằng hay ngược lại.

Quy tắc final hoặc sealed ngầm định của enum nằm tại [JLS §8.9](https://docs.oracle.com/javase/specs/jls/se21/html/jls-8.html#jls-8.9).

## 7. Null và mảng rỗng không thể tùy tiện đổi nghĩa cho nhau

Một đoạn mã dễ gây lỗi là:

~~~java
// Minh họa cách gọi thiếu kiểm tra; có thể gây NullPointerException.
for (Class<?> child : type.getPermittedSubclasses()) {
    System.out.println(child.getName());
}
~~~

Đoạn trên chỉ an toàn khi đã biết `type` sealed và việc gọi API hoàn tất bình thường. Nếu `type` là lớp thường, kết quả `null` khiến vòng lặp thất bại.

Có hai cách xử lý tùy hợp đồng của công cụ.

### 7.1. Chỉ xử lý kiểu sealed

Có thể kiểm tra trạng thái trước:

~~~java
// Đoạn minh họa trong một phương thức, với type khác null.
if (type.isSealed()) {
    for (Class<?> child : type.getPermittedSubclasses()) {
        System.out.println(child.getName());
    }
} else {
    System.out.println("NOT_SEALED");
}
~~~

Nhánh `else` cho biết API danh sách permitted không áp dụng theo cùng cách với một kiểu sealed. Nó không nói kiểu đó có hay không có hậu duệ.

### 7.2. Chuẩn hóa để tiện dùng nhưng giữ cờ trạng thái

Nếu tầng trình bày muốn luôn có một danh sách khác `null`, hãy giữ riêng trạng thái sealed.

Ví dụ các khai báo hỗ trợ dưới đây đặt trong một lớp; cần import `java.util.Arrays`, `java.util.List` và `java.util.Objects`:

~~~java
record SealedInfo(boolean sealed, List<Class<?>> permitted) {
}

static SealedInfo inspectSealing(Class<?> type) {
    Objects.requireNonNull(type, "type");

    Class<?>[] permitted = type.getPermittedSubclasses();
    List<Class<?>> children = permitted == null
            ? List.of()
            : List.copyOf(Arrays.asList(permitted));

    return new SealedInfo(type.isSealed(), children);
}
~~~

Cách gọi minh họa trong chương trình đầu:

~~~java
SealedInfo root = inspectSealing(Root.class);
SealedInfo open = inspectSealing(OpenBranch.class);
SealedInfo closed = inspectSealing(Closed.class);

System.out.println(root.sealed() + "/" + root.permitted().size());
System.out.println(open.sealed() + "/" + open.permitted().size());
System.out.println(closed.sealed() + "/" + closed.permitted().size());
~~~

Kết quả của riêng đoạn gọi:

~~~text
true/3
false/0
false/0
~~~

Danh sách đã chuẩn hóa rỗng cho `open` và `closed` là **quy ước của hàm hỗ trợ**, không phải kết quả nguyên bản của `Class.getPermittedSubclasses()`.

Giữ cờ `sealed` tránh làm mất khác biệt giữa “không sealed” và “sealed nhưng API trả một danh sách không có phần tử”. Nếu công cụ cần phân biệt thêm final hoặc các loại token khác, hãy bổ sung đúng thông tin phân loại cần thiết.

## 8. Vì sao API vẫn cho phép mảng rỗng với kiểu sealed?

Khai báo Java sealed thông thường phải đáp ứng các quy tắc về kiểu con được phép. Không nên từ câu chữ “mảng có thể rỗng” của Reflection mà suy ra người viết Java có thể tùy ý khai báo một lớp sealed không có nhánh hợp lệ.

Ở mức API, `getPermittedSubclasses()` cố lấy các đối tượng `Class` được ghi trong metadata và chỉ đưa vào kết quả những kiểu mà nó thu được, phù hợp quan hệ trực tiếp. Nếu không lấy được một đối tượng `Class` tương ứng, mục đó có thể bị bỏ qua theo hợp đồng phương thức.

Vì vậy, trong môi trường tải lớp hoặc đóng gói không đầy đủ, số phần tử quan sát được không nên bị coi là bản kiểm kê tuyệt đối mọi tên trong metadata class file.

Sự phân biệt vẫn là:

- `null`: kiểu không sealed.
- Mảng rỗng khác `null`: kiểu sealed nhưng không có phần tử được trả về trong lần truy vấn đó.

Không phân loại trạng thái sealed bằng cách chỉ kiểm tra số lượng phần tử. Cũng không gọi một nhánh `non-sealed` là “sealed với danh sách rỗng”.

## 9. Không suy trạng thái từ chuỗi modifier hay tên lớp

Trong class file, sealed được biểu diễn bằng thuộc tính `PermittedSubclasses`, không phải một cờ `ACC_SEALED` tương tự `ACC_FINAL`. Điều này được mô tả tại [JVMS §4.7.31](https://docs.oracle.com/javase/specs/jvms/se21/html/jvms-4.html#jvms-4.7.31).

Vì vậy, công cụ nên dùng `Class.isSealed()`, không tự tìm chữ `sealed` trong chuỗi do `Modifier.toString(...)` tạo.

Tương tự, tên lớp, việc lớp là lồng hay ở cấp cao nhất, hoặc việc có một lớp cha sealed không thay cho việc hỏi đúng trạng thái trên token hiện tại.

`getDeclaredClasses()` cũng không thay thế `getPermittedSubclasses()`: một API khảo sát các lớp thành viên được khai báo, API kia khảo sát các nhánh trực tiếp được sealed cho phép. Một lớp con có thể được khai báo ở nơi khác, và một lớp thành viên không nhất thiết là lớp con.

Khi gặp kiểu không sealed, nếu công cụ cần tìm mọi lớp con thực tế, đó là một bài toán khám phá kiểu riêng. Kết quả `null` không tự cung cấp một danh sách những lớp đó.

## 10. Tự kiểm tra

1. Một lớp `final` cho `isSealed() == false`. `getPermittedSubclasses()` trả mảng rỗng hay `null`?
2. Có thể kết luận một lớp có từ khóa `non-sealed` chỉ từ `!type.isSealed()` không?
3. `OpenBranch` có lớp con `Extension`. Vì sao permitted của `OpenBranch` vẫn bằng `null`?
4. Nếu `Root` sealed, `Root[].class.isSealed()` có tự cho `true` không?
5. Enum không có từ khóa sealed trong mã nguồn có nhất thiết cho `isSealed() == false` không?
6. Tại sao không dùng `getPermittedSubclasses().length == 0` để nhận diện kiểu không sealed?
7. Kiểu con gián tiếp của một root sealed có nhất thiết có mặt trong danh sách permitted của root không?
8. Khi hàm hỗ trợ chuẩn hóa `null` thành danh sách rỗng, vì sao nên giữ riêng cờ sealed?

Đáp án:

1. Trả về `null`.
2. Không. Nhiều kiểu khác như lớp final, lớp thường, interface thường và record cũng cho `false`.
3. Nó không sealed; API không có nhiệm vụ liệt kê các lớp con thực tế của nhánh mở.
4. Không. Kiểu mảng cho `false`; token phần tử và token mảng là hai kiểu khác nhau.
5. Không. Enum có hằng kèm phần thân riêng được sealed ngầm định.
6. Với kiểu không sealed, kết quả là `null` và truy cập `length` gây lỗi; mảng rỗng khác `null` còn có ý nghĩa API khác.
7. Không. Danh sách chỉ mô tả các kiểu con trực tiếp được phép mà API thu được.
8. Để giữ khác biệt giữa trạng thái không sealed và trạng thái sealed có danh sách trả về rỗng.
