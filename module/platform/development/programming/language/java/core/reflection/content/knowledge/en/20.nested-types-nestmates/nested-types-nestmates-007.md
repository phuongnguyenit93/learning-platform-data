# Tham số hoặc field tổng hợp để giữ ngữ cảnh bao ngoài trong Java

## 1. Vấn đề cần hiểu

Khi biên dịch **inner class** (lớp lồng không `static`), **local class** (lớp khai báo trong một khối lệnh) hoặc **anonymous class** (lớp vô danh), trình biên dịch có thể tạo thêm **tham số constructor** và **field** không được lập trình viên khai báo trong mã nguồn. Chúng truyền hoặc giữ tham chiếu đến đối tượng bao ngoài (enclosing instance) và những biến cục bộ được lớp bên trong sử dụng.

Đây là chi tiết đặc biệt quan trọng khi làm việc với **Reflection**: danh sách tham số constructor hay danh sách field nhìn ở bytecode có thể khác những gì bạn đọc được từ khai báo Java. Từ khóa `synthetic` mô tả thành phần do trình biên dịch sinh ra để thực hiện ngôn ngữ, không phải thành phần được khai báo trực tiếp trong source.

Cần phân biệt ba khái niệm:

- **Lexical enclosing class**: lớp bao quanh về mặt khai báo, ví dụ `Outer` bao quanh `Outer.Inner`.
- **Enclosing instance**: một đối tượng cụ thể của `Outer` gắn với một đối tượng `Inner`; `Outer.this` trong `Inner` dùng để truy cập đối tượng ấy.
- **Captured local variable**: biến cục bộ hoặc tham số của phương thức/constructor ở phạm vi bao quanh, được local/anonymous class sử dụng. Biến phải `final` hoặc *effectively final*; việc lưu biến này không đồng nghĩa với việc lưu một enclosing instance.

Không phải cứ thấy ký hiệu `$` trong tên lớp là chắc chắn có field tổng hợp: tên nhị phân chỉ phản ánh quy ước biên dịch phổ biến. Muốn xác định chính xác, kiểm tra cấu trúc lớp thực tế.

## 2. Tại sao cần tham số và field bổ sung?

Xét khai báo:

~~~java
class Outer {
    private final String name = "outer";

    class Inner {
        String message() {
            return Outer.this.name;
        }
    }
}
~~~

Trong mã nguồn, ta tạo `Inner` bằng `outer.new Inner()`. Đối tượng `Inner` cần biết `outer` nào là đối tượng bao ngoài để thực hiện `Outer.this.name`. Một cách triển khai thường gặp của `javac` là:

1. **Constructor ở bytecode nhận thêm đối số `Outer`** (thường nằm trước tham số do người dùng khai báo).
2. **Một field tham chiếu tới `Outer`** được gán từ đối số constructor để các phương thức của `Inner` có thể dùng về sau. Với `javac`, tên hay gặp là `this$0`; đó chỉ là tên triển khai.
3. Field mang cờ **synthetic** (có thể quan sát qua `Field.isSynthetic()`). Cách ánh xạ và tên field là chi tiết trình biên dịch, không phải API được Java bảo đảm ổn định.

Một cách hình dung gần đúng cho bytecode là:

~~~text
Outer.Inner(Outer outer, ...) {
    this.<outer-reference> = outer;
    ...
}
~~~

Đoạn trên **chỉ mô tả ý tưởng**, không phải mã Java hợp lệ: `<outer-reference>` là field ẩn, không thể khai báo hoặc gọi trực tiếp bằng tên giả định từ mã ứng dụng.

Về **ngữ nghĩa ngôn ngữ**, mỗi instance của member inner class được tạo với một enclosing instance theo các quy tắc của Java. Về **biểu diễn vật lý**, Java không buộc mọi trình biên dịch và mọi phiên bản phải tạo field giống nhau: các bản `javac` hiện đại có thể bỏ field tham chiếu bao ngoài nếu không có chỗ nào cần sử dụng nó.

## 3. Ví dụ Java 17+: quan sát qua Reflection và gọi constructor

Lưu toàn bộ chương trình sau trong tệp **`EnclosingContextDemo.java`**:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Field;
import java.util.Arrays;

public class EnclosingContextDemo {
    static class Outer {
        private final String name;

        Outer(String name) {
            this.name = name;
        }

        class Inner {
            private final int id;

            Inner(int id) {
                this.id = id;
            }

            String describe() {
                return Outer.this.name + ":" + id;
            }
        }
    }

    public static void main(String[] args) throws ReflectiveOperationException {
        Outer outer = new Outer("CTX");
        Outer.Inner normal = outer.new Inner(7);
        System.out.println("normal=" + normal.describe());

        Class<Outer.Inner> type = Outer.Inner.class;

        // Tham số Outer là tham số biên dịch bổ sung.
        Constructor<Outer.Inner> ctor =
                type.getDeclaredConstructor(Outer.class, int.class);

        Class<?>[] parameterTypes = ctor.getParameterTypes();
        System.out.println("hasOuterParameter="
                + (parameterTypes.length == 2
                    && parameterTypes[0] == Outer.class
                    && parameterTypes[1] == int.class));

        Outer.Inner reflected = ctor.newInstance(outer, 8);
        System.out.println("reflected=" + reflected.describe());

        // Inner thực sự sử dụng Outer.this nên javac cần giữ tham chiếu.
        boolean foundSyntheticOuterField = Arrays.stream(type.getDeclaredFields())
                .anyMatch(field ->
                        field.isSynthetic() && field.getType() == Outer.class);
        System.out.println("hasSyntheticOuterField=" + foundSyntheticOuterField);

        for (Field field : type.getDeclaredFields()) {
            System.out.println("field=" + field.getName()
                    + ", type=" + field.getType().getSimpleName()
                    + ", synthetic=" + field.isSynthetic());
        }
    }
}
~~~

Biên dịch và chạy bằng JDK 17 trở lên:

~~~bash
javac EnclosingContextDemo.java
java EnclosingContextDemo
~~~

**Bốn dòng đầu** khi dùng `javac` thông thường:

~~~text
normal=CTX:7
hasOuterParameter=true
reflected=CTX:8
hasSyntheticOuterField=true
~~~

Các dòng bắt đầu bằng `field=` liệt kê field thực tế. Với `javac`, bạn thường thấy field `id` có `synthetic=false` và một field tham chiếu `Outer` (thường `this$0`) có `synthetic=true`. **Không dựa vào thứ tự dòng hay chính tả tên field**: Reflection không cam kết thứ tự trả về của `getDeclaredFields()`, và chi tiết tổng hợp có thể thay đổi giữa trình biên dịch.

Vì phương thức `describe()` thực sự truy cập `Outer.this.name`, chương trình có một lý do cụ thể để giữ tham chiếu `Outer`. Nếu `Inner` không sử dụng dữ liệu của `Outer`, kết quả về field có thể khác; không nên biến sự hiện diện của `this$0` thành giả định phổ quát.

**Điểm mấu chốt của constructor:** trong source chỉ thấy `Inner(int id)`, còn Reflection trên lớp được `javac` biên dịch cần tìm `getDeclaredConstructor(Outer.class, int.class)`. Gọi nhầm `getDeclaredConstructor(int.class)` sẽ gây `NoSuchMethodException` trong ví dụ này. `Constructor.newInstance(outer, 8)` cần cả đối tượng bao ngoài và tham số `id`; gọi thiếu sẽ gây `IllegalArgumentException` do số lượng/kiểu đối số không khớp.

## 4. So sánh các kiểu lớp lồng

| Kiểu lớp | Có enclosing instance? | Điều thường thấy trong bytecode / Reflection |
| --- | --- | --- |
| **Member inner class**: `class Outer { class Inner {} }` | Có khi tạo instance; biểu thức tạo có thể là `outer.new Inner()` | Constructor `javac` thường có thêm tham số `Outer`; field giữ `Outer` khi cần truy cập đối tượng bao ngoài. |
| **Static nested class**: `static class Nested {}` | Không có enclosing instance mặc định | Không cần tham số `Outer` hoặc field `this$0` chỉ vì khai báo lồng; vẫn có thể có thành phần synthetic vì lý do khác. |
| **Local class** khai báo trong phương thức/block | Tùy ngữ cảnh khai báo và cách tạo; có thể dùng enclosing instance | Có thể có tham số/field cho outer instance và cho các biến cục bộ được capture. |
| **Anonymous class**: `new Runnable() { ... }` | Tùy ngữ cảnh tạo và biểu thức thân lớp | Có thể nhận/lưu outer instance, biến captured và các đối số cần thiết để khởi tạo superclass. |

Không nên đồng nhất **lớp lồng** với **inner class**: static nested class là nested class nhưng không phải inner class. Tương tự, local class trong ngữ cảnh `static` không tự có đối tượng bao ngoài chỉ vì được viết bên trong một lớp.

Trong inner class:

- `this` chỉ chính đối tượng inner.
- `Outer.this` chỉ đối tượng bao ngoài tương ứng, khi biểu thức này hợp lệ.
- `Outer.class` là đối tượng `Class` mô tả kiểu `Outer`, **không phải** một enclosing instance.
- `Outer.Inner.class.getDeclaringClass()` giúp xác định lớp khai báo `Inner`, nhưng **không trả về đối tượng `outer`** gắn với một instance.

## 5. Capture biến cục bộ: field khác với outer reference

Một local/anonymous class còn có thể cần giữ **giá trị của biến cục bộ** tại thời điểm tạo đối tượng. Ví dụ độc lập:

~~~java
public class LocalCaptureDemo {
    static Runnable makeTask(String label) {
        int copies = label.length(); // không phải hằng compile-time
        class Task implements Runnable {
            @Override
            public void run() {
                System.out.println(label.repeat(copies));
            }
        }
        return new Task();
    }

    public static void main(String[] args) {
        Runnable task = makeTask("Hi");
        task.run();
    }
}
~~~

Chạy:

~~~bash
javac LocalCaptureDemo.java
java LocalCaptureDemo
~~~

Stdout:

~~~text
HiHi
~~~

Sau khi `makeTask` đã kết thúc, `Task.run()` vẫn dùng được `label` và `copies` vì đối tượng local class có thể lưu các giá trị được capture trong các field do trình biên dịch thêm vào. Trong một số bytecode do `javac` tạo, tên field kiểu này có dạng `val$label` hoặc `val$copies`; tên và cách bố trí không cố định. Ví dụ nằm trong **phương thức static**, nên nó **không cần** enclosing instance của `LocalCaptureDemo`.

Những điểm cần nhớ:

- `label` và `copies` là *effectively final*: sau khi gán, không được gán lại nếu muốn capture chúng trong local/anonymous class.
- Capture biến cục bộ giữ **giá trị của biến**. Nếu giá trị là một tham chiếu tới object, cả local class và bên ngoài có thể quan sát trạng thái object thay đổi; không có nghĩa Java cho phép gán lại chính biến captured.
- Lambda (`() -> ...`) cũng có quy tắc capture, nhưng **không phải là anonymous class**. Triển khai lambda thường dùng `invokedynamic`; không áp đặt mô hình `this$0` hay `val$...` của local/anonymous class lên lambda.

## 6. Reflection: chọn đúng API và đọc đúng tín hiệu

Các API hữu ích khi phân tích cấu trúc đã biên dịch:

| API | Dùng để làm gì | Điều không nên suy luận |
| --- | --- | --- |
| `Class.getDeclaredFields()` | Lấy field khai báo trong class file, gồm field private và synthetic nếu hiện diện | Không cam kết thứ tự, không bao gồm field kế thừa. |
| `Field.isSynthetic()` | Kiểm tra cờ synthetic của một field | Không khẳng định mọi field synthetic đều là enclosing reference. |
| `Class.getDeclaredConstructors()` | Lấy constructor khai báo, kể cả non-public | Danh sách tham số không nhất thiết trùng danh sách tham số trong source. |
| `Constructor.getParameterTypes()` / `getParameters()` | Xem các tham số ở cấp Reflection | Không dùng chỉ số tham số trong source để suy ra tuyệt đối chỉ số tại bytecode. |
| `Parameter.isImplicit()` / `isSynthetic()` | Kiểm tra metadata về tham số ngầm định/tổng hợp khi có | Cờ và tên hiển thị phụ thuộc class file, phiên bản/trình biên dịch và metadata được phát hành. |
| `Class.isMemberClass()` / `isLocalClass()` / `isAnonymousClass()` | Xác định loại lớp | Không chứng minh một instance thực tế đang giữ field outer reference. |
| `Class.getDeclaringClass()` / `getEnclosingClass()` / `getEnclosingMethod()` / `getEnclosingConstructor()` | Xem quan hệ khai báo/bao quanh ở cấp kiểu | Không truy xuất trực tiếp giá trị tham chiếu bao ngoài của một object. |

**Phân biệt `synthetic` và `implicit`:** `Field.isSynthetic()` phản ánh cờ field trên bytecode. Với tham số constructor, `Parameter.isImplicit()` phản ánh tham số được ngôn ngữ khai báo ngầm; `Parameter.isSynthetic()` phản ánh tham số do trình biên dịch thêm không xuất hiện trong source theo phân loại của metadata. Đừng mặc định mọi tham số outer sẽ cho cùng giá trị các cờ trên mọi bản biên dịch. Hãy in kết quả thực tế và đối chiếu loại constructor, class file và cách build.

Khi Reflection dùng `getDeclaredConstructor(...)`, hãy xét **mảng kiểu tham số thực tế** bằng `getParameterTypes()` trước. Đừng tìm tham số chỉ bằng tên `this$0`, `arg0` hoặc một tên máy sinh khác. Việc biên dịch với `javac -parameters` giúp giữ nhiều thông tin tên tham số cho Reflection, nhưng **không xóa** những tham số do compiler bổ sung, cũng không bảo đảm mọi chi tiết nội bộ đều là API ổn định.

`getDeclaredFields()` cho phép *quan sát metadata* của field không public, nhưng việc **đọc giá trị** qua `Field.get(object)` còn phụ thuộc kiểm tra quyền truy cập. Từ Java 9, giới hạn mạnh của module có thể khiến `setAccessible(true)` không thành công đối với package không được mở; không nên viết tiện ích phụ thuộc đọc `this$0` bằng Reflection để làm logic ứng dụng.

## 7. Xem bytecode để đối chiếu

Sau khi biên dịch `EnclosingContextDemo.java`, có thể dùng:

~~~bash
javap -p 'EnclosingContextDemo$Outer$Inner'
javap -v 'EnclosingContextDemo$Outer$Inner'
~~~

Dấu nháy đơn giữ nguyên ký tự `$` trên shell có hỗ trợ dạng trích dẫn này; trên Windows PowerShell, có thể dùng dấu nháy đơn như ví dụ. Lệnh đầu in field và constructor kể cả private; lệnh `-v` hiển thị thông tin chi tiết class file, trong đó có cờ `ACC_SYNTHETIC` khi field được gắn synthetic. Với lớp trong ví dụ, tìm constructor mang tham số kiểu `EnclosingContextDemo$Outer` và một field có kiểu đó.

Nếu quan sát lớp được biên dịch từ **compiler khác** hoặc **JDK khác**, tên và số field không nhất thiết trùng. Đặc biệt, `javac` từ các bản JDK mới hơn đã có tối ưu hóa bỏ field outer-reference không dùng tới ở một số trường hợp; việc không thấy field không tự động kết luận lớp không có quan hệ enclosing instance theo ngôn ngữ.

`javap` là công cụ chẩn đoán, không phải hợp đồng cho code ứng dụng. Hãy thiết kế thao tác Reflection dựa trên cấu trúc được xác minh tại runtime, hoặc tốt hơn, tránh phụ thuộc vào các thành phần ẩn do compiler tạo.

## 8. Lỗi hay gặp và cách xử lý

**Lỗi 1 — Tìm constructor chỉ theo tham số viết trong source.**

~~~java
// Sai đối với Inner trong ví dụ phần 3:
Outer.Inner.class.getDeclaredConstructor(int.class);

// Đúng với class file javac của ví dụ:
Outer.Inner.class.getDeclaredConstructor(Outer.class, int.class);
~~~

Nếu cần khởi tạo class inner từ Reflection, trước hết có enclosing instance đúng kiểu, kiểm tra signature thực tế rồi truyền đủ đối số cho `newInstance`.

**Lỗi 2 — Coi tất cả field là dữ liệu nghiệp vụ.** Khi tự động liệt kê field để serialize, log, so sánh hoặc ánh xạ object, field synthetic có thể vô tình bị đưa vào, khiến object graph chứa thêm tham chiếu bao ngoài hoặc gây vòng tham chiếu. Hãy định nghĩa rõ chính sách field; thường cần kiểm tra `Field.isSynthetic()` và `Modifier.isStatic(field.getModifiers())`, đồng thời cân nhắc annotation/schema của nghiệp vụ. Không được xóa mù quáng field synthetic trong mọi công cụ phân tích bytecode, vì chúng có vai trò ở cấp runtime.

**Lỗi 3 — Mặc định inner class nào cũng làm outer không được GC.** Một outer reference **thực sự được giữ** bởi inner object sống lâu có thể kéo dài vòng đời outer object. Nhưng chi tiết field có thể được tối ưu nếu không dùng, nên phải xem bytecode hoặc heap thực tế trước khi chẩn đoán rò rỉ bộ nhớ. Nếu không cần outer instance, cân nhắc `static nested class` và truyền tường minh dữ liệu thiết yếu.

**Lỗi 4 — Phụ thuộc tên `this$0`/`val$...`.** Đây không phải tên ổn định trong đặc tả Java. Không hard-code chúng trong framework, unit test hay mapper; kiểm tra `isSynthetic()`, kiểu, constructor và bối cảnh cụ thể, hoặc dùng API nguồn dữ liệu rõ ràng thay vì đọc cấu trúc ẩn.

**Lỗi 5 — Nhầm capture local với outer capture.** Local class ở trong phương thức static vẫn có thể giữ biến cục bộ, nhưng không có enclosing instance ngầm. Quan sát constructor và field theo **ngữ cảnh tạo object**, không chỉ theo vị trí viết class.

**Lỗi 6 — Dựa vào thứ tự của Reflection.** Không nên dựa vào thứ tự `getDeclaredFields()`, `getDeclaredConstructors()` hoặc suy luận “tham số thứ 0 luôn là do người dùng khai báo”. Với constructor cần tương thích compiler cụ thể, định vị theo signature thực và xác minh mỗi tham số.

## 9. Câu hỏi tự kiểm tra

1. Với `Outer.Inner` dùng `Outer.this`, vì sao Reflection thường thấy constructor có thêm tham số `Outer` dù source chỉ khai báo `Inner(int)`?
2. Vì sao `static class Nested` không cần tham chiếu outer instance chỉ vì được khai báo bên trong `Outer`?
3. Một local class trong phương thức static sử dụng biến `String label` có thể có field synthetic không? Nó có cần một object `Outer` không?
4. Nếu một bản `javac` không sinh `this$0` khi inner class không truy cập outer, điều đó có cho phép giả định mọi inner class khác cũng không có field ấy không?
5. Khi dựng mapper Reflection, vì sao nên xem xét `Field.isSynthetic()` và tránh coi tên field do compiler đặt là API?

**Ghi nhớ:** tham số/field tổng hợp là một cách trình biên dịch hiện thực hóa enclosing instance và biến được capture. Phân biệt **quan hệ của source Java** với **chi tiết class file**, và khi dùng Reflection phải kiểm tra cấu trúc thực tế thay vì dựa vào tên nội bộ hoặc chữ ký constructor nhìn thấy trong source.
